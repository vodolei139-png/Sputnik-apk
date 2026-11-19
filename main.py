# -*- coding: utf-8 -*-
"""Спутник — диктофон с заметками.

Записи сохраняются в общедоступную папку Music/Sputnik (MediaStore),
у каждой заметки есть кнопки воспроизведения и «Поделиться».
"""

import os
import json
import time
import threading

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.audio import SoundLoader
from kivy.clock import Clock, mainthread
from kivy.utils import platform

IS_ANDROID = platform == 'android'

if IS_ANDROID:
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.RECORD_AUDIO,
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])
    except Exception:
        pass

# --- палитра ---
HEADER_BLUE = (0.10, 0.45, 0.85, 1)
RED = (0.85, 0.15, 0.15, 1)
GREEN = (0.10, 0.65, 0.30, 1)
BTN_BLUE = (0.15, 0.50, 0.90, 1)
BTN_ORANGE = (0.95, 0.55, 0.10, 1)
CARD_COLORS = [
    (1.00, 0.95, 0.60, 1),   # жёлтый
    (0.60, 0.95, 0.90, 1),   # бирюзовый
    (1.00, 0.72, 0.65, 1),   # коралловый
]
BG_WHITE = (1, 1, 1, 1)


def _fmt_ts(ts):
    return time.strftime('%d.%m.%Y %H:%M', time.localtime(ts))


class Root(BoxLayout):
    pass


class SputnikApp(App):
    title = 'Спутник'

    def build(self):
        self.notes = []
        self.recorder = None
        self.recording = False
        self.current_sound = None
        self.pending_path = None

        self.notes_file = None
        if IS_ANDROID:
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                self.notes_file = os.path.join(
                    PythonActivity.mActivity.getFilesDir().getAbsolutePath(),
                    'notes.json')
            except Exception:
                self.notes_file = None
        if not self.notes_file:
            self.notes_file = os.path.join(
                self.user_data_dir, 'notes.json')
        self._load_notes()

        root = Root(orientation='vertical', padding=[8, 4, 8, 8], spacing=6)
        root.canvas.before.clear()

        # шапка
        header = Label(text='ДИКТОФОН С ЗАМЕТКАМИ',
                       size_hint_y=None, height=44,
                       bold=True, color=(1, 1, 1, 1),
                       font_size='22sp')
        with header.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*HEADER_BLUE)
            self._header_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self._upd_rect, size=self._upd_rect)
        root.add_widget(header)

        self.status = Label(text='Готов к записи', size_hint_y=None,
                            height=30, font_size='16sp', color=(0, 0, 0, 1))
        root.add_widget(self.status)

        self.rec_btn = Button(text='НАЧАТЬ ЗАПИСЬ', size_hint_y=None,
                              height=56, font_size='20sp', bold=True,
                              background_normal='', background_color=RED,
                              color=(1, 1, 1, 1))
        self.rec_btn.bind(on_press=self.on_rec)
        root.add_widget(self.rec_btn)

        self.path_label = Label(
            text='Записи: Music/Sputnik (общедоступная папка)',
            size_hint_y=None, height=24, font_size='13sp',
            color=(0.4, 0.4, 0.45, 1))
        root.add_widget(self.path_label)

        self.text_input = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                                    size_hint_y=None, height=56,
                                    multiline=False, font_size='16sp')
        root.add_widget(self.text_input)

        self.search_input = TextInput(hint_text='Поиск по заметкам',
                                      size_hint_y=None, height=48,
                                      multiline=False, font_size='15sp')
        self.search_input.bind(text=lambda w, v: self.refresh_list())
        root.add_widget(self.search_input)

        self.list_container = BoxLayout(orientation='vertical',
                                        size_hint_y=None, spacing=6)
        self.scroll = ScrollView()
        self.scroll.add_widget(self.list_container)
        root.add_widget(self.scroll)

        self.refresh_list()
        return root

    def _upd_rect(self, w, v):
        self._header_rect.pos = w.pos
        self._header_rect.size = w.size

    # ---------- хранение заметок ----------

    def _load_notes(self):
        try:
            with open(self.notes_file, encoding='utf-8') as f:
                self.notes = json.load(f)
        except Exception:
            self.notes = []

    def _save_notes(self):
        try:
            with open(self.notes_file, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False)
        except Exception:
            pass

    # ---------- запись ----------

    def on_rec(self, *args):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.recording = True
        self.rec_btn.text = 'ОСТАНОВИТЬ'
        self.rec_btn.background_color = GREEN
        self.status.text = 'Идёт запись…'
        self.pending_path = None
        self._fallback_reason = None

        tmp = self._temp_file()
        self.pending_path = tmp

        def work():
            err = None
            try:
                from kivy.core.audio import android_recorder  # noqa
            except Exception:
                pass
            try:
                rec = self._make_recorder()
                rec.setOutputFile(tmp)
                rec.prepare()
                rec.start()
                self.recorder = rec
                return
            except Exception as e:
                err = str(e)
                self.recorder = None
            Clock.schedule_once(
                lambda dt: self._on_rec_error(err), 0)

        threading.Thread(target=work, daemon=True).start()

    def _make_recorder(self):
        from android.media import MediaRecorder  # noqa: unused при неудаче
        raise ImportError

    def _on_rec_error(self, err):
        # откат на нативный MediaRecorder через pyjnius
        try:
            if IS_ANDROID:
                from jnius import autoclass
                MediaRecorder = autoclass('android.media.MediaRecorder')
                rec = MediaRecorder()
                rec.setAudioSource(MediaRecorder.AudioSource.MIC)
                rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                rec.setAudioEncodingBitRate(128000)
                rec.setAudioSamplingRate(44100)
                rec.setOutputFile(self.pending_path)
                rec.prepare()
                rec.start()
                self.recorder = rec
                return
            else:
                # на десктопе — чистый Python (для отладки не критично)
                self.status.text = 'Запись доступна только на Android'
                self.recording = False
                self.rec_btn.text = 'НАЧАТЬ ЗАПИСЬ'
                self.rec_btn.background_color = RED
                return
        except Exception as e2:
            self.recording = False
            self.rec_btn.text = 'НАЧАТЬ ЗАПИСЬ'
            self.rec_btn.background_color = RED
            self.status.text = 'Ошибка микрофона: %s' % e2

    def stop_recording(self):
        err = None
        try:
            self.recorder.stop()
        except Exception as e:
            err = str(e)
        finally:
            try:
                self.recorder.release()
            except Exception:
                pass
            self.recorder = None
        self.recording = False
        self.rec_btn.text = 'НАЧАТЬ ЗАПИСЬ'
        self.rec_btn.background_color = RED

        if err:
            self.status.text = 'Ошибка сохранения: %s' % err
            return

        tmp = self.pending_path
        self.pending_path = None
        if not tmp or not os.path.exists(tmp):
            self.status.text = 'Файл записи не найден'
            return

        self.status.text = 'Сохраняю…'
        threading.Thread(
            target=lambda: Clock.schedule_once(
                lambda dt: self._finalize_save(tmp), 0),
            daemon=True).start()

    def _finalize_save(self, tmp):
        result = {'where': None, 'uri': None, 'data': None, 'reason': None}
        if IS_ANDROID:
            try:
                from jnius import autoclass
                Environment = autoclass('android.os.Environment')
                MediaStore = autoclass('android.provider.MediaStore')
                ContentValues = autoclass('android.content.ContentValues')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                resolver = activity.getContentResolver()

                fname = os.path.basename(tmp)
                values = ContentValues()
                values.put(MediaStore.Audio.Media.DISPLAY_NAME, fname)
                values.put(MediaStore.Audio.Media.MIME_TYPE, 'audio/mp4')
                rel = Environment.DIRECTORY_MUSIC + '/Sputnik'
                values.put(MediaStore.Audio.Media.RELATIVE_PATH, rel)
                values.put(MediaStore.Audio.Media.IS_PENDING, 1)
                uri = resolver.insert(
                    MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)

                with open(tmp, 'rb') as f:
                    data = f.read()
                out = resolver.openOutputStream(uri)
                out.write(data)
                out.close()
                values.clear()
                values.put(MediaStore.Audio.Media.IS_PENDING, 0)
                resolver.update(uri, values, None, None)

                # абсолютный путь для воспроизведения
                data_path = None
                try:
                    cursor = resolver.query(uri, None, None, None, None)
                    cursor.moveToFirst()
                    idx = cursor.getColumnIndexOrThrow(
                        MediaStore.Audio.Media.DATA)
                    data_path = cursor.getString(idx)
                    cursor.close()
                except Exception:
                    pass

                result['where'] = 'Music/Sputnik'
                result['uri'] = str(uri)
                result['data'] = data_path or None
            except Exception as e:
                result['where'] = 'папка приложения'
                result['reason'] = str(e)
        else:
            result['where'] = 'локальная папка'

        if result['where'] == 'Music/Sputnik':
            try:
                os.remove(tmp)
            except Exception:
                pass

        ts = time.time()
        note = {
            'ts': ts,
            'text': self.text_input.text.strip(),
            'path': result['data'] or tmp,
            'uri': result['uri'],
            'where': result['where'],
            'reason': result['reason'],
        }
        self.notes.insert(0, note)
        self._save_notes()
        self.text_input.text = ''

        if result['where'] == 'Music/Sputnik':
            self.status.text = 'Запись сохранена (Music/Sputnik)'
            self.path_label.text = 'Записи: Music/Sputnik (общедоступная папка)'
        elif result['where'] == 'папка приложения':
            self.status.text = 'Запись сохранена (папка приложения). Причина: %s' % (
                result['reason'] or 'неизвестна')
        else:
            self.status.text = 'Запись сохранена (локальная папка)'
        self.refresh_list()

    def _temp_file(self):
        base = self.user_data_dir if not IS_ANDROID else None
        if IS_ANDROID:
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                base = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
            except Exception:
                base = self.user_data_dir
        return os.path.join(base, 'rec_tmp_%d.m4a' % int(time.time() * 1000))

    # ---------- список заметок ----------

    def refresh_list(self, *args):
        self.list_container.clear_widgets()
        self.list_container.height = 0

        query = (self.search_input.text or '').lower()
        shown = [n for n in self.notes
                 if not query or query in (n.get('text') or '').lower()]

        if not shown:
            empty = Label(text='Заметок пока нет — нажмите красную кнопку',
                          size_hint_y=None, height=40, color=(0, 0, 0, 1),
                          font_size='16sp')
            self.list_container.add_widget(empty)
            self.list_container.height = 40
            return

        for i, note in enumerate(shown):
            color = CARD_COLORS[i % len(CARD_COLORS)]
            row = BoxLayout(orientation='horizontal', size_hint_y=None,
                            height=76, spacing=4)
            row.canvas.before.clear()
            with row.canvas.before:
                from kivy.graphics import Color, Rectangle
                Color(*color)
                rect = Rectangle(pos=row.pos, size=row.size)
            row.bind(pos=lambda w, v, r=rect: (
                setattr(r, 'pos', w.pos), setattr(r, 'size', w.size)))

            text_col = BoxLayout(orientation='vertical', size_hint_x=0.62,
                                 padding=[6, 4])
            lbl_date = Label(text=_fmt_ts(note['ts']),
                             halign='left', valign='middle',
                             color=(0, 0, 0, 1), font_size='15sp',
                             bold=True, size_hint_y=0.45)
            lbl_date.bind(size=lambda w, v: setattr(
                w, 'text_size', (w.width, None)))
            txt = note.get('text') or '(без текста)'
            lbl_text = Label(text=txt, halign='left', valign='middle',
                             color=(0, 0, 0, 1), font_size='14sp',
                             size_hint_y=0.55)
            lbl_text.bind(size=lambda w, v: setattr(
                w, 'text_size', (w.width, None)))
            text_col.add_widget(lbl_date)
            text_col.add_widget(lbl_text)

            btn_play = Button(text='▶', size_hint_x=0.20,
                              background_normal='',
                              background_color=BTN_BLUE,
                              color=(1, 1, 1, 1), font_size='18sp')
            btn_play.bind(on_press=lambda w, n=note: self.play_note(n))

            btn_share = Button(text='↗', size_hint_x=0.18,
                               background_normal='',
                               background_color=BTN_ORANGE,
                               color=(1, 1, 1, 1), font_size='18sp')
            btn_share.bind(on_press=lambda w, n=note: self.share_note(n))

            row.add_widget(text_col)
            row.add_widget(btn_play)
            row.add_widget(btn_share)
            self.list_container.add_widget(row)

        self.list_container.height = len(shown) * (76 + 6)

    # ---------- воспроизведение ----------

    def play_note(self, note):
        try:
            if self.current_sound:
                try:
                    self.current_sound.stop()
                    self.current_sound.unload()
                except Exception:
                    pass
                self.current_sound = None
            path = note.get('path')
            if not path or not os.path.exists(path):
                self.status.text = 'Файл записи не найден'
                return
            sound = SoundLoader.load(path)
            if not sound:
                self.status.text = 'Не удалось открыть файл для воспроизведения'
                return
            sound.play()
            self.current_sound = sound
            self.status.text = 'Воспроизведение…'
            def done(dt):
                try:
                    if not sound.state == 'play':
                        self.status.text = 'Готов к записи'
                        sound.unload()
                        self.current_sound = None
                except Exception:
                    pass
            Clock.schedule_interval(done, 0.5)
        except Exception as e:
            self.status.text = 'Ошибка воспроизведения: %s' % e

    # ---------- поделиться ----------

    def share_note(self, note):
        try:
            if not IS_ANDROID:
                self.status.text = 'Поделиться можно только на Android'
                return
            from jnius import autoclass, cast
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            uri_str = note.get('uri')
            if uri_str:
                uri = Uri.parse(uri_str)
            else:
                path = note.get('path')
                if not path or not os.path.exists(path):
                    self.status.text = 'Файл записи не найден'
                    return
                uri = Uri.parse('file://' + path)

            intent = Intent()
            intent.setAction(Intent.ACTION_SEND)
            intent.setType('audio/mp4')
            intent.putExtra(Intent.EXTRA_STREAM, cast(
                'android.os.Parcelable', uri))
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            chooser = Intent.createChooser(intent, 'Отправить запись')
            PythonActivity.mActivity.startActivity(chooser)
        except Exception as e:
            self.status.text = 'Ошибка отправки: %s' % e


if __name__ == '__main__':
    SputnikApp().run()
