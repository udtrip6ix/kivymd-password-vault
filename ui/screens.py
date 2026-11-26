from kivy.app import App
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.toast import toast
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField

from core.crypto import CryptoError
from core.database import DatabaseError, VaultEntry
from core.password_tools import PasswordGenConfig, PasswordToolsError, generate_password
from ui.widgets import VaultEntryCard


class AuthScreen(MDScreen):
    is_setup_mode = BooleanProperty(False)
    status_text = StringProperty("")

    def on_pre_enter(self, *args) -> None:
        app = App.get_running_app()
        main_db = app.main_db or app.db
        self.is_setup_mode = not main_db.is_initialized()
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
                target_db = app.main_db or app.db
                key = target_db.initialize_vault(password)
                is_decoy = False
            except (DatabaseError, CryptoError) as exc:
                self.status_text = str(exc)
                return
        else:
            try:
                target_db, key, is_decoy = app.authenticate_vault(password)
            except (DatabaseError, CryptoError) as exc:
                self.status_text = str(exc)
                return

        self.ids.password_field.text = ""
        if "confirm_field" in self.ids:
            self.ids.confirm_field.text = ""
        self.status_text = ""
        app.open_session(target_db, key, is_decoy)


class VaultScreen(MDScreen):
    search_query = StringProperty("")
    entries_count = NumericProperty(0)
    empty_text = StringProperty("Записей пока нет. Нажмите + чтобы добавить.")
    _all_entries: list[VaultEntry] = []
    _decoy_dialog: MDDialog | None = None
    _main_pwd_input: MDTextField | None = None
    _decoy_pwd_input: MDTextField | None = None

    def on_pre_enter(self, *args) -> None:
        self.refresh_entries()

    def lock_now(self) -> None:
        App.get_running_app().lock_vault()

    def open_decoy_setup(self) -> None:
        app = App.get_running_app()
        if app.is_decoy_mode:
            return

        if self._decoy_dialog is None:
            content = MDBoxLayout(
                orientation="vertical",
                spacing="12dp",
                size_hint_y=None,
                height="130dp",
            )
            self._main_pwd_input = MDTextField(
                hint_text="Текущий основной мастер-пароль",
                password=True,
                mode="rectangle",
            )
            self._decoy_pwd_input = MDTextField(
                hint_text="Пароль decoy-хранилища (мин. 8 симв.)",
                password=True,
                mode="rectangle",
            )
            content.add_widget(self._main_pwd_input)
            content.add_widget(self._decoy_pwd_input)

            self._decoy_dialog = MDDialog(
                title="Резервное (decoy) хранилище",
                type="custom",
                content_cls=content,
                buttons=[
                    MDFlatButton(
                        text="ОТМЕНА",
                        on_release=lambda _btn: self._decoy_dialog.dismiss(),
                    ),
                    MDRaisedButton(
                        text="СОХРАНИТЬ",
                        on_release=lambda _btn: self._save_decoy_setup(),
                    ),
                ],
            )

        if self._main_pwd_input is not None:
            self._main_pwd_input.text = ""
        if self._decoy_pwd_input is not None:
            self._decoy_pwd_input.text = ""
        self._decoy_dialog.open()

    def _save_decoy_setup(self) -> None:
        app = App.get_running_app()
        main_pwd = (self._main_pwd_input.text if self._main_pwd_input else "").strip()
        decoy_pwd = (self._decoy_pwd_input.text if self._decoy_pwd_input else "").strip()

        if len(decoy_pwd) < 8:
            toast("Пароль decoy-хранилища должен быть не короче 8 символов")
            return

        try:
            app.configure_decoy_vault(decoy_pwd, main_pwd)
        except (DatabaseError, CryptoError) as exc:
            toast(str(exc))
            return

        if self._decoy_dialog:
            self._decoy_dialog.dismiss()
        toast("Decoy-хранилище настроено")

    def refresh_entries(self) -> None:
        app = App.get_running_app()
        if not app.db or not app.session_key:
            self._all_entries = []
            self._render_list([])
            return
        try:
            self._all_entries = app.db.list_entries(app.session_key)
        except (DatabaseError, CryptoError):
            self._all_entries = []
        self._apply_filter()

    def on_search_change(self, query: str) -> None:
        self.search_query = query.strip().lower()
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self.search_query:
            filtered = self._all_entries
            self.empty_text = "Записей пока нет. Нажмите + чтобы добавить."
        else:
            filtered = [
                e
                for e in self._all_entries
                if self.search_query in e.title.lower()
                or self.search_query in e.username.lower()
                or self.search_query in e.category.lower()
            ]
            self.empty_text = "Ничего не найдено."
        self.entries_count = len(filtered)
        self._render_list(filtered)

    def _render_list(self, entries: list[VaultEntry]) -> None:
        container = self.ids.entries_list
        container.clear_widgets()
        for entry in entries:
            card = VaultEntryCard(
                entry=entry,
                on_open=self.open_edit_entry,
                on_copy=self.copy_entry_secret,
            )
            container.add_widget(card)

    def copy_entry_secret(self, entry: VaultEntry) -> None:
        App.get_running_app().copy_secret_to_clipboard(entry.secret, entry.title)

    def open_new_entry(self) -> None:
        screen = self.manager.get_screen("entry_edit")
        screen.load_entry(None)
        self.manager.current = "entry_edit"

    def open_edit_entry(self, entry: VaultEntry) -> None:
        screen = self.manager.get_screen("entry_edit")
        screen.load_entry(entry)
        self.manager.current = "entry_edit"


class EntryEditScreen(MDScreen):
    editing_entry_id = NumericProperty(0)
    is_editing = BooleanProperty(False)
    is_favorite = BooleanProperty(False)
    show_password = BooleanProperty(False)
    status_text = StringProperty("")
    _delete_dialog: MDDialog | None = None

    def load_entry(self, entry: VaultEntry | None) -> None:
        self.status_text = ""
        self.show_password = False
        if entry is None:
            self.editing_entry_id = 0
            self.is_editing = False
            self.is_favorite = False
            self.ids.title_field.text = ""
            self.ids.username_field.text = ""
            self.ids.secret_field.text = ""
            self.ids.category_field.text = ""
            self.ids.note_field.text = ""
        else:
            self.editing_entry_id = entry.id
            self.is_editing = True
            self.is_favorite = entry.is_favorite
            self.ids.title_field.text = entry.title
            self.ids.username_field.text = entry.username
            self.ids.secret_field.text = entry.secret
            self.ids.category_field.text = entry.category
            self.ids.note_field.text = entry.note

    def toggle_password_visibility(self) -> None:
        self.show_password = not self.show_password

    def toggle_favorite(self) -> None:
        self.is_favorite = not self.is_favorite

    def generate_new_password(self) -> None:
        try:
            pwd = generate_password(PasswordGenConfig(length=16, exclude_ambiguous=True))
        except PasswordToolsError as exc:
            self.status_text = str(exc)
            return
        self.ids.secret_field.text = pwd
        self.show_password = True
        self.status_text = ""

    def save_entry(self) -> None:
        app = App.get_running_app()
        if not app.db or not app.session_key:
            self.status_text = "Сессия не активна."
            return

        title = self.ids.title_field.text.strip()
        username = self.ids.username_field.text.strip()
        secret = self.ids.secret_field.text
        category = self.ids.category_field.text.strip()
        note = self.ids.note_field.text.strip()

        if not title:
            self.status_text = "Укажите название записи."
            return
        if not secret:
            self.status_text = "Введите или сгенерируйте пароль."
            return

        try:
            if self.is_editing and self.editing_entry_id:
                app.db.update_entry(
                    entry_id=int(self.editing_entry_id),
                    fernet_key=app.session_key,
                    title=title,
                    secret=secret,
                    username=username,
                    category=category,
                    note=note,
                    is_favorite=self.is_favorite,
                )
            else:
                app.db.add_entry(
                    fernet_key=app.session_key,
                    title=title,
                    secret=secret,
                    username=username,
                    category=category,
                    note=note,
                    is_favorite=self.is_favorite,
                )
        except (DatabaseError, CryptoError) as exc:
            self.status_text = str(exc)
            return

        self.manager.current = "vault"

    def confirm_delete(self) -> None:
        if not self.is_editing or not self.editing_entry_id:
            return
        if self._delete_dialog is None:
            self._delete_dialog = MDDialog(
                text="Удалить эту запись без возможности восстановления?",
                buttons=[
                    MDFlatButton(
                        text="ОТМЕНА",
                        on_release=lambda _btn: self._delete_dialog.dismiss(),
                    ),
                    MDRaisedButton(
                        text="УДАЛИТЬ",
                        on_release=lambda _btn: self._perform_delete(),
                    ),
                ],
            )
        self._delete_dialog.open()

    def _perform_delete(self) -> None:
        app = App.get_running_app()
        if self._delete_dialog:
            self._delete_dialog.dismiss()
        if app.db and self.editing_entry_id:
            app.db.delete_entry(int(self.editing_entry_id))
        self.manager.current = "vault"

    def cancel(self) -> None:
        self.manager.current = "vault"