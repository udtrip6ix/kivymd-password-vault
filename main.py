from pathlib import Path

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast import toast
from kivymd.uix.screenmanager import MDScreenManager

from core.config import (
    APP_NAME,
    DEFAULT_CLIPBOARD_CLEAR_SECONDS,
    get_db_path,
    get_decoy_db_path,
)
from core.crypto import CryptoError
from core.database import DatabaseError, VaultDatabase
from ui.screens import AuthScreen, EntryEditScreen, VaultScreen


class PassVaultApp(MDApp):
    ui_scale = NumericProperty(1.0)
    is_decoy_mode = BooleanProperty(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = APP_NAME
        self.main_db: VaultDatabase | None = None
        self.decoy_db: VaultDatabase | None = None
        self.db: VaultDatabase | None = None
        self.session_key: bytes | None = None
        self._last_copied_secret: str | None = None
        self._clipboard_event = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"

        if platform != "android":
            Window.size = (412, 892)

        Window.bind(size=self._update_ui_scale)
        self._update_ui_scale(Window, Window.size)

        data_dir = self.user_data_dir if platform == "android" else None
        self.main_db = VaultDatabase(get_db_path(data_dir))
        self.decoy_db = VaultDatabase(get_decoy_db_path(data_dir))
        self.db = self.main_db

        kv_path = Path(__file__).resolve().parent / "ui" / "vault.kv"
        Builder.load_file(str(kv_path))

        sm = MDScreenManager()
        sm.add_widget(AuthScreen())
        sm.add_widget(VaultScreen())
        sm.add_widget(EntryEditScreen())
        sm.current = "auth"
        return sm

    def _update_ui_scale(self, _window, size) -> None:
        width, height = size
        if width <= 0 or height <= 0:
            return
        base_width = 390.0
        aspect_ratio = height / width
        width_factor = width / base_width
        aspect_factor = max(0.88, min(1.12, (aspect_ratio / 2.0) ** 0.25))
        raw_scale = width_factor * aspect_factor
        self.ui_scale = max(0.85, min(1.45, raw_scale))

    def authenticate_vault(self, password: str) -> tuple[VaultDatabase, bytes, bool]:
        if self.main_db is None or self.decoy_db is None:
            raise DatabaseError("Базы данных не инициализированы.")

        main_err: Exception | None = None
        try:
            key = self.main_db.unlock(password)
            return self.main_db, key, False
        except (DatabaseError, CryptoError) as exc:
            main_err = exc

        if self.decoy_db.is_initialized():
            try:
                decoy_key = self.decoy_db.unlock(password)
                return self.decoy_db, decoy_key, True
            except (DatabaseError, CryptoError):
                pass

        raise main_err or CryptoError("Неверный мастер-пароль.")

    def configure_decoy_vault(self, decoy_password: str, main_password_check: str) -> None:
        if self.is_decoy_mode or self.main_db is None or self.decoy_db is None:
            raise DatabaseError("Настройка decoy-режима доступна только в основном хранилище.")
        if decoy_password == main_password_check:
            raise CryptoError("Пароль decoy-хранилища должен отличаться от основного.")

        # Проверяем, что пароль подходит к текущему основному хранилищу
        self.main_db.unlock(main_password_check)

        db_path = self.decoy_db.db_path
        if db_path.exists():
            db_path.unlink()
        self.decoy_db = VaultDatabase(db_path)
        self.decoy_db.initialize_vault(decoy_password)

    def copy_secret_to_clipboard(self, secret: str, title: str = "") -> None:
        Clipboard.copy(secret)
        self._last_copied_secret = secret
        msg = f"Пароль скопирован ({title})" if title else "Пароль скопирован"
        toast(msg)
        if self._clipboard_event is not None:
            self._clipboard_event.cancel()
        self._clipboard_event = Clock.schedule_once(
            self._clear_clipboard, DEFAULT_CLIPBOARD_CLEAR_SECONDS
        )

    def _clear_clipboard(self, _dt) -> None:
        self._clipboard_event = None
        if self._last_copied_secret and Clipboard.paste() == self._last_copied_secret:
            Clipboard.copy("")
        self._last_copied_secret = None

    def open_session(self, target_db: VaultDatabase, fernet_key: bytes, is_decoy: bool) -> None:
        self.db = target_db
        self.session_key = fernet_key
        self.is_decoy_mode = is_decoy
        self.root.current = "vault"

    def lock_vault(self) -> None:
        self.session_key = None
        self.is_decoy_mode = False
        self.db = self.main_db
        if self.root is not None:
            self.root.current = "auth"

    def on_pause(self) -> bool:
        self.lock_vault()
        return True


if __name__ == "__main__":
    PassVaultApp().run()