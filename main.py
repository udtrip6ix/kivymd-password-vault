from pathlib import Path

from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import NumericProperty
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager

from core.config import APP_NAME, get_db_path
from core.database import VaultDatabase
from ui.screens import AuthScreen, VaultScreen


class PassVaultApp(MDApp):
    ui_scale = NumericProperty(1.0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = APP_NAME
        self.db: VaultDatabase | None = None
        self.session_key: bytes | None = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"

        if platform != "android":
            Window.size = (412, 892)

        Window.bind(size=self._update_ui_scale)
        self._update_ui_scale(Window, Window.size)

        data_dir = self.user_data_dir if platform == "android" else None
        self.db = VaultDatabase(get_db_path(data_dir))

        kv_path = Path(__file__).resolve().parent / "ui" / "vault.kv"
        Builder.load_file(str(kv_path))

        sm = MDScreenManager()
        sm.add_widget(AuthScreen())
        sm.add_widget(VaultScreen())
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

    def open_session(self, fernet_key: bytes) -> None:
        self.session_key = fernet_key
        self.root.current = "vault"

    def lock_vault(self) -> None:
        self.session_key = None
        self.root.current = "auth"

    def on_pause(self) -> bool:
        self.lock_vault()
        return True


if __name__ == "__main__":
    PassVaultApp().run()