from pathlib import Path

APP_NAME = "PassVault"
KDF_ITERATIONS = 300_000
DEFAULT_AUTO_LOCK_SECONDS = 120
DEFAULT_CLIPBOARD_CLEAR_SECONDS = 25


def get_db_path(user_data_dir: str | None = None, filename: str = "vault.db") -> Path:
    base_dir = Path(user_data_dir) if user_data_dir else Path("data")
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / filename