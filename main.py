from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock
import os
import json
import time

# --- ANDROID IMPORTS (Только то, что реально нужно) ---
try:
    from jnius import autoclass
    from android.permissions import request_permissions, Permission
    
    MediaRecorder = autoclass('android.media.MediaRecorder')
    MediaRecorder_OutputFormat = autoclass('android.media.MediaRecorder\$OutputFormat')
    MediaRecorder_AudioSource = autoclass('android.media.MediaRecorder\$AudioSource')
    MediaRecorder_AudioEncoder = autoclass('android.media.MediaRecorder\$AudioEncoder')
    Environment = autoclass('android.os.Environment')
    File = autoclass('java.io.File')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    
    ANDROID = True
except ImportError:
    ANDROID = False
    print("Running on Desktop")

# --- КОНФИГУРАЦИЯ ---
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
        self.size_hint_y = None
        self.height = 80
        
        # Левая часть: Дата и текст (60%)
        left_box = BoxLayout(orientation='vertical', size_hint=(0.6, 1))
        self.lbl_date = Label(text=data.get('date', ''), color=(0, 0, 0, 1), font_size=14, halign='left', valign='top')
        self.lbl_text = Label(text=data.get('text', 'Без текста'), color=(0, 0, 0, 1), font_size=16, halign='left', valign='top', size_hint_y=None, height=40)
        self.lbl_text.bind(texture_size=self.lbl_text.setter('size'))
        left_box.add_widget(self.lbl_date)
        left_box.add_widget(self.lbl_text)
        self.add_widget(left_box)
        
        # Правая часть: Кнопки (40%)
        right_box = BoxLayout(orientation='vertical', size_hint=(0.4, 1), spacing=5)
        
        btn_play = Button(text="▶ Воспроизвести", size_hint=(1, 0.5), background_color=(0.2, 0.6, 0.2, 1), font_size=14)
        btn_play.bind(on_press=lambda x: self.on_play(data))
        
        btn_share = Button(text="↗ Поделиться", size_hint=(1, 0.5), background_color=(0.2, 0.4, 0.8, 1), font_size=14)
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
        
        # Статус бар
        self.lbl_status = Label(text=self.status_text, size_hint=(1, 0.05), 
                                color=(0.8, 0, 0, 1), font_size=14, halign='center')
        self.lbl_status.bind(size=self.lbl_status.setter('text_size'))
        root.add_widget(self.lbl_status)
        
        # Кнопка записи
        self.btn_record = Button(text="НАЧАТЬ ЗАПИСЬ", size_hint=(1, 0.15), 
                                 font_size=20, bold=True, background_color=(0.8, 0.2, 0.2, 1))
        self.btn_record.bind(on_press=self.toggle_recording)
        root.add_widget(self.btn_record)
        
        # Путь к файлам
        path_label = Label(text=f"Записи: Music/{RECORD_FOLDER_NAME}", 
                           size_hint=(1, 0.05), color=(0.3, 0.3, 0.3, 1), font_size=12)
        root.add_widget(path_label)
        
        # Поле заметки
        self.txt_note = TextInput(hint_text="Текст заметки", size_hint=(1, 0.08), multiline=True)
        root.add_widget(self.txt_note)
        
        # Поиск
        self.txt_search = TextInput(hint_text="Поиск по заметкам", size_hint=(1, 0.08), multiline=False)
        self.txt_search.bind(text=self.filter_notes)
        root.add_widget(self.txt_search)
        
        # Список заметок
        self.list_container = BoxLayout(orientation='vertical', size_hint=(1, 0.5), padding=0)
        self.scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.scroll.add_widget(self.list_container)
        root.add_widget(self.scroll)
        
        self.refresh_notes_ui()
        
        if ANDROID:
            request_permissions([Permission.RECORD_AUDIO, Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
            
        return root

    def toggle_recording(self, instance):
        if not ANDROID:
            self.set_status("Ошибка: Запуск только на Android")
            return

        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        try:
            self.is_recording = True
            self.btn_record.text = "ОСТАНОВИТЬ ЗАПИСЬ"
            self.btn_record.background_color = (0.8, 0.5, 0.2, 1)
            self.set_status("Идёт запись...")
            
            # 1. Получаем путь к папке Music/Sputnik
            external_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
            target_folder = File(external_dir, RECORD_FOLDER_NAME)
            if not target_folder.exists():
                target_folder.mkdirs()
            
            filename = f"rec_{int(time.time())}.m4a"
            self.output_file = File(target_folder, filename)
            
            # 2. Инициализируем MediaRecorder
            self.recorder = MediaRecorder()
            self.recorder.setAudioSource(MediaRecorder_AudioSource.MIC)
            self.recorder.setOutputFormat(MediaRecorder_OutputFormat.MPEG_4)
            self.recorder.setAudioEncoder(MediaRecorder_AudioEncoder.AAC)
            self.recorder.setOutputFile(self.output_file.getAbsolutePath())
            self.recorder.prepare()
            self.recorder.start()
            
        except Exception as e:
            self.is_recording = False
            self.reset_button_state()
            self.set_status(f"Ошибка записи: {str(e)}")

    def stop_recording(self):
        try:
            if self.recorder:
                self.recorder.stop()
                self.recorder.release()
                self.recorder = None
            
            # Сохраняем заметку
            note_text = self.txt_note.text.strip()
            current_time = time.strftime("%d.%m.%Y %H:%M")
            
            new_note = {
                "text": note_text if note_text else "(без текста)",
                "date": current_time,
                "file_path": self.output_file.getAbsolutePath() if self.output_file else ""
            }
            self.notes.append(new_note)
            self.save_notes()
            
            self.is_recording = False
            self.reset_button_state()
            self.txt_note.text = ""
            self.set_status("Запись сохранена в Music/Sputnik")
            self.refresh_notes_ui()
            
        except Exception as e:
            self.is_recording = False
            self.reset_button_state()
            self.set_status(f"Ошибка сохранения: {str(e)}")

    def reset_button_state(self):
        self.btn_record.text = "НАЧАТЬ ЗАПИСЬ"
        self.btn_record.background_color = (0.8, 0.2, 0.2, 1)

    def load_notes(self):
        try:
            app_path = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
            path = os.path.join(app_path, NOTES_FILE)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    self.notes = json.load(f)
        except:
            self.notes = 

    def save_notes(self):
        try:
            app_path = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
            path = os.path.join(app_path, NOTES_FILE)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save error: {e}")

    def refresh_notes_ui(self):
        self.list_container.clear_widgets()
        
        if not self.notes:
            lbl = Label(text="Заметок пока нет — нажмите красную кнопку", color=(0.5, 0.5, 0.5, 1), size_hint_y=None, height=40)
            self.list_container.add_widget(lbl)
            return

        for note in self.notes:
            item = NoteItem(note, self.play_audio, self.share_audio)
            self.list_container.add_widget(item)

    def filter_notes(self, instance, value):
        # Упрощенная фильтрация (можно доработать)
        self.refresh_notes_ui()

    def play_audio(self, note):
        self.set_status("Для воспроизведения откройте файл в плеере")

    def share_audio(self, note):
        self.set_status("Функция шаринга в разработке")

    def set_status(self, text):
        self.status_text = text
        self.lbl_status.text = text
        print(f"[STATUS] {text}")

if __name__ == '__main__':
    DictaphoneApp().run()
