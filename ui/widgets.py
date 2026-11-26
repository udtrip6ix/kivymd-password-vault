from kivy.app import App
from kivy.metrics import dp, sp
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel

from core.database import VaultEntry


class VaultEntryCard(MDCard):
    entry = ObjectProperty(None)
    title_text = StringProperty("")
    subtitle_text = StringProperty("")
    category_text = StringProperty("")

    def __init__(self, entry: VaultEntry, on_open, on_copy, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entry = entry
        self._on_open = on_open
        self._on_copy = on_copy

        app = App.get_running_app()
        scale = app.ui_scale if app else 1.0

        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(68 * scale)
        self.padding = [dp(12 * scale), dp(8 * scale)]
        self.spacing = dp(8 * scale)
        self.radius = [dp(12 * scale)]
        self.elevation = 1
        self.ripple_behavior = True

        self.title_text = entry.title
        user_part = entry.username or "без логина"
        cat_part = entry.category or "Общее"
        self.subtitle_text = f"{user_part} • {cat_part}"
        self.category_text = cat_part

        info_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2 * scale),
            size_hint_x=1,
            pos_hint={"center_y": 0.5},
        )
        title_lbl = MDLabel(
            text=self.title_text,
            font_style="Subtitle1",
            font_size=sp(15 * scale),
            bold=True,
            shorten=True,
            shorten_from="right",
            adaptive_height=True,
        )
        sub_lbl = MDLabel(
            text=self.subtitle_text,
            font_style="Caption",
            font_size=sp(12 * scale),
            theme_text_color="Secondary",
            shorten=True,
            shorten_from="right",
            adaptive_height=True,
        )
        info_box.add_widget(title_lbl)
        info_box.add_widget(sub_lbl)

        copy_btn = MDIconButton(
            icon="content-copy",
            pos_hint={"center_y": 0.5},
            on_release=lambda _btn: self._on_copy(self.entry),
        )

        self.add_widget(info_box)
        self.add_widget(copy_btn)

    def on_release(self) -> None:
        if self._on_open and self.entry is not None:
            self._on_open(self.entry)