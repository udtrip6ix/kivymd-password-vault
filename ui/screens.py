from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.screen import MDScreen

from core.crypto import CryptoError
from core.database import DatabaseError


class AuthScreen(MDScreen):
    is_setup_mode = BooleanProperty(False)
    status_text = StringProperty("")

    def on_pre_enter(self, *args) -> None:
        app = App.get_running_app()
        self.is_setup_mode = not app.db.is_initialized()
        self.status_text = ""
        if "password_field" in self.ids:
            self.ids.password_field.text = ""
        if "confirm_field" in self.ids:
            self.ids.confirm_field.text = ""

    def submit_auth(self) -> None:
        app = App.get_running_app()
        password = self.ids.password_field.text.strip()

        if not password:
            self.status_text = "Введите мастер-пароль."
            return

        if self.is_setup_mode:
            confirm = self.ids.confirm_field.text.strip()
            if len(password) < 8:
                self.status_text = "Минимум 8 символов для мастер-пароля."
                return
            if password != confirm:
                self.status_text = "Пароли не совпадают."
                return
            try:
                key = app.db.initialize_vault(password)
            except (DatabaseError, CryptoError) as exc:
                self.status_text = str(exc)
                return
        else:
            try:
                key = app.db.unlock(password)
            except (DatabaseError, CryptoError) as exc:
                self.status_text = str(exc)
                return

        self.ids.password_field.text = ""
        if "confirm_field" in self.ids:
            self.ids.confirm_field.text = ""
        self.status_text = ""
        app.open_session(key)


class VaultScreen(MDScreen):
    def lock_now(self) -> None:
        App.get_running_app().lock_vault()