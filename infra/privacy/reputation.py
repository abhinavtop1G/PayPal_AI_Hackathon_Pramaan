"""Online caller-reputation check: one DH-PSI query per incoming call.

Batch PSI (psi.run_psi) suits a nightly reconciliation; at call time the bank needs one answer for one number. The same
commutative-blinding idea works per query:

    setup (once):   telecom sends its reported list blinded with b:  { H(y)^b }   (shuffled; the bank can't read it)
                    bank re-blinds with a and keeps                  { H(y)^ab }
    per call:       bank sends H(x)^a  ->  telecom returns (H(x)^a)^b = H(x)^ab  ->  bank checks membership

The telecom learns only that a query happened (not the number: it sees H(x)^a); the bank learns one bit for a number
that already called its customer. Both run in-process here; in production they would be separate services.
"""
from __future__ import annotations

import secrets
import threading

from .psi import Party


class Telecom:
    """The operator side: holds the numbers reported to 1930 and its secret exponent."""

    def __init__(self, reported: list[str] | set[str]):
        self._party = Party("telecom", sorted(reported))
        self.queries = 0

    def published_set(self) -> list[int]:
        out = self._party.blind()
        secrets.SystemRandom().shuffle(out)
        return out

    def answer(self, blinded_query: int) -> int:
        self.queries += 1
        return self._party.reblind([blinded_query])[0]


class ReputationClient:
    """The bank side: caches the doubly-blinded reported set once, then answers `is_reported(number)` per call."""

    def __init__(self, telecom: Telecom, background: bool = False):
        self.telecom = telecom
        self._bank = Party("bank", [])
        self._set: set[int] = set()
        self.cache: dict[str, bool] = {}
        self._ready = threading.Event()
        if background:  # the one-time exchange takes a few seconds; don't hold up service start
            threading.Thread(target=self._setup, daemon=True).start()
        else:
            self._setup()

    def _setup(self) -> None:
        self._set = set(self._bank.reblind(self.telecom.published_set()))
        self._ready.set()

    def is_reported(self, number: str) -> bool:
        self._ready.wait()
        if number not in self.cache:
            q = Party("bank-query", [number], secret=self._bank.secret).blind()[0]
            self.cache[number] = self.telecom.answer(q) in self._set
        return self.cache[number]

    @property
    def size(self) -> int:
        return len(self._set)
