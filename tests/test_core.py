from pathlib import Path
import pytest

from core.crypto import CryptoError
from core.database import DatabaseError, VaultDatabase
from core.password_tools import (
    PasswordGenConfig,
    PasswordToolsError,
    audit_entries,
    evaluate_password_weakness,
    generate_password,
)


def test_vault_lifecycle_and_wrong_password(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.db"
    db = VaultDatabase(db_path)
    assert db.is_initialized() is False

    key = db.initialize_vault("StrongMaster_2026", iterations=20_000)
    assert db.is_initialized() is True

    with pytest.raises(DatabaseError):
        db.initialize_vault("AnotherMaster_2026", iterations=20_000)

    entry_id = db.add_entry(
        fernet_key=key,
        title="Mail",
        secret="P@ssw0rd_Mail_99",
        username="user@example.com",
        category="Email",
        note="backup code in safe",
        is_favorite=True,
    )

    with pytest.raises(CryptoError):
        db.unlock("WrongMasterPassword")

    unlocked_key = db.unlock("StrongMaster_2026")
    entry = db.get_entry(entry_id, unlocked_key)
    assert entry is not None
    assert entry.title == "Mail"
    assert entry.secret == "P@ssw0rd_Mail_99"
    assert entry.note == "backup code in safe"
    assert entry.is_favorite is True

    assert db.update_entry(
        entry_id=entry_id,
        fernet_key=unlocked_key,
        title="Mail Updated",
        secret="NewP@ssw0rd_2026!",
        username="user@example.com",
        category="Email",
        is_favorite=False,
    )
    updated = db.get_entry(entry_id, unlocked_key)
    assert updated is not None
    assert updated.title == "Mail Updated"
    assert updated.secret == "NewP@ssw0rd_2026!"
    assert updated.is_favorite is False

    assert db.delete_entry(entry_id) is True
    assert db.get_entry(entry_id, unlocked_key) is None


def test_password_generator_and_audit(tmp_path: Path) -> None:
    cfg = PasswordGenConfig(length=18, exclude_ambiguous=True)
    pwd = generate_password(cfg)
    assert len(pwd) == 18
    assert not any(ch in "0O1lI" for ch in pwd)
    assert evaluate_password_weakness(pwd, min_length=10) == []

    with pytest.raises(PasswordToolsError):
        generate_password(PasswordGenConfig(length=2))

    db = VaultDatabase(tmp_path / "audit.db")
    key = db.initialize_vault("MasterAudit_123", iterations=20_000)

    db.add_entry(key, "Service A", "SameSecret123!", username="a")
    db.add_entry(key, "Service B", "SameSecret123!", username="b")
    db.add_entry(key, "Weak Service", "1234", username="c")

    entries = db.list_entries(key)
    report = audit_entries(entries, min_length=10)

    assert report.total_entries == 3
    assert report.duplicate_entries_count == 2
    assert report.weak_entries_count >= 1