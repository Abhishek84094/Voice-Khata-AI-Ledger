"""Benchmark script measuring live latency (p50/p95) for Sarvam AI and Groq."""

import json
import os
import statistics
import time
from pathlib import Path

import dotenv
import httpx

dotenv.load_dotenv()
SARVAM_KEY = os.getenv("SARVAM_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")


def measure_groq_llm(iterations: int = 10) -> dict[str, object]:
    print(f"Benchmarking Groq (qwen/qwen3.8-27b) over {iterations} requests...")
    latencies: list[float] = []
    valid_json_count = 0

    with httpx.Client(timeout=10.0) as client:
        for _ in range(iterations):
            prompt = (
                'Extract as JSON: "Ramesh ka 340 udhaar, Sunday ko dega". '
                "Fields: customer, amount, direction, due_date"
            )
            t0 = time.perf_counter()
            r = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "qwen/qwen3.8-27b",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                    "max_tokens": 100,
                },
            )
            dt = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt)
            if r.status_code == 200:
                try:
                    data = r.json()
                    json.loads(data["choices"][0]["message"]["content"])
                    valid_json_count += 1
                except Exception:
                    pass

    latencies.sort()
    return {
        "provider": "Groq",
        "model": "qwen/qwen3.8-27b",
        "n": len(latencies),
        "p50_ms": round(latencies[len(latencies) // 2], 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "json_validity_rate": round(100.0 * valid_json_count / len(latencies), 1),
    }


def measure_sarvam_tts(iterations: int = 5) -> dict[str, object]:
    print(f"Benchmarking Sarvam TTS (bulbul:v4-flash) over {iterations} requests...")
    latencies: list[float] = []

    with httpx.Client(timeout=15.0) as client:
        for _ in range(iterations):
            t0 = time.perf_counter()
            r = client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": SARVAM_KEY, "Content-Type": "application/json"},
                json={
                    "inputs": ["रमेश, ₹340 उधार. हो गया."],
                    "target_language_code": "hi-IN",
                    "speaker": "amit_hi_conversational",
                    "model": "bulbul:v4-flash",
                },
            )
            dt = (time.perf_counter() - t0) * 1000.0
            if r.status_code == 200:
                latencies.append(dt)

    latencies.sort()
    return {
        "provider": "Sarvam AI",
        "service": "TTS",
        "model": "bulbul:v4-flash",
        "n": len(latencies),
        "p50_ms": round(latencies[len(latencies) // 2], 1) if latencies else None,
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1) if latencies else None,
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
    }


def measure_sarvam_stt(iterations: int = 5) -> dict[str, object]:
    print(f"Benchmarking Sarvam STT (saaras:v3) over {iterations} requests...")
    # First obtain sample audio
    with httpx.Client(timeout=15.0) as client:
        tts_res = client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": SARVAM_KEY, "Content-Type": "application/json"},
            json={
                "inputs": ["सुरेश ने पांच सौ रुपये दिए"],
                "target_language_code": "hi-IN",
                "speaker": "amit_hi_conversational",
                "model": "bulbul:v4-flash",
            },
        )
        audio_b64 = tts_res.json()["audios"][0]
        import base64

        audio_bytes = base64.b64decode(audio_b64)

        latencies: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            r = client.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": SARVAM_KEY},
                files={"file": ("sample.wav", audio_bytes, "audio/wav")},
                data={"model": "saaras:v3", "language_code": "hi-IN"},
            )
            dt = (time.perf_counter() - t0) * 1000.0
            if r.status_code == 200:
                latencies.append(dt)

    latencies.sort()
    return {
        "provider": "Sarvam AI",
        "service": "STT",
        "model": "saaras:v3",
        "n": len(latencies),
        "p50_ms": round(latencies[len(latencies) // 2], 1) if latencies else None,
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1) if latencies else None,
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
    }


def main() -> None:
    results: dict[str, object] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "groq_llm": measure_groq_llm(10),
        "sarvam_tts": measure_sarvam_tts(5),
        "sarvam_stt": measure_sarvam_stt(5),
    }

    out_file = Path("eval/results/provider_bakeoff.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\n--- BENCHMARK RESULTS ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
