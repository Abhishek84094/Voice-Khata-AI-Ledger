"""In-memory customer resolution cache with phonetic keys and write invalidation (§4.3 item 5).

Sub-millisecond customer resolution across Latin and Indic scripts with alias support.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Mapping Devanagari to approximate Latin transliteration for search keys
DEVANAGARI_TO_LATIN = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "अं": "am",
    "अः": "ah",
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "ng",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "ny",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ं": "n",
    "्": "",
}


def normalize_to_search_key(name: str) -> str:
    """Normalize a customer name to a lowercase phonetic-ready ASCII search key."""
    # Transliterate Devanagari characters
    res: list[str] = []
    for ch in name:
        if ch in DEVANAGARI_TO_LATIN:
            res.append(DEVANAGARI_TO_LATIN[ch])
        else:
            res.append(ch)
    joined = "".join(res)
    # Strip accents / normalize unicode
    nfd = unicodedata.normalize("NFKD", joined)
    ascii_text = nfd.encode("ascii", "ignore").decode("ascii")
    # Clean whitespace and punctuation
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", ascii_text).lower().strip()
    return re.sub(r"\s+", " ", cleaned)


def compute_phonetic_key(search_key: str) -> str:
    """Compute a phonetic key for fuzzy Indian name matching (e.g. Ramesh / Rames)."""
    if not search_key:
        return ""
    # Simplify consonants and vowels for Indian names
    s = search_key
    s = re.sub(r"ph", "f", s)
    s = re.sub(r"kh", "k", s)
    s = re.sub(r"gh", "g", s)
    s = re.sub(r"dh", "d", s)
    s = re.sub(r"bh", "b", s)
    s = re.sub(r"sh", "s", s)
    s = re.sub(r"ee|oo", "u", s)
    s = re.sub(r"[aeiou]", "", s[1:])  # Keep first letter, remove subsequent vowels
    return (search_key[0] + s)[:8]


@dataclass
class CachedCustomer:
    id: str
    shop_id: str
    display_name: str
    search_key: str
    aliases: list[str] = field(default_factory=list)
    phonetic_key: str = ""

    def __post_init__(self) -> None:
        if not self.search_key:
            self.search_key = normalize_to_search_key(self.display_name)
        if not self.phonetic_key:
            self.phonetic_key = compute_phonetic_key(self.search_key)


class CustomerCache:
    """In-process per-shop customer cache."""

    def __init__(self) -> None:
        self._by_shop: dict[str, dict[str, CachedCustomer]] = {}
        self._by_search_key: dict[str, dict[str, list[str]]] = {}
        self._by_phonetic: dict[str, dict[str, list[str]]] = {}

    def load_shop_customers(self, shop_id: str, customers: list[CachedCustomer]) -> None:
        """Populate or refresh the in-memory cache for a shop."""
        shop_dict: dict[str, CachedCustomer] = {}
        sk_dict: dict[str, list[str]] = {}
        pk_dict: dict[str, list[str]] = {}

        for c in customers:
            shop_dict[c.id] = c

            # Index by primary search key
            sk_dict.setdefault(c.search_key, []).append(c.id)

            # Index by aliases
            for alias in c.aliases:
                alias_sk = normalize_to_search_key(alias)
                sk_dict.setdefault(alias_sk, []).append(c.id)

            # Index by phonetic key
            if c.phonetic_key:
                pk_dict.setdefault(c.phonetic_key, []).append(c.id)

        self._by_shop[shop_id] = shop_dict
        self._by_search_key[shop_id] = sk_dict
        self._by_phonetic[shop_id] = pk_dict

    def invalidate_shop(self, shop_id: str) -> None:
        """Evict a shop's cache on customer creation, deletion, or alias update."""
        self._by_shop.pop(shop_id, None)
        self._by_search_key.pop(shop_id, None)
        self._by_phonetic.pop(shop_id, None)

    def is_cached(self, shop_id: str) -> bool:
        return shop_id in self._by_shop

    def resolve_customer(
        self,
        shop_id: str,
        query: str,
    ) -> tuple[CachedCustomer | None, list[CachedCustomer]]:
        """Resolve a customer name query in microseconds.

        Returns (customer, []) if exactly one match.
        Returns (None, [matches]) if ambiguous.
        Returns (None, []) if no match.
        """
        if shop_id not in self._by_shop:
            return None, []

        query_sk = normalize_to_search_key(query)
        if not query_sk:
            return None, []

        shop_dict = self._by_shop[shop_id]
        sk_dict = self._by_search_key[shop_id]

        # 1. Exact match on search key or alias
        if query_sk in sk_dict:
            ids = sk_dict[query_sk]
            if len(ids) == 1:
                return shop_dict[ids[0]], []
            return None, [shop_dict[i] for i in ids]

        # 2. Prefix match (e.g. query "Ramesh" matches "Ramesh Kumar")
        prefix_matches: list[str] = []
        for sk, ids in sk_dict.items():
            if sk.startswith(query_sk) or query_sk.startswith(sk):
                prefix_matches.extend(ids)
        unique_prefix = list(dict.fromkeys(prefix_matches))
        if len(unique_prefix) == 1:
            return shop_dict[unique_prefix[0]], []
        if len(unique_prefix) > 1:
            return None, [shop_dict[i] for i in unique_prefix]

        # 3. Phonetic matching
        query_pk = compute_phonetic_key(query_sk)
        pk_dict = self._by_phonetic[shop_id]
        if query_pk in pk_dict:
            ids = pk_dict[query_pk]
            if len(ids) == 1:
                return shop_dict[ids[0]], []
            return None, [shop_dict[i] for i in ids]

        return None, []


_global_customer_cache = CustomerCache()


def get_customer_cache() -> CustomerCache:
    return _global_customer_cache
