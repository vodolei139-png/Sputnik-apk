import os
import json
import datetime

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

try:
    from jnius import autoclass
    MediaRecorder = autoclass('android.media.MediaRecorder')
    MediaPlayer = autoclass('android.media.MediaPlayer')
    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False  # запуск на ПК: интерфейс виден, запись отключена


NOTES_FILE = 'notes.json'


class DiktofonApp(App):

    def build(self):
        Window.clearcolor = (0.96, 0.96, 0.97, 1)
        layout = BoxLayout(orientation='vertical', padding=12, spacing=10)

        title = Label(text='Диктофон с заметками', size_hint_y=None, height=36,
                      bold=True, color=(0.15, 0.15, 0.2, 1), font_size='20sp')
        layout.add_widget(title)

        self.status = Label(text='Готов к записи', size_hint_y=None, height=28,
                            color=(0.3, 0.3, 0.35, 1))
        layout.add_widget(self.status)

        self.btn_rec = Button(text='● НАЧАТЬ ЗАПИСЬ', size_hint_y=None, height=64,
                              background_color=(0.65, 0.18, 0.18, 1), font_size='18sp')
        self.btn_rec.bind(on_press=self.toggle_record)
        layout.add_widget(self.btn_rec)

        self.path_label = Label(text='', size_hint_y=None, height=22,
                                color=(0.45, 0.45, 0.5, 1), font_size='11sp')
        if ON_ANDROID:
            self.path_label.text = 'Записи: %s' % self.user_data_dir
        layout.add_widget(self.path_label)

        self.inp_note = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                                  size_hint_y=None, height=70, multiline=True)
        layout.add_widget(self.inp_note)

        self.inp_search = TextInput(hint_text='Поиск по заметкам', size_hint_y=None,
                                    height=44, multiline=False)
        self.inp_search.bind(text=lambda *a: self.refresh_list())
        layout.add_widget(self.inp_search)

        self.list_box = GridLayout(cols=1, size_hint_y=None, spacing=8)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        scroll = ScrollView(bar_width=6)
        scroll.add_widget(self.list_box)
        layout.add_widget(scroll)

        self.recorder = None
        self.player = None
        self.audio_path = None
        self.notes = self.load_notes()
        self.refresh_list()
        return layout

    # ---------- запись ----------

    def toggle_record(self, *args):
        if not ON_ANDROID:
            self.status.text = 'Запись работает только на Android'
            return
        if self.recorder is None:
            self.start_record()
        else:
            self.stop_record()

    def start_record(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.audio_path = os.path.join(self.user_data_dir, 'rec_%s.m4a' % ts)
        rec = MediaRecorder()
        rec.setAudioSource(6)   # AudioSource.MIC
        rec.setOutputFormat(2)  # MPEG_4
        rec.setAudioEncoder(3)  # AAC
        rec.setOutputFile(self.audio_path)
        rec.prepare()
        rec.start()
        self.recorder = rec
        self.btn_rec.text = '■ ОСТАНОВИТЬ'
        self.btn_rec.background_color = (0.2, 0.45, 0.2, 1)
        self.status.text = 'Идёт запись… говорите!'

    def stop_record(self):
        try:
            self.recorder.stop()
        finally:
            self.recorder.release()
            self.recorder = None
        self.btn_rec.text = '● НАЧАТЬ ЗАПИСЬ'
        self.btn_rec.background_color = (0.65, 0.18, 0.18, 1)
        fname = os.path.basename(self.audio_path)
        self.add_note(text=self.inp_note.text.strip(),
                      audio=fname)
        self.inp_note.text = ''
        self.status.text = 'Запись сохранена: %s' % fname

    # ---------- проигрывание ----------

    def play_note(self, note, *args):
        if not ON_ANDROID or not note.get('audio'):
            return
        if self.player is not None:
            try:
                self.player.release()
            except Exception:
                pass
        self.player = MediaPlayer()
        self.player.setDataSource(os.path.join(self.user_data_dir, note['audio']))
        self.player.prepare()
        self.player.start()
        self.status.text = 'Проигрываю: %s' % note['audio']

    # ---------- заметки ----------

    def notes_file(self):
        return os.path.join(self.user_data_dir, NOTES_FILE)

    def load_notes(self):
        try:
            with open(self.notes_file(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_notes(self):
        with open(self.notes_file(), 'w', encoding='utf-8') as f:
            json.dump(self.notes, f, ensure_ascii=False, indent=1)

    def add_note(self, text, audio):
        self.notes.insert(0, {
            'date': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
            'text': text or '(без текста)',
            'audio': audio,
        })
        self.save_notes()
        self.refresh_list()

    def refresh_list(self):
        query = self.inp_search.text.strip().lower() if hasattr(self, 'inp_search') else ''
        self.list_box.clear_widgets()
        for note in self.notes:
            if query and query not in note['text'].lower():
                continue
            text = note['text'] if len(note['text']) <= 80 else note['text'][:80] + '…'
            btn = Button(text='%s\n%s' % (note['date'], text),
                         size_hint_y=None, height=80,
                         halign='left', valign='middle',
                         background_color=(1, 1, 1, 1),
                         color=(0.1, 0.1, 0.15, 1))
            btn.bind(size=lambda w, s: setattr(w, 'text_size', s))
            btn.bind(on_press=lambda inst, n=note: self.play_note(n))
            self.list_box.add_widget(btn)
        if not self.list_box.children:
            self.list_box.add_widget(Label(text='Заметок пока нет — запишите первую!',
                                           size_hint_y=None, height=60,
                                           color=(0.5, 0.5, 0.55, 1)))

    def on_stop(self):
        if self.recorder is not None:
            try:
                self.recorder.stop()
            except Exception:
                pass
            self.recorder.release()
            self.recorder = None
        if self.player is not None:
            try:
                self.player.release()
            except Exception:
                pass
            self.player = None

    def on_start(self):
        if ON_ANDROID:
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.RECORD_AUDIO])
            except Exception:
                pass


if __name__ == '__main__':
    DiktofonApp().run()
