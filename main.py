# -*- coding: utf-8 -*-
"""Диктофон с заметками — «Спутник».
Записи сохраняются в общедоступную папку Music/Sputnik (MediaStore),
у заметок кнопки воспроизведения и «Поделиться».
Все опасные вызовы обёрнуты в защиту: приложение не падает при старте.
"""

import os
import json
import datetime
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.utils import platform

Window.clearcolor = (1, 1, 1, 1)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_JSON = os.path.join(APP_DIR, 'notes.json')

ANDROID = (platform == 'android')

if ANDROID:
    try:
        from jnius import autoclass, PythonJavaClass, java_method
        from android.permissions import request_permissions, check_permission
        Environment = autoclass('android.os.Environment')
        MediaStore = autoclass('android.provider.MediaStore')
        ContentValues = autoclass('android.content.ContentValues')
        Intent = autoclass('android.content.Intent')
        mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
        ContentUris = autoclass('android.content.ContentUris')
        Uri = autoclass('android.net.Uri')
        FileProvider = autoclass('android.support.v4.content.FileProvider')
        MediaPlayer = autoclass('android.media.MediaPlayer')
        MediaRecorder = autoclass('android.media.MediaRecorder')
    except Exception:
        traceback.print_exc()
        ANDROID = False
else:
    class MediaPlayer(object):
        pass
    class MediaRecorder(object):
        pass


def _toast(msg):
    try:
        if ANDROID:
            Toast = autoclass('android.widget.Toast')
            Toast.makeText(mActivity, str(msg), Toast.LENGTH_SHORT).show()
    except Exception:
        traceback.print_exc()


def get_music_sputnik_dir():
    """Путь к общедоступной папке Music/Sputnik (или None)."""
    if not ANDROID:
        d = os.path.join(APP_DIR, 'recordings')
        os.makedirs(d, exist_ok=True)
        return d
    try:
        music_dir = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_MUSIC)
        d = os.path.join(str(music_dir), 'Sputnik')
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        traceback.print_exc()
        return None


def request_perms():
    try:
        if ANDROID:
            request_permissions([
                'android.permission.RECORD_AUDIO',
                'android.permission.WRITE_EXTERNAL_STORAGE',
                'android.permission.READ_EXTERNAL_STORAGE',
            ])
    except Exception:
        traceback.print_exc()


def save_to_mediastore(src_path, display_name):
    """Копирует файл в Music/Sputnik через MediaStore (Android 10+).
    Возвращает (успех, сообщение)."""
    try:
        if not ANDROID:
            return True, src_path
        values = ContentValues()
        values.put(MediaStore.Audio.Media.DISPLAY_NAME, display_name)
        values.put(MediaStore.Audio.Media.MIME_TYPE, 'audio/mp4')
        values.put(MediaStore.Audio.Media.RELATIVE_PATH, 'Music/Sputnik')
        resolver = mActivity.getContentResolver()
        uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)
        if uri is None:
            return False, 'MediaStore вернул null'
        out = resolver.openOutputStream(uri)
        with open(src_path, 'rb') as f:
            out.write(f.read())
        out.close()
        os.remove(src_path)
        return True, str(uri)
    except Exception as e:
        traceback.print_exc()
        return False, str(e)


def get_uri_for_share(path):
    """URI для системного «Поделиться»."""
    try:
        if not ANDROID:
            return None
        from jnius import autoclass as _ac
        JFile = _ac('java.io.File')
        try:
            Provider = _ac('androidx.core.content.FileProvider')
            return Provider.getUriForFile(
                mActivity, mActivity.getPackageName() + '.provider', JFile(path))
        except Exception:
            Provider = _ac('android.support.v4.content.FileProvider')
            return Provider.getUriForFile(
                mActivity, mActivity.getPackageName() + '.provider', JFile(path))
    except Exception:
        traceback.print_exc()
        return None


class NoteRow(GridLayout):
    def __init__(self, app, note, **kw):
        super(NoteRow, self).__init__(cols=3, size_hint_y=None, height='44dp',
                                      spacing='4dp', padding='4dp', **kw)
        self.app = app
        self.note = note
        colors = [(1, 0.97, 0.7, 1), (0.75, 0.94, 0.94, 1), (1, 0.85, 0.8, 1)]
        bg = colors[len(app.notes) % len(colors)]

        lbl = Label(text=note['title'] + '\n' + (note['text'] or '(без текста)'),
                    color=(0, 0, 0, 1), halign='left', valign='middle',
                    size_hint_x=0.62, bold=True)
        lbl.bind(size=lambda inst, s: setattr(inst, 'text_size', s))
        from kivy.graphics import Color, Rectangle
        with lbl.canvas.before:
            Color(*bg)
            Rectangle(pos=lbl.pos, size=lbl.size)
        self.add_widget(lbl)

        play = Button(text='\u25B6', size_hint_x=0.2,
                      background_normal='', background_color=(0.12, 0.39, 0.87, 1))
        play.bind(on_press=lambda *a: self.app.play_note(self.note))
        self.add_widget(play)

        share = Button(text='\u2197', size_hint_x=0.18,
                       background_normal='', background_color=(0.96, 0.5, 0.1, 1))
        share.bind(on_press=lambda *a: self.app.share_note(self.note))
        self.add_widget(share)


class DictApp(App):
    def build(self):
        self.title = 'Спутник'
        self.recorder = None
        self.player = None
        self.recording = False
        self.notes = self.load_notes()

        root = BoxLayout(orientation='vertical', padding='8dp', spacing='8dp')

        header = Label(text='ДИКТОФОН С ЗАМЕТКАМИ', bold=True, color=(1, 1, 1, 1),
                       size_hint_y=None, height='48dp')
        with header.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(0.05, 0.35, 0.75, 1)
            Rectangle(pos=header.pos, size=header.size)
        root.add_widget(header)

        self.status = Label(text='Готов к записи', size_hint_y=None, height='28dp',
                            color=(0.1, 0.1, 0.1, 1))
        root.add_widget(self.status)

        self.btn = Button(text='\u25CF НАЧАТЬ ЗАПИСЬ', bold=True, size_hint_y=None,
                          height='56dp', background_normal='',
                          background_color=(0.9, 0.2, 0.2, 1))
        self.btn.bind(on_press=self.on_record)
        root.add_widget(self.btn)

        self.path_lbl = Label(text='Записи: Music/Sputnik (общедоступная папка)',
                              size_hint_y=None, height='24dp', color=(0.3, 0.3, 0.3, 1))
        root.add_widget(self.path_lbl)

        self.txt = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                             size_hint_y=None, height='44dp',
                             background_color=(0.9, 0.94, 1, 1), multiline=False)
        root.add_widget(self.txt)

        self.search = TextInput(hint_text='Поиск по заметкам', size_hint_y=None,
                                height='44dp', background_color=(0.9, 0.94, 1, 1),
                                multiline=False)
        self.search.bind(text=self.on_search)
        root.add_widget(self.search)

        self.list_scroll = ScrollView()
        self.list_box = GridLayout(cols=1, size_hint_y=None, spacing='6dp')
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)

        self.refresh_list('')
        return root

    # ---------- заметки ----------
    def load_notes(self):
        try:
            if os.path.exists(NOTES_JSON):
                with open(NOTES_JSON, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            traceback.print_exc()
        return []

    def save_notes(self):
        try:
            with open(NOTES_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False)
        except Exception:
            traceback.print_exc()

    def refresh_list(self, flt=''):
        try:
            self.list_box.clear_widgets()
            matched = [n for n in self.notes
                       if flt.lower() in (n['text'] or '').lower()
                       or flt.lower() in n['title'].lower()]
            if not matched:
                empty = Label(text='Заметок пока нет — нажмите красную кнопку',
                              color=(0.2, 0.2, 0.2, 1), size_hint_y=None, height='40dp')
                self.list_box.add_widget(empty)
                return
            for n in matched:
                self.list_box.add_widget(NoteRow(self, n))
        except Exception:
            self.set_status('Ошибка списка: ' + traceback.format_exc(limit=1))

    def on_search(self, inst, value):
        try:
            self.refresh_list(value)
        except Exception:
            traceback.print_exc()

    def set_status(self, msg):
        try:
            self.status.text = msg
        except Exception:
            pass

    # ---------- запись ----------
    def on_record(self, inst):
        try:
            if not self.recording:
                self.start_recording()
            else:
                self.stop_recording()
        except Exception as e:
            self.set_status('Ошибка записи: ' + str(e))
            traceback.print_exc()

    def start_recording(self):
        request_perms()
        d = get_music_sputnik_dir()
        if d is None:
            d = os.path.join(APP_DIR, 'recordings')
            os.makedirs(d, exist_ok=True)
        fname = 'rec_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.m4a'
        self.tmp_path = os.path.join(APP_DIR, fname)
        self.fname = fname
        try:
            r = MediaRecorder()
            r.setAudioSource(6)  # MIC = 6 в API через pyjnius
            r.setOutputFormat(2)  # MPEG_4
            r.setAudioEncoder(3)  # AAC
            r.setAudioEncodingBitRate(128000)
            r.setAudioSamplingRate(44100)
            r.setOutputFile(self.tmp_path)
            r.prepare()
            r.start()
            self.recorder = r
            self.recording = True
            self.btn.text = '\u25A0 ОСТАНОВИТЬ'
            self.btn.background_color = (0.1, 0.65, 0.25, 1)
            self.set_status('Идёт запись…')
        except Exception as e:
            self.set_status('Причина: ' + str(e))
            traceback.print_exc()

    def stop_recording(self):
        try:
            if self.recorder:
                self.recorder.stop()
                self.recorder.release()
                self.recorder = None
            self.recording = False
            self.btn.text = '\u25CF НАЧАТЬ ЗАПИСЬ'
            self.btn.background_color = (0.9, 0.2, 0.2, 1)

            now = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
            note = {
                'title': now,
                'text': self.txt.text.strip(),
                'file': self.fname,
                'dir': get_music_sputnik_dir() or APP_DIR,
            }
            ok, msg = save_to_mediastore(self.tmp_path, self.fname)
            if ok:
                note['dir'] = str(get_music_sputnik_dir() or APP_DIR)
                self.set_status('Запись сохранена (Music/Sputnik)')
            else:
                note['dir'] = APP_DIR
                self.set_status('Запись сохранена (папка приложения). Причина: ' + msg)
            self.notes.insert(0, note)
            self.save_notes()
            self.txt.text = ''
            self.refresh_list(self.search.text)
        except Exception as e:
            self.set_status('Ошибка сохранения: ' + str(e))
            traceback.print_exc()

    # ---------- воспроизведение и поделиться ----------
    def play_note(self, note):
        try:
            if self.player:
                try:
                    self.player.release()
                except Exception:
                    pass
                self.player = None
            path = os.path.join(str(note.get('dir') or ''), note['file'])
            if not os.path.exists(path):
                self.set_status('Файл не найден: ' + path)
                return
            p = MediaPlayer()
            p.setDataSource(path)
            p.prepare()
            p.start()
            self.player = p
            self.set_status('Воспроизведение: ' + note['title'])
        except Exception as e:
            self.set_status('Ошибка воспроизведения: ' + str(e))
            traceback.print_exc()

    def share_note(self, note):
        try:
            if not ANDROID:
                self.set_status('Поделиться доступно на Android')
                return
            path = os.path.join(str(note.get('dir') or ''), note['file'])
            if not os.path.exists(path):
                self.set_status('Файл не найден: ' + path)
                return
            from jnius import autoclass as _ac
            uri = get_uri_for_share(path)
            if uri is None:
                self.set_status('Не удалось получить URI для файла')
                return
            Intent = _ac('android.content.Intent')
            intent = Intent(Intent.ACTION_SEND)
            intent.setType('audio/mp4')
            intent.putExtra(Intent.EXTRA_STREAM, uri)
            intent.addFlags(0x10000000)  # FLAG_GRANT_READ_URI_PERMISSION
            mActivity.startActivity(Intent.createChooser(intent, 'Отправить запись'))
        except Exception as e:
            self.set_status('Ошибка отправки: ' + str(e))
            traceback.print_exc()


if __name__ == '__main__':
    DictApp().run()
