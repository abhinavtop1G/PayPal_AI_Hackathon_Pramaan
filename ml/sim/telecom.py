"""Caller phone numbers and the telecom operator's database of numbers reported to the 1930 helpline.

Scam syndicates run a pool of numbers and reuse them across victims, so a good share of the numbers that call victims
have already been reported by earlier victims. Genuine unknown callers (hospitals, delivery agents, relatives on a new
SIM) come from a huge pool in which a very small fraction is wrongly reported. All draws use private seeded RNGs, so
adding numbers never changes the rest of the simulation.

    REPORTED_SHARE        share of a syndicate's numbers that are already in the telecom's reported list
    FALSE_REPORT_SHARE    share of genuine numbers wrongly reported (spite reports, recycled numbers)
"""
from __future__ import annotations

import hashlib

import numpy as np

NUMBERS_PER_SYNDICATE = 40
REPORTED_SHARE = 0.45
GENUINE_POOL = 60_000
FALSE_REPORT_SHARE = 0.004


def _u(*parts) -> float:
    """Deterministic uniform in [0, 1) from a key."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "little") / 2**64


def syndicate_number(syndicate: int, k: int, voip: bool) -> tuple[str, bool]:
    """The k-th number of a syndicate's pool and whether the telecom has it on the reported list."""
    base = int(_u("synd", syndicate, k) * 1e8)
    number = f"+44 20 {base // 10000:04d} {base % 10000:04d}" if voip else f"+91 7{base:09d}"[:14]
    return number, _u("synd-reported", syndicate, k) < REPORTED_SHARE


def genuine_number(k: int, voip: bool) -> tuple[str, bool]:
    base = int(_u("genuine", k) * 1e9)
    number = f"+971 4 {base % 10_000_000:07d}" if voip else f"+91 9{base:09d}"[:14]
    return number, _u("genuine-reported", k) < FALSE_REPORT_SHARE


def fresh_number(rng: np.random.Generator) -> tuple[str, bool]:
    """A brand-new SIM / virtual number nobody has reported yet (adaptive scammers)."""
    return f"+91 6{int(rng.integers(0, 10**9)):09d}", False


def contact_number(user_id: str) -> tuple[str, bool]:
    return f"+91 8{int(_u('contact', user_id) * 1e9):09d}", False


def reported_numbers(n_syndicates: int) -> set[str]:
    """The telecom's list: every reported syndicate number plus the wrongly reported genuine ones."""
    out = set()
    for s in range(n_syndicates):
        for k in range(NUMBERS_PER_SYNDICATE):
            for voip in (False, True):
                n, rep = syndicate_number(s, k, voip)
                if rep:
                    out.add(n)
    for k in range(GENUINE_POOL):
        if _u("genuine-reported", k) < FALSE_REPORT_SHARE:
            for voip in (False, True):
                out.add(genuine_number(k, voip)[0])
    return out
