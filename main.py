# -*- coding: utf-8 -*-
import os, json, time

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle

IS_ANDROID = False
try:
    from jnius import autoclass
    IS_ANDROID = True
except Exception:
    pass


def request_android_permissions():
    if not IS_ANDROID:
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.RECORD_AUDIO,
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])
    except Exception:
        pass


class ColoredBox(BoxLayout):
    def __init__(self, bg=(1, 1, 1, 1), **kw):
        super(ColoredBox, self).__init__(**kw)
        self.bg = bg
        with self.canvas.before:
            Color(*bg)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size


NOTES_FILE = 'notes.json'


class RecorderApp(App):
    def __init__(self, **kw):
        super(RecorderApp, self).__init__(**kw)
        self.recorder = None
        self.recording = False
        self.recording_path = None
        self.pending_note_text = ''
        self.notes = []

    def build(self):
        request_android_permissions()
        Clock.schedule_once(lambda dt: self._load_notes(), 0)

        root = ColoredBox(bg=(1, 1, 1, 1), orientation='vertical', spacing=6, padding=[8, 8, 8, 8])

        header = Label(text='ДИКТОФОН С ЗАМЕТКАМИ', bold=True, color=(1, 1, 1, 1),
                       font_size='22sp', size_hint_y=None, height=56)
        with header.canvas.before:
            Color(0.13, 0.42, 0.85, 1)
            Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self._upd_bg, size=self._upd_bg)
        root.add_widget(header)

        self.status = Label(text='Готов к записи', color=(0.2, 0.2, 0.2, 1),
                            size_hint_y=None, height=34, font_size='16sp')
        root.add_widget(self.status)

        self.btn_record = Button(text='НАЧАТЬ ЗАПИСЬ', bold=True, color=(1, 1, 1, 1),
                                 background_normal='', background_color=(0.90, 0.20, 0.20, 1),
                                 size_hint_y=None, height=64, font_size='20sp',
                                 on_press=self.on_record)
        root.add_widget(self.btn_record)

        hint = Label(text='Записи: Music/Sputnik (общедоступная папка)',
                     color=(0.35, 0.45, 0.6, 1), size_hint_y=None, height=30, font_size='14sp')
        root.add_widget(hint)

        self.txt_note = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                                  size_hint_y=None, height=56, multiline=False,
                                  background_color=(0.93, 0.95, 1, 1), foreground_color=(0.1, 0.1, 0.1, 1))
        root.add_widget(self.txt_note)

        self.txt_search = TextInput(hint_text='Поиск по заметкам', size_hint_y=None, height=50,
                                    multiline=False,
                                    background_color=(0.93, 0.95, 1, 1), foreground_color=(0.1, 0.1, 0.1, 1))
        self.txt_search.bind(text=lambda inst, v: self.refresh_list())
        root.add_widget(self.txt_search)

        self.scroll = ScrollView(do_scroll_x=False)
        self.list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)

        return root

    def _upd_bg(self, inst, val):
        pass

    # ---------- notes storage ----------

    def _notes_path(self):
        try:
            d = self.user_data_dir
        except Exception:
            d = os.getcwd()
        return os.path.join(d, NOTES_FILE)

    def _load_notes(self):
        try:
            p = self._notes_path()
            if os.path.exists(p):
                with open(p, 'r') as f:
                    self.notes = json.load(f)
            else:
                self.notes = []
        except Exception as e:
            self.notes = []
            self.set_status('Заметки не прочитаны: %s' % e)
        self.refresh_list()

    def _save_notes(self):
        try:
            with open(self._notes_path(), 'w') as f:
                json.dump(self.notes, f, ensure_ascii=False)
            return True
        except Exception as e:
            self.set_status('Не сохранить список: %s' % e)
            return False

    # ---------- recording ----------

    def set_status(self, text):
        try:
            self.status.text = text
        except Exception:
            pass

    def on_record(self, *args):
        request_android_permissions()
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        try:
            if not IS_ANDROID:
                self.set_status('Запись доступна только на Android')
                return
            if not os.path.isdir(self.user_data_dir):
                os.makedirs(self.user_data_dir)
            tmp = os.path.join(self.user_data_dir, 'tmp_rec.m4a')

            MediaRecorder = autoclass('android.media.MediaRecorder')
            mr = MediaRecorder()
            mr.setAudioSource(1)       # MIC
            mr.setOutputFormat(2)      # MPEG_4
            mr.setAudioEncoder(3)      # AAC
            mr.setOutputFile(tmp)
            mr.prepare()
            mr.start()

            self.recorder = mr
            self.recording = True
            self.recording_path = tmp
            self.pending_note_text = self.txt_note.text.strip()
            self.txt_note.text = ''
            self.btn_record.text = 'ОСТАНОВИТЬ'
            self.btn_record.background_color = (0.13, 0.65, 0.25, 1)
            self.set_status('Идёт запись...')
        except Exception as e:
            self.set_status('Ошибка записи: %s' % e)
            self.recording = False
            self.recorder = None

    def _stop_recording(self):
        try:
            if self.recorder:
                self.recorder.stop()
                self.recorder.release()
        except Exception as e:
            self.set_status('Ошибка остановки: %s' % e)
            self.recorder = None
        self.recorder = None
        self.recording = False
        self.btn_record.text = 'НАЧАТЬ ЗАПИСЬ'
        self.btn_record.background_color = (0.90, 0.20, 0.20, 1)

        src = self.recording_path
        if not src or not os.path.exists(src):
            self.set_status('Файл записи не создан')
            return

        fname = 'rec_%s.m4a' % time.strftime('%Y%m%d_%H%M%S')
        note = {'date': time.strftime('%d.%m.%Y %H:%M'), 'text': self.pending_note_text,
                'uri': None, 'tmp': None}
        self.pending_note_text = ''

        ok, where = self._save_public(src, fname)
        if ok:
            note['uri'] = where
            self.set_status('Запись сохранена (Music/Sputnik)')
        else:
            note['tmp'] = src
            self.set_status('Сохранено в папке приложения. Причина: %s' % where)

        self.notes.insert(0, note)
        self._save_notes()
        self.refresh_list()

    def _save_public(self, src, fname):
        """Пытается сохранить запись в общедоступную Music/Sputnik.
        Возвращает (True, uri_str) или (False, причина)."""
        try:
            if not IS_ANDROID:
                return False, 'не Android'
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            MediaStore = autoclass('android.provider.MediaStore')
            ContentValues = autoclass('android.content.ContentValues')
            JString = autoclass('java.lang.String')
            Build = autoclass('android.os.Build')
            sdk = Build.VERSION.SDK_INT

            with open(src, 'rb') as f:
                data = f.read()

            if sdk >= 29:
                resolver = PythonActivity.mActivity.getContentResolver()
                values = ContentValues()
                values.put(JString('_display_name'), JString(fname))
                values.put(JString('mime_type'), JString('audio/mp4'))
                values.put(JString('relative_path'), JString('Music/Sputnik'))
                uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)
                if uri is None:
                    return False, 'система не дала создать файл'
                out = resolver.openOutputStream(uri)
                if out is None:
                    return False, 'поток записи недоступен'
                try:
                    out.write(data)
                finally:
                    out.close()
                return True, str(uri.toString())
            else:
                base = '/storage/emulated/0/Music/Sputnik'
                if not os.path.isdir(base):
                    os.makedirs(base)
                dst = os.path.join(base, fname)
                with open(dst, 'wb') as f:
                    f.write(data)
                return True, 'file://' + dst
        except Exception as e:
            return False, str(e)

    # ---------- playback ----------

    def _play(self, note):
        try:
            if not IS_ANDROID:
                self.set_status('Прослушивание доступно только на Android')
                return
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            MediaPlayer = autoclass('android.media.MediaPlayer')
            Uri = autoclass('android.net.Uri')
            if self.player:
                try:
                    self.player.release()
                except Exception:
                    pass
                self.player = None
            mp = MediaPlayer()
            if note.get('uri'):
                mp.setDataSource(PythonActivity.mActivity, Uri.parse(note['uri']))
            elif note.get('tmp'):
                mp.setDataSource(note['tmp'])
            else:
                self.set_status('Файл записи не найден')
                return
            mp.prepare()
            mp.start()
            self.player = mp
            self.set_status('Воспроизведение...')
        except Exception as e:
            self.set_status('Ошибка воспроизведения: %s' % e)

    # ---------- share ----------

    def _share(self, note):
        try:
            if not IS_ANDROID:
                self.set_status('Отправка доступна только на Android')
                return
            if not note.get('uri'):
                self.set_status('Отправить нельзя: файл не в общей папке')
                return
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            intent = Intent()
            intent.setAction(Intent.ACTION_SEND)
            intent.putExtra(Intent.EXTRA_STREAM, Uri.parse(note['uri']))
            intent.setType('audio/mp4')
            chooser = Intent.createChooser(intent, None)
            PythonActivity.mActivity.startActivity(chooser)
        except Exception as e:
            self.set_status('Ошибка отправки: %s' % e)

    # ---------- list ----------

    def refresh_list(self, *args):
        self.list_box.clear_widgets()
        query = (self.txt_search.text or '').strip().lower()
        palette = [(1.0, 0.98, 0.80, 1), (0.80, 0.96, 0.94, 1), (1.0, 0.86, 0.80, 1)]
        shown = 0
        for i, note in enumerate(self.notes):
            text = note.get('text') or '(без текста)'
            if query and query not in text.lower():
                continue
            row = ColoredBox(bg=palette[i % len(palette)], size_hint_y=None, height=72,
                             padding=[8, 4, 4, 4], spacing=6)
            info = ColoredBox(bg=palette[i % len(palette)], orientation='vertical')
            info.add_widget(Label(text=note.get('date', ''), bold=True,
                                  color=(0.1, 0.1, 0.1, 1), font_size='16sp',
                                  halign='left', valign='middle', size_hint_y=None, height=30))
            info.add_widget(Label(text=text, color=(0.25, 0.25, 0.25, 1),
                                  font_size='15sp', halign='left', valign='top',
                                  text_size=(None, None)))
            row.add_widget(info)
            b_play = Button(text='▶', background_normal='',
                            background_color=(0.15, 0.45, 0.90, 1), color=(1, 1, 1, 1),
                            font_size='20sp')
            b_play.bind(on_press=lambda inst, n=note: self._play(n))
            row.add_widget(b_play)
            b_share = Button(text='↗', background_normal='',
                             background_color=(0.95, 0.55, 0.10, 1), color=(1, 1, 1, 1),
                             font_size='20sp')
            b_share.bind(on_press=lambda inst, n=note: self._share(n))
            row.add_widget(b_share)
            self.list_box.add_widget(row)
            shown += 1
        if shown == 0:
            self.list_box.add_widget(Label(text='Заметок пока нет — нажмите красную кнопку',
                                           color=(0.4, 0.4, 0.4, 1)))


if __name__ == '__main__':
    RecorderApp().run()
