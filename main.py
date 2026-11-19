# -*- coding: utf-8 -*-
"""
Диктофон с заметками "Спутник"
- запись микрофона
- заметки с текстом и поиском
- воспроизведение по кнопке ▶
- поделиться по кнопке ↗
- записи дублируются в общедоступную папку Music/Sputnik
"""
import os
import json
import shutil
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

IS_ANDROID = (os.environ.get('ANDROID_ARGUMENT') is not None)

if IS_ANDROID:
    Window.softinput_mode = 'below_target'

# ---------- палитра ----------
C_HEADER = '#1565C0'
C_RED = '#E53935'
C_GREEN = '#2E7D32'
C_BLUE = '#1976D2'
C_ORANGE = '#EF6C00'
CARDS = ['#FFF9C4', '#B2EBF2', '#FFCCBC']


def rgba(hexcol, alpha=1.0):
    h = hexcol.lstrip('#')
    return (int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0,
            alpha)


NOTES_FILE = 'notes.json'


def ensure_permissions():
    if not IS_ANDROID:
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.RECORD_AUDIO,
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])
    except Exception as e:
        print('permissions request failed:', e)


class Recorder:
    def __init__(self):
        self.recorder = None
        self.path = None

    def start(self, out_path):
        from jnius import autoclass
        MR = autoclass('android.media.MediaRecorder')
        r = MR()
        r.setAudioSource(0)  # MIC
        r.setOutputFormat(2)  # MPEG_4
        r.setAudioEncoder(3)  # AAC
        r.setAudioSamplingRate(44100)
        r.setAudioEncodingBitRate(128000)
        r.setOutputFile(out_path)
        r.prepare()
        r.start()
        self.recorder = r
        self.path = out_path

    def stop(self):
        if self.recorder is None:
            return None
        try:
            self.recorder.stop()
        except Exception:
            pass
        try:
            self.recorder.release()
        except Exception:
            pass
        p = self.path
        self.recorder = None
        self.path = None
        return p


def get_activity():
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        return PythonActivity.mActivity
    except Exception:
        return None


def copy_to_public(local_path, display_name):
    """Копирует запись в общедоступную Music/Sputnik через MediaStore.
    Возвращает content-URI (str) или None."""
    if not IS_ANDROID:
        return None
    try:
        from jnius import autoclass
        Environment = autoclass('android.os.Environment')
        ContentValues = autoclass('android.content.ContentValues')
        MediaStore = autoclass('android.provider.MediaStore')
        String = autoclass('java.lang.String')

        activity = get_activity()
        if activity is None:
            return None
        resolver = activity.getContentResolver()

        values = ContentValues()
        values.put(String('display_name'), String(display_name))
        values.put(String('mime_type'), String('audio/mp4'))
        values.put(String('relative_path'),
                   String(Environment.DIRECTORY_MUSIC + '/Sputnik'))

        uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)
        if uri is None:
            return None

        out = resolver.openOutputStream(uri)
        with open(local_path, 'rb') as f:
            shutil.copyfileobj(f, out)
        out.close()
        return uri.toString()
    except Exception as e:
        print('copy_to_public failed:', e)
        return None


def query_public_uri(display_name):
    """Ищет content-URI записи в MediaStore по имени файла."""
    if not IS_ANDROID:
        return None
    try:
        from jnius import autoclass
        MediaStore = autoclass('android.provider.MediaStore')
        String = autoclass('java.lang.String')
        activity = get_activity()
        if activity is None:
            return None
        resolver = activity.getContentResolver()
        coll = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        cur = resolver.query(coll, None, String('_display_name=?'),
                             [String(display_name)], None)
        if cur is None:
            return None
        uri = None
        if cur.moveToFirst():
            idx = cur.getColumnIndexOrThrow(String('_id'))
            _id = cur.getLong(idx)
            uri = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI.toString() + '/' + str(_id)
        cur.close()
        return uri
    except Exception as e:
        print('query_public_uri failed:', e)
        return None


def share_file(uri_string):
    """Открывает системное меню Поделиться для content-URI."""
    try:
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        String = autoclass('java.lang.String')
        activity = get_activity()
        if activity is None or uri_string is None:
            return False
        intent = Intent()
        intent.setAction(Intent.ACTION_SEND)
        intent.setType(String('audio/mp4'))
        intent.putExtra(Intent.EXTRA_STREAM, Uri.parse(String(uri_string)))
        intent.addFlags(0x10000000)  # FLAG_GRANT_READ_URI_PERMISSION
        chooser = Intent.createChooser(intent, String('Поделиться записью'))
        activity.startActivity(chooser)
        return True
    except Exception as e:
        print('share failed:', e)
        return False


class SputnikApp(App):
    def build(self):
        self.title = 'Диктофон с заметками'
        ensure_permissions()

        self.rec = Recorder()
        self.recording = False
        self.notes = self.load_notes()

        Window.clearcolor = (1, 1, 1, 1)

        root = BoxLayout(orientation='vertical', padding=[12, 10], spacing=10)

        # шапка
        header = Label(text='ДИКТОФОН С ЗАМЕТКАМИ',
                       color=(1, 1, 1, 1), bold=True, font_size='22sp',
                       size_hint=(1, None), height='54dp')
        with header.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*rgba(C_HEADER))
            header.bg_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self._upd_bg, size=self._upd_bg)
        root.add_widget(header)

        # статус
        self.status = Label(text='Готов к записи', font_size='17sp',
                            color=(0.1, 0.1, 0.1, 1),
                            size_hint=(1, None), height='30dp')
        root.add_widget(self.status)

        # кнопка записи
        self.btn_rec = Button(text='● НАЧАТЬ ЗАПИСЬ', bold=True,
                              font_size='20sp', color=(1, 1, 1, 1),
                              background_normal='', background_down='',
                              background_color=rgba(C_RED),
                              size_hint=(1, None), height='62dp')
        self.btn_rec.bind(on_press=self.toggle_rec)
        root.add_widget(self.btn_rec)

        # подпись, куда пишутся записи
        self.path_hint = Label(text='Записи: Music/Sputnik (общедоступная папка)',
                               font_size='14sp', color=(0.35, 0.35, 0.35, 1),
                               size_hint=(1, None), height='24dp')
        root.add_widget(self.path_hint)

        # поле текста заметки
        self.note_input = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                                    font_size='17sp', multiline=False,
                                    size_hint=(1, None), height='48dp',
                                    background_color=(0.93, 0.96, 1, 1),
                                    foreground_color=(0.05, 0.05, 0.05, 1))
        root.add_widget(self.note_input)

        # поиск
        self.search_input = TextInput(hint_text='Поиск по заметкам',
                                      font_size='16sp', multiline=False,
                                      size_hint=(1, None), height='44dp',
                                      background_color=(0.93, 0.96, 1, 1))
        self.search_input.bind(text=self.refresh_list)
        root.add_widget(self.search_input)

        # список заметок
        self.list_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_box = BoxLayout(orientation='vertical', spacing=8, size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)

        self.refresh_list()
        return root

    def _upd_bg(self, inst, value):
        inst.bg_rect.pos = inst.pos
        inst.bg_rect.size = inst.size

    # ---------- заметки ----------
    def notes_path(self):
        return os.path.join(self.user_data_dir, NOTES_FILE)

    def load_notes(self):
        try:
            with open(self.notes_path(), encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_notes(self):
        try:
            with open(self.notes_path(), 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print('save_notes failed:', e)

    # ---------- запись ----------
    def toggle_rec(self, *args):
        if self.recording:
            self.stop_rec()
        else:
            self.start_rec()

    def start_rec(self):
        try:
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            local = os.path.join(self.user_data_dir,
                                 'rec_{}.m4a'.format(stamp))
            self.rec.start(local)
            self.recording = True
            self.btn_rec.text = '■ ОСТАНОВИТЬ'
            self.btn_rec.background_color = rgba(C_GREEN)
            self.status.text = 'Идёт запись…'
            self.status.color = rgba(C_GREEN)
        except Exception as e:
            self.status.text = 'Ошибка микрофона: {}'.format(e)
            self.status.color = rgba(C_RED)

    def stop_rec(self):
        try:
            path = self.rec.stop()
            self.recording = False
            self.btn_rec.text = '● НАЧАТЬ ЗАПИСЬ'
            self.btn_rec.background_color = rgba(C_RED)
            self.status.color = (0.1, 0.1, 0.1, 1)

            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                display = os.path.basename(path)
                public_uri = copy_to_public(path, display)
                note = {
                    'file': path,
                    'name': display,
                    'uri': public_uri,
                    'text': (self.note_input.text or '').strip(),
                    'time': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'dur': 0,
                }
                self.notes.insert(0, note)
                self.save_notes()
                self.note_input.text = ''
                self.refresh_list()
                if public_uri:
                    self.status.text = 'Запись сохранена (Music/Sputnik)'
                else:
                    self.status.text = 'Запись сохранена (папка приложения)'
            else:
                self.status.text = 'Запись пустая — микрофон не дал данных'
        except Exception as e:
            self.status.text = 'Ошибка сохранения: {}'.format(e)

    # ---------- список ----------
    def refresh_list(self, *args):
        self.list_box.clear_widgets()
        q = (self.search_input.text or '').strip().lower() \
            if hasattr(self, 'search_input') else ''
        shown = [n for n in self.notes
                 if not q or q in (n.get('text') or '').lower()
                 or q in (n.get('time') or '').lower()]
        if not shown:
            lbl = Label(text='Заметок пока нет — нажмите красную кнопку'
                             if not q else 'Ничего не найдено',
                        color=(0.1, 0.1, 0.1, 1), font_size='17sp',
                        size_hint=(1, None), height='40dp')
            self.list_box.add_widget(lbl)
            return
        for i, n in enumerate(shown):
            card = BoxLayout(orientation='horizontal', spacing=6,
                             size_hint_y=None, height='64dp',
                             padding=[8, 4])
            with card.canvas.before:
                from kivy.graphics import Color, Rectangle
                Color(*rgba(CARDS[i % 3]))
                card.bg_rect = Rectangle(pos=card.pos, size=card.size)
            card.bind(pos=self._upd_bg, size=self._upd_bg)

            info = BoxLayout(orientation='vertical', spacing=2)
            t1 = Label(text=n.get('time', ''), font_size='15sp',
                       bold=True, color=(0.05, 0.05, 0.05, 1), halign='left')
            txt = n.get('text') or '(без текста)'
            t2 = Label(text=txt, font_size='14sp',
                       color=(0.15, 0.15, 0.15, 1), halign='left')
            t1.bind(size=lambda inst, s: setattr(inst, 'text_size', s))
            t2.bind(size=lambda inst, s: setattr(inst, 'text_size', s))
            info.add_widget(t1)
            info.add_widget(t2)
            card.add_widget(info)

            b_play = Button(text='▶', bold=True, font_size='20sp',
                            background_normal='', background_down='',
                            background_color=rgba(C_BLUE),
                            size_hint=(None, 1), width='58dp')
            b_play.bind(on_press=lambda inst, nn=n: self.play_note(nn))
            card.add_widget(b_play)

            b_share = Button(text='↗', bold=True, font_size='20sp',
                             background_normal='', background_down='',
                             background_color=rgba(C_ORANGE),
                             size_hint=(None, 1), width='58dp')
            b_share.bind(on_press=lambda inst, nn=n: self.share_note(nn))
            card.add_widget(b_share)

            self.list_box.add_widget(card)

    # ---------- проигрывание ----------
    def play_note(self, note):
        try:
            self.stop_player()
        except Exception:
            pass
        try:
            from jnius import autoclass
            MediaPlayer = autoclass('android.media.MediaPlayer')
            Uri = autoclass('android.net.Uri')
            String = autoclass('java.lang.String')
            activity = get_activity()

            uri = note.get('uri')
            if uri:
                mp = MediaPlayer()
                mp.setDataSource(activity, Uri.parse(String(uri)))
            else:
                mp = MediaPlayer()
                mp.setDataSource(String(note.get('file')))

            mp.prepare()
            mp.start()
            self.mp = mp
            self.status.text = 'Воспроизведение: ' + note.get('time', '')
            self.status.color = rgba(C_BLUE)
        except Exception as e:
            self.status.text = 'Ошибка проигрывания: {}'.format(e)
            self.status.color = rgba(C_RED)

    def stop_player(self):
        mp = getattr(self, 'mp', None)
        if mp is not None:
            try:
                mp.stop()
                mp.release()
            except Exception:
                pass
            self.mp = None

    # ---------- поделиться ----------
    def share_note(self, note):
        uri = note.get('uri') or query_public_uri(note.get('name', ''))
        if uri is None:
            self.status.text = 'Файл не найден в Music/Sputnik — общая папка недоступна'
            self.status.color = rgba(C_ORANGE)
            return
        if share_file(uri):
            self.status.text = 'Открываю меню Поделиться…'
            self.status.color = rgba(C_BLUE)
        else:
            self.status.text = 'Не удалось открыть меню Поделиться'
            self.status.color = rgba(C_ORANGE)


if __name__ == '__main__':
    SputnikApp().run()
