import os
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

from jnius import autoclass

MediaRecorder = autoclass('android.media.MediaRecorder')
MediaPlayer = autoclass('android.media.MediaPlayer')
Environment = autoclass('android.os.Environment')

AUDIO_SOURCES = {
    'mic': MediaRecorder.AudioSource.MIC,
}
OUTPUT_FORMATS = {
    'm4a': MediaRecorder.OutputFormat.MPEG_4,
}
ENCODERS = {
    'm4a': MediaRecorder.AudioEncoder.AAC,
}


class DictophoneApp(App):
    title = 'Диктофон с заметками'

    def build(self):
        # Папка, которую видно в настройках приложения
        self.audio_dir = os.path.join(self.user_data_dir, 'recordings')
        os.makedirs(self.audio_dir, exist_ok=True)

        self.recorder = None
        self.player = None
        self.current_file = None
        self.recording = False

        root = BoxLayout(orientation='vertical', padding=10, spacing=10)

        self.status = Label(
            text='Готов к записи',
            size_hint=(1, None), height=30,
            color=(0.1, 0.1, 0.1, 1))
        root.add_widget(self.status)

        self.rec_btn = Button(
            text='НАЧАТЬ ЗАПИСЬ',
            size_hint=(1, None), height=60,
            background_color=(0.35, 0.05, 0.05, 1))
        self.rec_btn.bind(on_press=self.toggle_record)
        root.add_widget(self.rec_btn)

        self.note_input = TextInput(
            hint_text='Текст заметки (можно оставить пустым)',
            size_hint=(1, None), height=50,
            multiline=False)
        root.add_widget(self.note_input)

        self.path_label = Label(
            text='Папка записей:\n' + self.audio_dir,
            size_hint=(1, None), height=60,
            color=(0.2, 0.2, 0.2, 1),
            halign='left')
        self.path_label.bind(size=lambda w, s: setattr(w.texture_size, 'x', s[0]))
        root.add_widget(self.path_label)

        self.list_scroll = ScrollView()
        self.list_box = BoxLayout(
            orientation='vertical', spacing=6, size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)

        self.refresh_list()
        return root

    def toggle_record(self, *args):
        if not self.recording:
            self.start_record()
        else:
            self.stop_record()

    def start_record(self):
        try:
            self.current_file = os.path.join(
                self.audio_dir,
                datetime.now().strftime('rec_%Y%m%d_%H%M%S.m4a'))
            r = MediaRecorder()
            r.setAudioSource(AUDIO_SOURCES['mic'])
            r.setOutputFormat(OUTPUT_FORMATS['m4a'])
            r.setAudioEncoder(ENCODERS['m4a'])
            r.setOutputFile(self.current_file)
            r.prepare()
            r.start()
            self.recorder = r
            self.recording = True
            self.rec_btn.text = 'ОСТАНОВИТЬ И СОХРАНИТЬ'
            self.status.text = 'Идёт запись…'
        except Exception as e:
            self.status.text = 'Ошибка запуска записи: %s' % e

    def stop_record(self):
        note = self.note_input.text.strip()
        try:
            self.recorder.stop()
            self.recorder.release()
        except Exception:
            pass
        self.recorder = None
        self.recording = False
        self.rec_btn.text = 'НАЧАТЬ ЗАПИСЬ'

        # Заметка хранится рядом с файлом: тот же путь + .txt
        if note:
            with open(self.current_file + '.txt', 'w', encoding='utf-8') as f:
                f.write(note)
        self.note_input.text = ''
        self.status.text = 'Сохранено:\n' + os.path.basename(self.current_file)
        self.refresh_list()

    def refresh_list(self):
        self.list_box.clear_widgets()
        for name in sorted(os.listdir(self.audio_dir), reverse=True):
            if not name.endswith('.m4a'):
                continue
            stamp = name.replace('rec_', '').replace('.m4a', '')
            txt_path = os.path.join(self.audio_dir, name + '.txt')
            note = ''
            if os.path.exists(txt_path):
                with open(txt_path, encoding='utf-8') as f:
                    note = f.read().strip()
            pretty = datetime.strptime(stamp, '%Y%m%d_%H%M%S')
            label = pretty.strftime('%d.%m.%Y %H:%M') + \
                ('  ' + note if note else '  (без текста)')
            btn = Button(
                text=label,
                size_hint=(1, None), height=50,
                background_color=(0.85, 0.85, 0.85, 1),
                color=(0.1, 0.1, 0.1, 1))
            btn.bind(on_press=lambda inst, fn=name: self.play(fn))
            self.list_box.add_widget(btn)

    def play(self, filename):
        if self.player:
            try:
                self.player.release()
            except Exception:
                pass
        path = os.path.join(self.audio_dir, filename)
        self.player = MediaPlayer()
        self.player.setDataSource(path)
        self.player.prepare()
        self.player.start()
        self.status.text = 'Проигрываю: ' + filename

    def on_stop(self):
        if self.recorder:
            try:
                self.recorder.stop()
                self.recorder.release()
            except Exception:
                pass
        if self.player:
            try:
                self.player.release()
            except Exception:
                pass


if __name__ == '__main__':
    DictophoneApp().run()
