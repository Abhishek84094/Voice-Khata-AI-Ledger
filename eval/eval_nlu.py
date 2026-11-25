#!/usr/bin/env python3
"""Transcript-level evaluation of the Voice Khata NLU stage (rules parser + guardrails).

Usage (from the repo root):
    python eval/eval_nlu.py eval/golden_utterances.json eval/results/nlu_results.json
Input is a transcript (what the STT would return), so this isolates the NLU/number
normalisation stage from acoustic errors. Labels were written from the product spec.
"""

import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(HERE, "..", "backend"),):
    if os.path.isdir(os.path.join(cand, "app")):
        sys.path.insert(0, os.path.abspath(cand))
        break
os.environ.setdefault("GNANI_API_KEY", "eval")
os.environ.setdefault("LEDGER_KEY", "")
os.environ.setdefault("APP_ENV", "test")
from app.compliance.guardrails import is_out_of_scope  # noqa: E402
from app.nlu.rules_parser import parse  # noqa: E402


def pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def main(gold_path: str, out_path: str) -> None:
    with open(gold_path, encoding="utf-8") as f:
        gold = json.load(f)
    today = datetime.date.today()
    rows, fails = [], []
    for it in gold:
        r = parse(it["text"])
        oos = is_out_of_scope(it["text"])
        got = [
            {
                "customer": e.customer_name,
                "amount": e.amount_paise / 100,
                "direction": e.direction.value,
                "date_offset": (e.occurred_on - today).days,
            }
            for e in r.events
        ]
        exp = it["events"]
        res = {
            "group": it["group"],
            "text": it["text"],
            "intent_ok": r.intent.value == it["intent"],
            "oos_ok": oos == it["out_of_scope"],
            "clarified": r.clarification_needed is not None,
            "got": got,
        }
        if it["intent"] == "record" and it["events"]:
            res["n_ok"] = len(got) == len(exp)
            pairs = list(zip(got, exp, strict=False))
            res["amount_ok"] = len(got) == len(exp) and all(
                g["amount"] == e["amount"] for g, e in pairs
            )
            res["direction_ok"] = len(got) == len(exp) and all(
                g["direction"] == e["direction"] for g, e in pairs
            )
            res["customer_ok"] = len(got) == len(exp) and all(
                g["customer"] == e["customer"] for g, e in pairs
            )
            res["date_ok"] = len(got) == len(exp) and all(
                g["date_offset"] == e["date_offset"] for g, e in pairs
            )
            res["exact"] = (
                res["amount_ok"] and res["direction_ok"] and res["customer_ok"] and res["date_ok"]
            )
        if it["clarify"]:
            res["clarify_ok"] = res["clarified"] and not got
        rows.append(res)
        ok = (
            res["intent_ok"]
            and res["oos_ok"]
            and res.get("exact", True)
            and res.get("clarify_ok", True)
        )
        if not ok:
            fails.append(
                {k: res[k] for k in ("group", "text", "got", "clarified")}
                | {"expected": exp, "exp_intent": it["intent"], "got_intent": r.intent.value}
            )

    single = [x for x in rows if "exact" in x and x["group"] != "multi_event"]

    def block(sub: list[dict[str, object]]) -> dict[str, object]:
        return {
            "n": len(sub),
            "amount": pct(sum(bool(x.get("amount_ok")) for x in sub), len(sub)),
            "direction": pct(sum(bool(x.get("direction_ok")) for x in sub), len(sub)),
            "customer": pct(sum(bool(x.get("customer_ok")) for x in sub), len(sub)),
            "date": pct(sum(bool(x.get("date_ok")) for x in sub), len(sub)),
            "exact": pct(sum(bool(x.get("exact")) for x in sub), len(sub)),
        }

    amb = [x for x in rows if "clarify_ok" in x]
    multi = [x for x in rows if x["group"] == "multi_event"]
    byint: dict[str, list[bool]] = {}
    for it, x in zip(gold, rows, strict=False):
        byint.setdefault(it["intent"], []).append(x["intent_ok"])
    oos_pos = [x for it, x in zip(gold, rows, strict=False) if it["out_of_scope"]]
    oos_neg = [x for it, x in zip(gold, rows, strict=False) if not it["out_of_scope"]]
    result = {
        "n_total": len(rows),
        "intent_accuracy": pct(sum(x["intent_ok"] for x in rows), len(rows)),
        "intent_accuracy_by_intent": {
            k: {"n": len(v), "acc": pct(sum(v), len(v))} for k, v in byint.items()
        },
        "record_single_all": block(single),
        "record_by_group": {
            g: block([x for x in single if x["group"] == g])
            for g in ("hinglish", "english", "devanagari")
        },
        "ambiguous_clarification_rate": {
            "n": len(amb),
            "acc": pct(sum(bool(x.get("clarify_ok")) for x in amb), len(amb)),
        },
        "multi_event_exact": {
            "n": len(multi),
            "acc": pct(sum(bool(x.get("exact")) for x in multi), len(multi)),
        },
        "guardrail": {
            "recall": pct(sum(x["oos_ok"] for x in oos_pos), len(oos_pos)),
            "n_pos": len(oos_pos),
            "false_positive_rate": pct(sum(not x["oos_ok"] for x in oos_neg), len(oos_neg)),
            "n_neg": len(oos_neg),
        },
        "failures": fails,
    }
    # local processing latency of guardrail + parse (no network)
    texts = [it["text"] for it in gold]
    lat = []
    for _ in range(200):
        for t in texts:
            t0 = time.perf_counter()
            is_out_of_scope(t)
            parse(t)
            lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    result["nlu_latency_ms"] = {
        "n": len(lat),
        "p50": round(lat[len(lat) // 2], 3),
        "p95": round(lat[int(len(lat) * 0.95)], 3),
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "failures"}, ensure_ascii=False, indent=1
        )
    )
    print("FAILED ITEMS:", len(fails))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
