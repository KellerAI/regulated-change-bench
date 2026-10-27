import pytest

from payments.vault import SealError, Vault, is_sealed


def test_round_trip():
    vault = Vault()
    sealed = vault.seal("880012345678")
    assert is_sealed(sealed)
    assert "880012345678" not in sealed
    assert vault.open(sealed) == "880012345678"


def test_same_plaintext_seals_differently():
    vault = Vault()
    assert vault.seal("990000123") != vault.seal("990000123")


def test_fixed_nonce_is_deterministic():
    vault = Vault(nonce_source=lambda n: b"\x01" * n)
    assert vault.seal("abc") == vault.seal("abc")


def test_tampering_is_detected():
    vault = Vault()
    sealed = vault.seal("00-1234567")
    flipped = sealed[:-6] + ("A" if sealed[-6] != "A" else "B") + sealed[-5:]
    with pytest.raises(SealError):
        vault.open(flipped)


def test_other_secret_cannot_open():
    sealed = Vault(master_secret=b"one").seal("secret")
    with pytest.raises(SealError):
        Vault(master_secret=b"two").open(sealed)


def test_rotation_keeps_old_values_readable():
    vault = Vault()
    old = vault.seal("1975-03-14")
    assert vault.rotate() == 2
    new = vault.seal("1975-03-14")
    assert vault.version_of(old) == 1
    assert vault.version_of(new) == 2
    assert vault.open(old) == vault.open(new) == "1975-03-14"


def test_unknown_version_and_plaintext_are_rejected():
    vault = Vault()
    with pytest.raises(SealError):
        vault.open("llv9:AAAA")
    with pytest.raises(SealError):
        vault.open("880012345678")
    assert not is_sealed(None)


def test_unicode_values():
    vault = Vault()
    assert vault.open(vault.seal("Zoë Ångström")) == "Zoë Ångström"
