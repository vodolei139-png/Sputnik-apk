# -*- coding: utf-8 -*-
import os
import json
import time

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

FONT_REGULAR = 'fonts/Montserrat-Regular.ttf'
FONT_BOLD = 'fonts/Montserrat-Bold.ttf'

ANDROID = False
ANDROID_ERR = ''
try:
    from jnius import autoclass, cast
    from android.permissions import request_permissions, Permission
    ANDROID = True
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
    OutputFormat = autoclass('android.media.MediaRecorder$OutputFormat')
    AudioEncoder = autoclass('android.media.MediaRecorder$AudioEncoder')
    Environment = autoclass('android.os.Environment')
    BuildVersion = autoclass('android.os.Build$VERSION')
    ContentValues = autoclass('android.content.ContentValues')
    MediaStoreAudio = autoclass('android.provider.MediaStore$Audio$Media')
    MediaPlayer = autoclass('android.media.MediaPlayer')
    IntentCls = autoclass('android.content.Intent')
    UriCls = autoclass('android.net.Uri')
    FileCls = autoclass('java.io.File')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
except Exception:
    ANDROID = False

RECORD_DIR = 'Music/Sputnik'
NOTES_FILE = 'notes.json'


def with_bg(widget, rgba):
    with widget.canvas.before:
        widget._bg = Color(*rgba)
        widget._bg_rect = Rectangle(pos=widget.pos, size=widget.size)

    def _sync(instance, value):
        widget._bg_rect.pos = widget.pos
        widget._bg_rect.size = widget.size

    widget.bind(pos=_sync, size=_sync)
    return widget


class NoteItem(BoxLayout):
    PALETTE = [
        (1.0, 0.97, 0.6, 1),
        (0.6, 0.93, 0.87, 1),
        (1.0, 0.68, 0.6, 1),
    ]

    def __init__(self, note, index, on_play, on_share, **kwargs):
        super(NoteItem, self).__init__(**kwargs)
        self.note = note
        self.orientation = 'horizontal'
        self.spacing = 8
        self.padding = (8, 6, 8, 6)
        self.size_hint_y = None
        self.height = 56
        with_bg(self, self.PALETTE[index % len(self.PALETTE)])

        left = BoxLayout(orientation='vertical', size_hint_x=0.6)
        left.add_widget(Label(
            text=note.get('date', ''),
            font_name=FONT_BOLD,
            color=(0.1, 0.1, 0.1, 1),
            font_size='15sp',
            size_hint_y=None,
            height=24,
        ))
        left.add_widget(Label(
            text=note.get('text') or '(без текста)',
            font_name=FONT_REGULAR,
            color=(0.15, 0.15, 0.15, 1),
            font_size='14sp',
        ))
        self.add_widget(left)

             right = BoxLayout(orientation='horizontal', size_hint_x=0.32, spacing=4)
        btn_play = Button(
            text='СЛУШАТЬ',
            font_name=FONT_REGULAR,
            font_size='11sp',
            background_color=(0.12, 0.45, 0.85, 1),
        )
        btn_play.bind(on_release=lambda *a: on_play(self.note))
        btn_share = Button(
            text='ОТПРАВИТЬ',
            font_name=FONT_REGULAR,
            font_size='11sp',
            background_color=(0.95, 0.55, 0.05, 1),
        )
        btn_share.bind(on_release=lambda *a: on_share(self.note))
        right.add_widget(btn_play)
        right.add_widget(btn_share)
        self.add_widget(right)


def save_to_music(temp_path):
    filename = 'rec_' + time.strftime('%Y%m%d_%H%M%S') + '.m4a'
    result = {'path': temp_path, 'uri': '', 'note': None}
    if not ANDROID:
        result['note'] = 'no android modules'
        return result
    sdk = 0
    try:
        sdk = int(BuildVersion.SDK_INT)
    except Exception:
        sdk = 0
    if sdk >= 29:
        try:
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            values = ContentValues()
            values.put('title', filename)
            values.put('mime_type', 'audio/mp4')
            values.put('relative_path', RECORD_DIR)
            uri = resolver.insert(MediaStoreAudio.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                result['note'] = 'MediaStore refused'
                return result
            out_stream = resolver.openOutputStream(uri)
            with open(temp_path, 'rb') as f:
                data = f.read()
            out_stream.write(data)
            out_stream.close()
            os.remove(temp_path)
            result['path'] = ''
            result['uri'] = str(uri)
            return result
        except Exception as e:
            result['note'] = 'MediaStore: ' + str(e)
            return result
    try:
        base = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
        folder = os.path.join(str(base), 'Sputnik')
        if not os.path.isdir(folder):
            os.makedirs(folder)
        target = os.path.join(folder, filename)
        with open(temp_path, 'rb') as f:
            data = f.read()
        with open(target, 'wb') as f:
            f.write(data)
        os.remove(temp_path)
        result['path'] = target
        return result
    except Exception as e:
        result['note'] = 'Copy: ' + str(e)
        return result


class DictaphoneApp(App):
    def __init__(self, **kwargs):
        super(DictaphoneApp, self).__init__(**kwargs)
        self.notes = []
        self.is_recording = False
        self.recorder = None
        self.temp_path = None
        self.load_notes()

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        header = with_bg(Label(
            text='ДИКТОФОН С ЗАМЕТКАМИ',
            font_name=FONT_BOLD,
            color=(1, 1, 1, 1),
            font_size='22sp',
            size_hint_y=None,
            height=52,
        ), (0.05, 0.4, 0.75, 1))
        root.add_widget(header)

        self.lbl_status = Label(
            text='Готов к записи',
            font_name=FONT_REGULAR,
            color=(0.6, 0.1, 0.1, 1),
            font_size='14sp',
            size_hint_y=None,
            height=30,
        )
        root.add_widget(self.lbl_status)

        if not ANDROID and ANDROID_ERR:
            self.show_status('Сборка без Android-модулей. Причина: ' + ANDROID_ERR)

        self.btn_record = Button(
            text='НАЧАТЬ ЗАПИСЬ',
            font_name=FONT_BOLD,
            font_size='20sp',
            background_color=(0.85, 0.2, 0.2, 1),
            size_hint_y=None,
            height=70,
        )
        self.btn_record.bind(on_release=self.toggle_recording)
        root.add_widget(self.btn_record)

        root.add_widget(Label(
            text='Записи: Music/Sputnik (общедоступная папка)',
            font_name=FONT_REGULAR,
            color=(0.2, 0.35, 0.6, 1),
            font_size='13sp',
            size_hint_y=None,
            height=24,
        ))

        self.txt_note = TextInput(
            hint_text='Текст заметки (можно оставить пустым)',
            font_name=FONT_REGULAR,
            multiline=True,
            size_hint_y=None,
            height=70,
        )
        root.add_widget(self.txt_note)

        self.txt_search = TextInput(
            hint_text='Поиск по заметкам',
            font_name=FONT_REGULAR,
            multiline=False,
            size_hint_y=None,
            height=48,
        )
        self.txt_search.bind(text=self.on_search)
        root.add_widget(self.txt_search)

        self.list_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
        self.list_container.bind(minimum_height=self.list_container.setter('height'))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.list_container)
        root.add_widget(scroll)

        self.refresh_notes_ui()

        if ANDROID:
            try:
                request_permissions([
                    Permission.RECORD_AUDIO,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                ])
            except Exception as e:
                self.show_status('Разрешения: ' + str(e))

        return root

    def toggle_recording(self, *args):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not ANDROID:
            if ANDROID_ERR:
                self.show_status('Android-модули не загрузились: ' + ANDROID_ERR)
            else:
                self.show_status('Запись доступна только на Android')
            return
        try:
            if not os.path.isdir(self.user_data_dir):
                os.makedirs(self.user_data_dir)
            self.temp_path = os.path.join(self.user_data_dir, 'rec_tmp.m4a')
            if os.path.exists(self.temp_path):
                os.remove(self.temp_path)
            rec = MediaRecorder()
            rec.setAudioSource(AudioSource.MIC)
            rec.setOutputFormat(OutputFormat.MPEG_4)
            rec.setAudioEncoder(AudioEncoder.AAC)
            rec.setOutputFile(self.temp_path)
            rec.prepare()
            rec.start()
            self.recorder = rec
            self.is_recording = True
            self.btn_record.text = 'ОСТАНОВИТЬ'
            self.btn_record.background_color = (0.1, 0.6, 0.3, 1)
            self.show_status('Идёт запись...')
        except Exception as e:
            self.is_recording = False
            self.recorder = None
            self.btn_record.text = 'НАЧАТЬ ЗАПИСЬ'
            self.btn_record.background_color = (0.85, 0.2, 0.2, 1)
            self.show_status('Ошибка записи: ' + str(e))

    def stop_recording(self):
        try:
            if self.recorder:
                self.recorder.stop()
                self.recorder.release()
                self.recorder = None
            self.is_recording = False
            self.btn_record.text = 'НАЧАТЬ ЗАПИСЬ'
            self.btn_record.background_color = (0.85, 0.2, 0.2, 1)
            self.publish_record()
        except Exception as e:
            self.is_recording = False
            self.recorder = None
            self.btn_record.text = 'НАЧАТЬ ЗАПИСЬ'
            self.btn_record.background_color = (0.85, 0.2, 0.2, 1)
            self.show_status('Ошибка остановки: ' + str(e))

    def publish_record(self):
        temp_path = self.temp_path
        if not temp_path or not os.path.exists(temp_path):
            self.show_status('Файл записи не найден')
            return
        note = {
            'text': self.txt_note.text.strip() or '(без текста)',
            'date': time.strftime('%d.%m.%Y %H:%M'),
            'path': '',
            'uri': '',
        }
        result = save_to_music(temp_path)
        note['path'] = result['path']
        note['uri'] = result['uri']
        if result['note']:
            note['note'] = result['note']
        self.notes.append(note)
        self.save_notes()
        self.txt_note.text = ''
        self.temp_path = None
        self.refresh_notes_ui()
        if result['note']:
            self.show_status('Запись во внутренней папке. Причина: ' + result['note'])
        else:
            self.show_status('Запись сохранена (Music/Sputnik)')

    def play_note(self, note):
        if not ANDROID:
            self.show_status('Воспроизведение доступно на Android')
            return
        try:
            player = MediaPlayer()
            uri_str = note.get('uri', '')
            if uri_str:
                player.setDataSource(PythonActivity.mActivity, UriCls.parse(uri_str))
            else:
                path = note.get('path', '')
                if not path or not os.path.exists(path):
                    self.show_status('Файл записи не найден')
                    return
                player.setDataSource(path)
            player.prepare()
            player.start()
            self.show_status('Воспроизведение...')
        except Exception as e:
            self.show_status('Ошибка воспроизведения: ' + str(e))

        def share_note(self, note):
        if not ANDROID:
            self.show_status('Отправка доступна на Android')
            return
        uri_str = note.get('uri', '')
        if uri_str:
            uri_obj = UriCls.parse(uri_str)
        else:
            path = note.get('path', '')
            if not path or not os.path.exists(path):
                self.show_status('Файл записи не найден')
                return
            uri_obj = UriCls.fromFile(FileCls(path))
        activity = PythonActivity.mActivity
        errors = []
        for attempt in ('cast', 'plain'):
            try:
                intent = IntentCls()
                intent.setAction(IntentCls.ACTION_SEND)
                intent.setType('audio/mp4')
                if attempt == 'cast':
                    intent.putExtra(IntentCls.EXTRA_STREAM,
                                    cast('android.os.Parcelable', uri_obj))
                else:
                    intent.putExtra(IntentCls.EXTRA_STREAM, uri_obj)
                intent.addFlags(1)
                chooser = IntentCls.createChooser(intent, 'Отправить запись')
                activity.startActivity(chooser)
                self.show_status('Открываю меню отправки...')
                return
            except Exception as e:
                errors.append(attempt + ': ' + str(e))
        print('share failed:', errors)
        try:
            view_intent = IntentCls(IntentCls.ACTION_VIEW)
            view_intent.setDataAndType(uri_obj, 'audio/mp4')
            view_intent.addFlags(1)
            activity.startActivity(view_intent)
            self.show_status('Меню не открылось (' + errors[0] + '). Открыто через плеер')
        except Exception:
            self.show_status('Ошибка отправки: ' + errors[0])


    def load_notes(self):
        self.notes = []
        try:
            path = os.path.join(self.user_data_dir, NOTES_FILE)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.notes = data
        except Exception as e:
            print('load_notes error:', e)

    def save_notes(self):
        try:
            if not os.path.isdir(self.user_data_dir):
                os.makedirs(self.user_data_dir)
            path = os.path.join(self.user_data_dir, NOTES_FILE)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('save_notes error:', e)

    def on_search(self, instance, value):
        self.refresh_notes_ui(search=value.strip().lower())

    def refresh_notes_ui(self, search=''):
        self.list_container.clear_widgets()
        notes = self.notes
        if search:
            notes = [n for n in notes if search in (n.get('text') or '').lower()]
        if not notes:
            self.list_container.add_widget(Label(
                text='Заметок пока нет — нажмите красную кнопку',
                font_name=FONT_REGULAR,
                color=(0.45, 0.45, 0.45, 1),
                size_hint_y=None,
                height=40,
            ))
            return
        for index, note in enumerate(notes):
            self.list_container.add_widget(
                NoteItem(note, index, self.play_note, self.share_note)
            )

    def show_status(self, text):
        self.lbl_status.text = text
        print('[STATUS]', text)


if __name__ == '__main__':
    DictaphoneApp().run()
