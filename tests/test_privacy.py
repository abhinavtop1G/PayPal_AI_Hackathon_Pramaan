"""Privacy stubs: DH-PSI between bank and telecom, and the DPDP consent gate."""
import pytest

from infra.privacy.consent import ConsentRegistry
from infra.privacy.psi import P, Party, hash_to_group, normalise, run_psi


def test_normalise_matches_number_formats():
    assert normalise("+91 98765 43210") == normalise("098765-43210") == normalise("9876543210") == "9876543210"


def test_hash_lands_in_the_prime_order_subgroup():
    h = hash_to_group("9876543210")
    assert 1 < h < P and pow(h, (P - 1) // 2, P) == 1  # a quadratic residue


def test_psi_returns_exactly_the_intersection():
    bank = ["+91 98000 00001", "+91 98000 00002", "+44 20 7946 0321", "9800000004"]
    telecom = ["9800000002", "442079460321", "9811111111", "9822222222", "9833333333"]
    r = run_psi(bank, telecom)
    assert sorted(r.matches) == sorted(["+91 98000 00002", "+44 20 7946 0321"])
    assert (r.bank_size, r.telecom_size, r.messages) == (4, 5, 13)


def test_psi_disjoint_and_empty_sets():
    assert run_psi(["9800000001"], ["9811111111"]).matches == []
    assert run_psi([], ["9811111111"]).matches == []
    assert run_psi(["9800000001"], []).matches == []


def test_blinded_values_hide_the_number():
    """Without the secret, a blinded value doesn't equal the plain hash, and two parties blind the same number differently."""
    a, b = Party("bank", ["9800000001"]), Party("telecom", ["9800000001"])
    assert a.blind()[0] != hash_to_group("9800000001") and a.blind()[0] != b.blind()[0]
    assert a.reblind(b.blind()) == b.reblind(a.blind())  # but the doubly-blinded values agree


def test_consent_gate_purposes_expiry_and_audit():
    reg = ConsentRegistry()
    reg.grant("u1", ["fraud_prevention"], now=0)
    reg.grant("u2", ["fraud_prevention", "telecom_reputation"], ttl_s=100, now=0)
    assert reg.check("u1", "fraud_prevention", now=1)
    assert not reg.check("u1", "telecom_reputation", now=1)        # purpose not granted
    assert reg.check("u2", "telecom_reputation", now=50)
    assert not reg.check("u2", "telecom_reputation", now=150)      # expired
    assert not reg.check("nobody", "fraud_prevention", now=1)      # no artefact
    assert reg.revoke("u2") and not reg.check("u2", "fraud_prevention", now=1)
    assert len(reg.audit) == 6 and [a["allowed"] for a in reg.audit] == [True, False, True, False, False, False]
    with pytest.raises(ValueError):
        reg.grant("u3", ["marketing"])
