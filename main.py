# -*- coding: utf-8 -*-
"""Sputnik — диктофон с заметками (Python/Kivy).

Записи сохраняются в общедоступную папку Music/Sputnik (MediaStore),
у каждой заметки — кнопки воспроизведения и «Поделиться».
"""
import os
import json
import shutil
from datetime import datetime

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.utils import platform, get_color_from_hex

# ---------------- Палитра (яркая) ----------------
C_BG      = get_color_from_hex('#FFFFFF')   # белый фон
C_HEAD    = get_color_from_hex('#1565C0')   # синяя шапка
C_RED     = get_color_from_hex('#E53935')   # красная запись
C_RED_DK  = get_color_from_hex('#B71C1C')
C_GREEN   = get_color_from_hex('#43A047')   # зелёная остановка
C_BLUE    = get_color_from_hex('#1E88E5')   # воспроизведение
C_ORANGE  = get_color_from_hex('#FB8C00')   # поделиться
C_TEXT    = get_color_from_hex('#212121')
C_WHITE   = (1, 1, 1, 1)
C_CARD1   = get_color_from_hex('#FFF176')   # жёлтая карточка
C_CARD2   = get_color_from_hex('#4DD0E1')   # бирюзовая карточка
C_CARD3   = get_color_from_hex('#FF8A65')   # коралловая карточка
C_INPUT   = get_color_from_hex('#E3F2FD')
C_INPUT_F = get_color_from_hex('#90CAF9')

Window.clearcolor = C_BG
IS_ANDROID = (platform == 'android')

if IS_ANDROID:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    MediaStore = autoclass('android.provider.MediaStore')
    ContentValues = autoclass('android.content.ContentValues')
    Environment = autoclass('android.os.Environment')
    Build = autoclass('android.os.Build')
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    MediaPlayer = autoclass('android.media.MediaPlayer')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioSource = autoclass('android.media.MediaRecorder$AudioSource')

_app_dir = None
_notes = []
_filter = ''
_player = None
_recorder = None
_recording = False
_tmp_path = None


def app_dir():
    global _app_dir
    if _app_dir is None:
        if IS_ANDROID:
            _app_dir = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
        else:
            _app_dir = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(_app_dir, exist_ok=True)
    return _app_dir


def notes_file():
    return os.path.join(app_dir(), 'notes.json')


def public_dir():
    """Путь к общедоступной папке Music/Sputnik (fallback для старых Android)."""
    if IS_ANDROID:
        try:
            f = Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_MUSIC)
            p = os.path.join(f.getAbsolutePath(), 'Sputnik')
            os.makedirs(p, exist_ok=True)
            return p
        except Exception:
            pass
    return app_dir()


def save_notes():
    try:
        with open(notes_file(), 'w', encoding='utf-8') as f:
            json.dump(_notes, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('save_notes error:', e)


def load_notes():
    global _notes
    try:
        with open(notes_file(), 'r', encoding='utf-8') as f:
            _notes = json.load(f)
    except Exception:
        _notes = []


# ---------------- Работа с записью и хранением ----------------

def insert_to_mediastore(src_path, display_name):
    """Копирует файл в MediaStore (Music/Sputnik), возвращает content-URI."""
    try:
        resolver = PythonActivity.mActivity.getContentResolver()
        values = ContentValues()
        values.put(MediaStore.Audio.Media.DISPLAY_NAME, display_name)
        values.put(MediaStore.Audio.Media.MIME_TYPE, 'audio/mp4')
        values.put(MediaStore.Audio.Media.RELATIVE_PATH, 'Music/Sputnik')
        uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                              values)
        if uri is None:
            return None, None
        out = resolver.openOutputStream(uri)
        with open(src_path, 'rb') as f:
            shutil.copyfileobj(f, out)
        out.close()
        return uri.toString(), None
    except Exception as e:
        print('mediastore error:', e)
        return None, None


def finalize_recording():
    """Переносит временный файл в общедоступное место, добавляет заметку."""
    global _tmp_path
    if _tmp_path is None or not os.path.exists(_tmp_path):
        _tmp_path = None
        return None
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = 'rec_' + stamp + '.m4a'
    uri_str = None
    dest_path = None
    if IS_ANDROID:
        try:
            if Build.VERSION.SDK_INT >= 29:
                uri_str, _ = insert_to_mediastore(_tmp_path, name)
            else:
                dest_path = os.path.join(public_dir(), name)
                shutil.copyfile(_tmp_path, dest_path)
        except Exception as e:
            print('finalize error:', e)
    if uri_str is None and dest_path is None:
        # крайний случай — остаётся во внутреннем каталоге
        dest_path = os.path.join(app_dir(), name)
        try:
            shutil.move(_tmp_path, dest_path)
        except Exception:
            pass
    try:
        os.remove(_tmp_path)
    except Exception:
        pass
    _tmp_path = None
    note = {
        'ts': datetime.now().strftime('%d.%m.%Y %H:%M'),
        'name': name,
        'uri': uri_str,
        'path': dest_path,
        'text': '',
    }
    _notes.insert(0, note)
    save_notes()
    return note


def start_recording():
    global _recorder, _recording, _tmp_path
    try:
        if IS_ANDROID:
            request_permissions([Permission.RECORD_AUDIO])
            _tmp_path = os.path.join(app_dir(), 'rec_tmp.m4a')
            _recorder = MediaRecorder()
            _recorder.setAudioSource(AudioSource.MIC)
            _recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            _recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            _recorder.setAudioEncodingBitRate(128000)
            _recorder.setAudioSamplingRate(44100)
            _recorder.setOutputFile(_tmp_path)
            _recorder.prepare()
            _recorder.start()
            _recording = True
            return True, 'ИДЁТ ЗАПИСЬ…'
        return False, 'Запись доступна только на Android'
    except Exception as e:
        print('record start error:', e)
        return False, 'Ошибка микрофона'


def stop_recording():
    global _recorder, _recording
    if not _recording or _recorder is None:
        return None
    try:
        _recorder.stop()
    except Exception as e:
        print('record stop error:', e)
    try:
        _recorder.release()
    except Exception:
        pass
    _recorder = None
    _recording = False
    return finalize_recording()


def stop_playback():
    global _player
    if _player is not None:
        try:
            _player.stop()
            _player.release()
        except Exception:
            pass
        _player = None


def play_note(note):
    stop_playback()
    global _player
    try:
        if note.get('uri') and IS_ANDROID:
            ctx = PythonActivity.mActivity
            _player = MediaPlayer()
            _player.setDataSource(ctx, Uri.parse(note['uri']))
            _player.prepare()
            _player.start()
            return True
        path = note.get('path')
        if path and os.path.exists(path):
            if IS_ANDROID:
                _player = MediaPlayer()
                _player.setDataSource(path)
                _player.prepare()
                _player.start()
                return True
        return False
    except Exception as e:
        print('play error:', e)
        return False


def share_note(note):
    """Системное меню «Поделиться» для файла записи."""
    try:
        if not IS_ANDROID:
            return False
        ctx = PythonActivity.mActivity
        it = Intent()
        it.setAction(Intent.ACTION_SEND)
        uri_str = note.get('uri')
        if uri_str:
            it.setType('audio/mp4')
            it.putExtra(Intent.EXTRA_STREAM, Uri.parse(uri_str))
            it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        else:
            path = note.get('path')
            if not path or not os.path.exists(path):
                return False
            it.setType('audio/mp4')
            it.putExtra(Intent.EXTRA_STREAM, Uri.fromFile(
                autoclass('java.io.File')(path)))
        ctx.startActivity(Intent.createChooser(it, 'Поделиться записью'))
        return True
    except Exception as e:
        print('share error:', e)
        return False


# ---------------- Интерфейс ----------------

class ColorBar(BoxLayout):
    def __init__(self, color, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            from kivy.graphics import Color as GColor, Rectangle
            self._c = GColor(*color)
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


class SputnikApp(App):
    title = 'Спутник'

    def build(self):
        root = BoxLayout(orientation='vertical', padding=[10, 6, 10, 6],
                         spacing=6)

        # Шапка
        head = ColorBar(C_HEAD, size_hint=(1, None), height=52, padding=8)
        head.add_vertex = None  # noqa
        self.head_label = Label(
            text='ДИКТОФОН С ЗАМЕТКАМИ',
            color=C_WHITE, bold=True, font_size='20sp')
        head.add_widget(self.head_label)
        root.add_widget(head)

        self.status = Label(text='Готов к записи', color=C_TEXT,
                            font_size='16sp', size_hint=(1, None), height=30)
        root.add_widget(self.status)

        # Кнопка записи
        self.rec_btn = Button(text='● НАЧАТЬ ЗАПИСЬ',
                              background_normal='',
                              background_color=C_RED,
                              color=C_WHITE, bold=True,
                              font_size='20sp',
                              size_hint=(1, None), height=64)
        self.rec_btn.bind(on_press=self.toggle_record)
        root.add_widget(self.rec_btn)

        self.path_label = Label(
            text='Записи: Music/Sputnik (общедоступная папка)',
            color=get_color_from_hex('#607D8B'),
            font_size='12sp', size_hint=(1, None), height=22)
        root.add_widget(self.path_label)

        # Поле текста заметки
        self.note_input = TextInput(
            hint_text='Текст заметки (можно оставить пустым)',
            multiline=False, font_size='16sp',
            background_normal='', background_active='',
            background_color=C_INPUT,
            foreground_color=C_TEXT,
            cursor_color=C_HEAD,
            size_hint=(1, None), height=48)
        root.add_widget(self.note_input)

        # Поиск
        self.search_input = TextInput(
            hint_text='Поиск по заметкам',
            multiline=False, font_size='16sp',
            background_normal='', background_active='',
            background_color=C_INPUT,
            foreground_color=C_TEXT,
            cursor_color=C_HEAD,
            size_hint=(1, None), height=48)
        self.search_input.bind(text=self.on_search)
        root.add_widget(self.search_input)

        # Список заметок
        self.list_container = GridLayout(cols=1, size_hint_y=None,
                                         spacing=6, padding=[0, 2, 0, 2])
        self.list_container.bind(
            minimum_height=self.list_container.setter('height'))
        scroll = ScrollView()
        scroll.add_widget(self.list_container)
        root.add_widget(scroll)

        load_notes()
        self.refresh_list()
        return root

    def on_search(self, instance, value):
        global _filter
        _filter = value.strip()
        self.refresh_list()

    def toggle_record(self, *args):
        global _recording
        if not _recording:
            self.status.text = 'Готовлюсь к записи…'
            ok, msg = start_recording()
            self.status.text = msg
            if ok:
                self.rec_btn.text = '■ ОСТАНОВИТЬ'
                self.rec_btn.background_color = C_GREEN
        else:
            note = stop_recording()
            if note is not None:
                self.status.text = 'Запись сохранена: ' + note['name']
            else:
                self.status.text = 'Запись не удалась'
            self.rec_btn.text = '● НАЧАТЬ ЗАПИСЬ'
            self.rec_btn.background_color = C_RED
            self.refresh_list()

    def refresh_list(self):
        c = self.list_container
        c.clear_widgets()
        shown = 0
        for i, note in enumerate(_notes):
            if _filter and _filter.lower() not in note.get('text', '').lower():
                continue
            shown += 1
            card_color = (C_CARD1, C_CARD2, C_CARD3)[i % 3]
            row = BoxLayout(size_hint=(1, None), height=64, spacing=4)
            text = note['ts']
            if note.get('text'):
                text += '\n' + note['text']
            else:
                text += '\n(без текста)'
            b = Button(text=text, background_normal='',
                       background_color=card_color,
                       color=C_TEXT, bold=True, font_size='14sp',
                       halign='left', valign='middle')
            b.bind(on_press=lambda *a, n=note: self.on_play(n))
            row.add_widget(b)
            pb = Button(text='▶', background_normal='',
                        background_color=C_BLUE, color=C_WHITE, bold=True,
                        font_size='18sp', size_hint_x=None, width=56)
            pb.bind(on_press=lambda *a, n=note: self.on_play(n))
            row.add_widget(pb)
            sb = Button(text='↗', background_normal='',
                        background_color=C_ORANGE, color=C_WHITE, bold=True,
                        font_size='18sp', size_hint_x=None, width=56)
            sb.bind(on_press=lambda *a, n=note: self.on_share(n))
            row.add_widget(sb)
            c.add_widget(row)
        if shown == 0:
            c.add_widget(Label(text='Заметок пока нет — нажмите красную кнопку',
                               color=C_TEXT, font_size='15sp',
                               size_hint=(1, None), height=40))

    def on_play(self, note):
        if play_note(note):
            self.status.text = 'Воспроизведение: ' + note['name']
        else:
            self.status.text = 'Не удалось воспроизвести'

    def on_share(self, note):
        if share_note(note):
            self.status.text = 'Открываю «Поделиться»…'
        else:
            self.status.text = 'Не удалось открыть «Поделиться»'


if __name__ == '__main__':
    SputnikApp().run()
