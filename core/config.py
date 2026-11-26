from pathlib import Path

APP_NAME = "PassVault"
KDF_ITERATIONS = 300_000
DEFAULT_AUTO_LOCK_SECONDS = 120
DEFAULT_CLIPBOARD_CLEAR_SECONDS = 25
MAIN_DB_FILENAME = "vault.db"
DECOY_DB_FILENAME = "decoy.db"


def get_db_path(user_data_dir: str | None = None, filename: str = MAIN_DB_FILENAME) -> Path:
    base_dir = Path(user_data_dir) if user_data_dir else Path("data")
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / filename


def get_decoy_db_path(user_data_dir: str | None = None) -> Path:
    return get_db_path(user_data_dir, filename=DECOY_DB_FILENAME)