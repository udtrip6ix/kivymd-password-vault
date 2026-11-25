import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


DEFAULT_ITERATIONS = 300_000
SALT_SIZE = 16
VERIFY_PLAINTEXT = b"PASSVAULT_MASTER_OK_v1"


class CryptoError(Exception):
    """Ошибка криптографической операции или неверный мастер-пароль."""


@dataclass(frozen=True)
class VaultAuthParams:
    salt: bytes
    iterations: int
    verifier_token: str


def generate_salt(length: int = SALT_SIZE) -> bytes:
    return os.urandom(length)


def derive_fernet_key(master_password: str, salt: bytes, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    if not master_password:
        raise CryptoError("Мастер-пароль не может быть пустым.")
    if not salt:
        raise CryptoError("Соль (salt) не может быть пустой.")
    if iterations < 10_000:
        raise CryptoError("Слишком мало итераций PBKDF2.")

    raw_key = hashlib.pbkdf2_hmac(
        "sha256",
        master_password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    return base64.urlsafe_b64encode(raw_key)


def create_auth_params(master_password: str, iterations: int = DEFAULT_ITERATIONS) -> tuple[VaultAuthParams, bytes]:
    salt = generate_salt()
    fernet_key = derive_fernet_key(master_password, salt, iterations)
    verifier_token = encrypt_text(VERIFY_PLAINTEXT.decode("utf-8"), fernet_key)
    params = VaultAuthParams(
        salt=salt,
        iterations=iterations,
        verifier_token=verifier_token,
    )
    return params, fernet_key


def unlock_vault(master_password: str, salt: bytes, iterations: int, verifier_token: str) -> bytes:
    fernet_key = derive_fernet_key(master_password, salt, iterations)
    try:
        decrypted = decrypt_text(verifier_token, fernet_key)
    except CryptoError as exc:
        raise CryptoError("Неверный мастер-пароль или повреждённые метаданные хранилища.") from exc

    if decrypted != VERIFY_PLAINTEXT.decode("utf-8"):
        raise CryptoError("Неверный мастер-пароль.")

    return fernet_key


def encrypt_text(plaintext: str, fernet_key: bytes) -> str:
    if plaintext is None:
        raise CryptoError("Передано пустое значение (None) для шифрования.")
    token = Fernet(fernet_key).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_text(token_str: str, fernet_key: bytes) -> str:
    if not token_str:
        return ""
    try:
        plaintext_bytes = Fernet(fernet_key).decrypt(token_str.encode("ascii"))
        return plaintext_bytes.decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise CryptoError("Не удалось расшифровать данные (неверный ключ или повреждённый токен).") from exc