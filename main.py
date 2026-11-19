from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
import os
import json
import time

# --- ANDROID IMPORTS (Критически важно для MediaRecorder) ---
try:
    from jnius import autoclass, cast
    from android.permissions import request_permissions, Permission
    
    MediaRecorder = autoclass('android.media.MediaRecorder')
    MediaRecorder_OutputFormat = autoclass('android.media.MediaRecorder\$OutputFormat')
    MediaRecorder_AudioSource = autoclass('android.media.MediaRecorder\$AudioSource')
    MediaRecorder_AudioEncoder = autoclass('android.media.MediaRecorder\$AudioEncoder')
    Environment = autoclass('android.os.Environment')
    File = autoclass('java.io.File')
    ContentValues = autoclass('android.content.ContentValues')
    MediaStore_Audio_Media = autoclass('android.provider.MediaStore$Audio$Media')
    Uri = autoclass('android.net.Uri')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    
    ANDROID = True
except ImportError:
    ANDROID = False
    MediaRecorder = None
    print("Running on Desktop (no MediaRecorder)")

# --- КОНФИГУРАЦИЯ ---
APP_NAME = "Диктофон с заметками"
RECORD_FOLDER_NAME = "Sputnik"
BASE_FOLDER = "Music"
NOTES_FILE = "notes.json"

class NoteItem(BoxLayout):
    def __init__(self, data, on_play, on_share, **kwargs):
        super().__init__(**kwargs)
        self.data = data
        self.on_play = on_play
        self.on_share = on_share
        self.orientation = 'horizontal'
        self.padding = 10
        self.spacing = 10
        
        # Левая часть: Дата и текст
        left_box = BoxLayout(orientation='vertical', size_hint=(0.6, 1))
        self.lbl_date = Label(text=data.get('date', ''), color=(0, 0, 0, 1), font_size=14, halign='left')
        self.lbl_text = Label(text=data.get('text', 'Без заметки'), color=(0, 0, 0, 1), font_size=16, halign='left', size_hint_y=None, height=40)
        self.lbl_text.bind(texture_size=self.lbl_text.setter('size'))
        left_box.add_widget(self.lbl_date)
        left_box.add_widget(self.lbl_text)
        self.add_widget(left_box)
        
        # Правая часть: Кнопки (фиксированная ширина)
        right_box = BoxLayout(orientation='vertical', size_hint=(0.4, 1), spacing=5)
        
        btn_play = Button(text="▶ Воспроизвести", size_hint=(1, 0.5), background_color=(0.2, 0.6, 0.2, 1))
        btn_play.bind(on_press=lambda x: self.on_play(data))
        
        btn_share = Button(text="↗ Поделиться", size_hint=(1, 0.5), background_color=(0.2, 0.4, 0.8, 1))
        btn_share.bind(on_press=lambda x: self.on_share(data))
        
        right_box.add_widget(btn_play)
        right_box.add_widget(btn_share)
        self.add_widget(right_box)

class DictaphoneApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_recording = False
        self.recorder = None
        self.output_file = None
        self.temp_file = None
        self.notes = 
        self.load_notes()
        self.status_text = "Готов к работе"

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        root = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Шапка
        header = Label(text="ДИКТОФОН С ЗАМЕТКАМИ", size_hint=(1, 0.1), 
                       color=(1, 1, 1, 1), font_size=24, bold=True, 
                       background_color=(0, 0.4, 0.7, 1))
        header.bind(size=header.setter('text_size'))
        root.add_widget(header)
        
        # Статус бар (сюда будут падать ошибки типа MediaRecorder)
        self.lbl_status
