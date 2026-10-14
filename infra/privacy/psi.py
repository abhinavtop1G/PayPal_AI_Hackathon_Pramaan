"""Private set intersection (PSI) between a bank and a telecom operator, Diffie-Hellman style.

The question the bank wants answered at call time: "has the number now calling my customer been reported to the 1930
helpline?". The telecom holds the reported numbers; the bank holds the numbers calling its customers. Neither should
hand its list to the other (DPDP 2023: purpose limitation, data minimisation). DH-PSI answers the question while
revealing only the intersection to the bank, and only the set sizes to the telecom:

    H(x)  = hash of a phone number into the prime-order subgroup of a 2048-bit MODP group (RFC 3526, group 14)
    bank:     sends   { H(x)^a }            for its numbers x           (a: bank secret)
    telecom:  returns { (H(x)^a)^b }         in the same order          (b: telecom secret)
              sends   { H(y)^b } shuffled   for reported numbers y
    bank:     computes { (H(y)^b)^a } and matches against { H(x)^ab }: equal exactly when x == y

Exponentiation commutes, so H(x)^ab == H(y)^ba iff H(x) == H(y). Without b the bank cannot test a number it doesn't
hold; without a the telecom cannot invert H(x)^a (decisional Diffie-Hellman). This is a teaching-grade implementation
(semi-honest parties, no malicious-security extensions, Python ints): fine for the demo, not for production, where an
audited library over an elliptic-curve group would be used.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field

# RFC 3526, 2048-bit MODP group (group 14). P = 2Q + 1 with Q prime; we work in the order-Q subgroup of squares.
P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF",
    16,
)
Q = (P - 1) // 2


def normalise(number: str) -> str:
    """Canonical Indian phone number: digits only, leading +91 / 0 removed ('+91 98XXX…' and '098…' match)."""
    d = re.sub(r"\D", "", number)
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    return d.lstrip("0") or d


def hash_to_group(number: str) -> int:
    """Map a number to a quadratic residue mod P (an element of the order-Q subgroup)."""
    h = int.from_bytes(hashlib.sha512(b"raksham-psi-v1|" + normalise(number).encode()).digest(), "big")
    return pow(h % P, 2, P)


@dataclass
class Party:
    """One side of the protocol. `secret` never leaves the party."""
    name: str
    items: list[str]
    # 256-bit secret exponents (~128-bit security for discrete log in this subgroup) keep each blinding to ~1 ms
    secret: int = field(default_factory=lambda: 1 + secrets.randbelow(2**256), repr=False)

    def blind(self) -> list[int]:
        """H(x)^s for own items, in item order."""
        return [pow(hash_to_group(x), self.secret, P) for x in self.items]

    def reblind(self, values: list[int]) -> list[int]:
        """Raise the other party's blinded values to this party's secret, keeping their order."""
        return [pow(v, self.secret, P) for v in values]


@dataclass
class PSIResult:
    matches: list[str]          # bank-side items found in the telecom's set (only the bank learns these)
    bank_size: int              # what the telecom learns: the size of the bank's query …
    telecom_size: int           # … and what the bank learns about the telecom: the size of its set
    messages: int               # group elements exchanged


def run_psi(bank_numbers: list[str], telecom_reported: list[str], rng: secrets.SystemRandom | None = None) -> PSIResult:
    """Run both parties in one process (for the demo and tests) and return the bank's view."""
    rng = rng or secrets.SystemRandom()
    bank, telecom = Party("bank", list(bank_numbers)), Party("telecom", list(telecom_reported))
    m1 = bank.blind()                         # bank -> telecom
    m2 = telecom.reblind(m1)                  # telecom -> bank (same order: the bank can map back to its items)
    m3 = telecom.blind()
    rng.shuffle(m3)                           # telecom -> bank (shuffled: hides which reported number matched)
    theirs = set(bank.reblind(m3))
    matches = [x for x, v in zip(bank.items, m2) if v in theirs]
    return PSIResult(matches=matches, bank_size=len(m1), telecom_size=len(m3), messages=len(m1) + len(m2) + len(m3))
