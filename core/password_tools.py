import secrets
import string
from collections import defaultdict
from dataclasses import dataclass

from core.database import VaultEntry


AMBIGUOUS_CHARS = set("0O1lI")
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}"


class PasswordToolsError(Exception):
    pass


@dataclass(frozen=True)
class PasswordGenConfig:
    length: int = 16
    use_lowercase: bool = True
    use_uppercase: bool = True
    use_digits: bool = True
    use_symbols: bool = True
    exclude_ambiguous: bool = True
    custom_symbols: str = DEFAULT_SYMBOLS


@dataclass(frozen=True)
class AuditReport:
    total_entries: int
    duplicate_groups: dict[str, list[VaultEntry]]
    weak_entries: list[tuple[VaultEntry, list[str]]]

    @property
    def duplicate_entries_count(self) -> int:
        return sum(len(group) for group in self.duplicate_groups.values())

    @property
    def weak_entries_count(self) -> int:
        return len(self.weak_entries)


def _filter_charset(charset: str, exclude_ambiguous: bool) -> str:
    if not exclude_ambiguous:
        return charset
    return "".join(ch for ch in charset if ch not in AMBIGUOUS_CHARS)


def generate_password(config: PasswordGenConfig | None = None) -> str:
    cfg = config or PasswordGenConfig()
    if cfg.length < 4:
        raise PasswordToolsError("Длина пароля должна быть не менее 4 символов.")

    pools: list[str] = []
    if cfg.use_lowercase:
        pool = _filter_charset(string.ascii_lowercase, cfg.exclude_ambiguous)
        if pool:
            pools.append(pool)
    if cfg.use_uppercase:
        pool = _filter_charset(string.ascii_uppercase, cfg.exclude_ambiguous)
        if pool:
            pools.append(pool)
    if cfg.use_digits:
        pool = _filter_charset(string.digits, cfg.exclude_ambiguous)
        if pool:
            pools.append(pool)
    if cfg.use_symbols:
        pool = _filter_charset(cfg.custom_symbols, cfg.exclude_ambiguous)
        if pool:
            pools.append(pool)

    if not pools:
        raise PasswordToolsError("Не выбран ни один набор символов для генерации пароля.")
    if cfg.length < len(pools):
        raise PasswordToolsError(
            f"Длина пароля ({cfg.length}) меньше числа выбранных наборов символов ({len(pools)})."
        )

    chars: list[str] = [secrets.choice(pool) for pool in pools]
    combined = "".join(pools)
    chars.extend(secrets.choice(combined) for _ in range(cfg.length - len(chars)))

    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


def evaluate_password_weakness(password: str, min_length: int = 10) -> list[str]:
    reasons: list[str] = []
    if not password:
        return ["пустой пароль"]
    if len(password) < min_length:
        reasons.append(f"длина меньше {min_length} символов")
    if not any(c.islower() for c in password):
        reasons.append("нет строчных букв")
    if not any(c.isupper() for c in password):
        reasons.append("нет заглавных букв")
    if not any(c.isdigit() for c in password):
        reasons.append("нет цифр")
    if not any(not c.isalnum() for c in password):
        reasons.append("нет спецсимволов")
    if len(set(password)) <= 3:
        reasons.append("слишком мало уникальных символов")
    return reasons


def audit_entries(entries: list[VaultEntry], min_length: int = 10) -> AuditReport:
    grouped_by_secret: dict[str, list[VaultEntry]] = defaultdict(list)
    weak_entries: list[tuple[VaultEntry, list[str]]] = []

    for entry in entries:
        grouped_by_secret[entry.secret].append(entry)
        reasons = evaluate_password_weakness(entry.secret, min_length=min_length)
        if reasons:
            weak_entries.append((entry, reasons))

    duplicate_groups = {
        secret: group for secret, group in grouped_by_secret.items() if len(group) > 1
    }

    return AuditReport(
        total_entries=len(entries),
        duplicate_groups=duplicate_groups,
        weak_entries=weak_entries,
    )