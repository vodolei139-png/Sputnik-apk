# -*- coding: utf-8 -*-
"""Спутник — диктофон с заметками. Записи: Music/Sputnik (общедоступная папка)."""
import os
import json
import time
import shutil
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

Window.clearcolor = (1, 1, 1, 1)

# --- Разрешения Android -------------------------------------------------
try:
    from android.permissions import request_permissions, Permission

    def _request_permissions():
        try:
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception as e:
            print('permissions error:', e)
except ImportError:
    def _request_permissions():
        pass

# --- JNI классы ---------------------------------------------------------
try:
    from jnius import autoclass

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    ContentValues = autoclass('android.content.ContentValues')
    MediaStoreAudio = autoclass('android.provider.MediaStore$Audio$Media')
    Intent = autoclass('android.content.Intent')
    UriCls = autoclass('android.net.Uri')
    FileCls = autoclass('java.io.File')
    Environment = autoclass('android.os.Environment')
    MediaPlayer = autoclass('android.media.MediaPlayer')
    Build = autoclass('android.os.Build$VERSION')

    HAVE_JNIUS = True
except Exception as e:
    print('jnius import failed:', e)
    HAVE_JNIUS = False


def get_activity():
    try:
        return PythonActivity.mCurrentActivity
    except Exception:
        return PythonActivity.mActivity


def get_context():
    return PythonActivity.mActivity


class SputnikApp(App):
    title = 'Спутник'

    # ------------------------------------------------------------------
    def build(self):
        self.recorder = None
        self.player = None
        self.recording = False
        self.temp_path = None
        self.notes = []

        _request_permissions()

        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))

        header = Label(text='ДИКТОФОН С ЗАМЕТКАМИ', bold=True,
                       font_size='24sp', color=(1, 1, 1, 1), size_hint_y=None,
                       height=dp(50))
        self._style_header(header)
        root.add_widget(header)

        self.status = Label(text='Готов к записи', font_size='16sp',
                            size_hint_y=None, height=dp(30),
                            color=(0.2, 0.2, 0.2, 1))
        root.add_widget(self.status)

        self.folder_hint = Label(text='Записи: Music/Sputnik (общедоступная папка)',
                                 font_size='13sp', size_hint_y=None,
                                 height=dp(24), color=(0.4, 0.4, 0.4, 1))
        root.add_widget(self.folder_hint)

        self.record_btn = Button(text='НАЧАТЬ ЗАПИСЬ', font_size='22sp',
                                 size_hint_y=None, height=dp(70),
                                 background_color=(0.86, 0.15, 0.15, 1),
                                 color=(1, 1, 1, 1), bold=True)
        self.record_btn.bind(on_press=self.toggle_record)
        root.add_widget(self.record_btn)

        self.note_input = TextInput(hint_text='Текст заметки (можно оставить пустым)',
                                    size_hint_y=None, height=dp(55),
                                    font_size='16sp',
                                    background_color=(0.9, 0.95, 1, 1))
        root.add_widget(self.note_input)

        self.search_input = TextInput(hint_text='Поиск по заметкам',
                                      size_hint_y=None, height=dp(45),
                                      font_size='16sp',
                                      background_color=(0.9, 0.95, 1, 1))
        self.search_input.bind(text=lambda *a: self.rebuild_list())
        root.add_widget(self.search_input)

        self.scroll = ScrollView()
        self.notes_grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.notes_grid.bind(minimum_height=self.notes_grid.setter('height'))
        self.scroll.add_widget(self.notes_grid)
        root.add_widget(self.scroll)

        self.load_notes()
        self.rebuild_list()
        return root

    def _style_header(self, label):
        # синяя шапка: рисуем цветной фон через canvas
        from kivy.graphics import Color, Rectangle

        def upd(*a):
            label.canvas.before.clear()
            with label.canvas.before:
                Color(0.05, 0.35, 0.75, 1)
                Rectangle(pos=label.pos, size=label.size)
        label.bind(pos=upd, size=upd)

    # ------------------------------------------------------------------
    def notes_file(self):
        return os.path.join(self.user_data_dir, 'notes.json')

    def load_notes(self):
        try:
            with open(self.notes_file(), encoding='utf-8') as f:
                self.notes = json.load(f)
        except Exception:
            self.notes = []

    def save_notes(self):
        try:
            with open(self.notes_file(), 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self.set_status('Не удалось сохранить список заметок: %s' % e)

    def set_status(self, text, error=False):
        print('STATUS:', text)
        self.status.text = text
        self.status.color = (0.7, 0.05, 0.05, 1) if error else (0.2, 0.2, 0.2, 1)

    # ------------------------------------------------------------------
    def toggle_record(self, *args):
        try:
            if not HAVE_JNIUS:
                self.set_status('Запись доступна только на Android', error=True)
                return
            if not self.recording:
                self.start_recording()
            else:
                self.stop_recording()
        except Exception as e:
            traceback.print_exc()
            self._safe_release()
            self.recording = False
            self.record_btn.text = 'НАЧАТЬ ЗАПИСЬ'
            self.record_btn.background_color = (0.86, 0.15, 0.15, 1)
            self.set_status('Ошибка записи: %s' % e, error=True)

    def _safe_release(self):
        if self.recorder is not None:
            try:
                self.recorder.release()
            except Exception:
                pass
            self.recorder = None

    def start_recording(self):
        temp = os.path.join(self.user_data_dir, 'tmp_rec.m4a')
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except Exception:
                pass
        mr = MediaRecorder()
        mr.setAudioSource(MediaRecorder.AudioSource.MIC)
        mr.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        mr.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        mr.setAudioSamplingRate(44100)
        mr.setAudioEncodingBitRate(128000)
        mr.setOutputFile(temp)
        mr.prepare()
        mr.start()
        self.recorder = mr
        self.temp_path = temp
        self.recording = True
        self.record_btn.text = 'ОСТАНОВИТЬ ЗАПИСЬ'
        self.record_btn.background_color = (0.1, 0.65, 0.25, 1)
        self.set_status('Идёт запись…')

    def stop_recording(self):
        fname = 'rec_%s.m4a' % time.strftime('%Y%m%d_%H%M%S')
        src = self.temp_path
        self.recorder.stop()
        self._safe_release()
        self.recording = False
        self.record_btn.text = 'НАЧАТЬ ЗАПИСЬ'
        self.record_btn.background_color = (0.86, 0.15, 0.15, 1)

        src_value, reason = self.save_to_public(src, fname)
        if src_value:
            note = {
                'time': time.strftime('%d.%m.%Y %H:%M'),
                'text': self.note_input.text or '',
                'src': src_value,
            }
            self.notes.insert(0, note)
            self.save_notes()
            self.note_input.text = ''
            self.rebuild_list()
            self.set_status('Запись сохранена (Music/Sputnik)')
        else:
            self.set_status('Записан во внутреннюю папку. Причина: %s' % (reason or 'неизвестно'),
                            error=True)

    def save_to_public(self, src, fname):
        """Возвращает (src_value, None) или (None, причина_ошибки)."""
        try:
            sdk = int(Build.SDK_INT)
        except Exception:
            sdk = 29
        try:
            if sdk >= 29:
                activity = get_activity()
                resolver = activity.getContentResolver()
                cv = ContentValues()
                cv.put('_display_name', fname)
                cv.put('mime_type', 'audio/mp4')
                cv.put('relative_path', 'Music/Sputnik')
                uri = resolver.insert(MediaStoreAudio.EXTERNAL_CONTENT_URI, cv)
                if uri is None:
                    return None, 'система не вернула URI'
                out = resolver.openOutputStream(uri)
                if out is None:
                    return None, 'не удалось открыть поток записи'
                with open(src, 'rb') as f:
                    data = f.read()
                out.write(data)
                out.flush()
                out.close()
                try:
                    os.remove(src)
                except Exception:
                    pass
                return uri.toString(), None
            else:
                base = Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_MUSIC)
                sdir = FileCls(base, 'Sputnik')
                if not sdir.exists():
                    sdir.mkdirs()
                dst = FileCls(sdir, fname)
                shutil.move(src, dst.getAbsolutePath())
                return dst.getAbsolutePath(), None
        except Exception as e:
            traceback.print_exc()
            return None, str(e)

    # ------------------------------------------------------------------
    def play_note(self, src, *args):
        try:
            if not HAVE_JNIUS:
                return
            if self.player is not None:
                try:
                    self.player.release()
                except Exception:
                    pass
                self.player = None
            player = MediaPlayer()
            if src.startswith('content:'):
                player.setDataSource(get_context(), UriCls.parse(src))
            else:
                player.setDataSource(src)
            player.prepare()
            player.start()
            self.player = player
            self.set_status('Воспроизведение…')
            self.check_play_finished()
        except Exception as e:
            traceback.print_exc()
            self.set_status('Ошибка воспроизведения: %s' % e, error=True)

    def check_play_finished(self):
        def _check(*a):
            if self.player is not None:
                try:
                    if not self.player.isPlaying():
                        self.player.release()
                        self.player = None
                        self.set_status('Готов к записи')
                        return
                except Exception:
                    return
            from kivy.clock import Clock
            Clock.schedule_once(_check, 0.5)
        from kivy.clock import Clock
        Clock.schedule_once(_check, 0.5)

    def share_note(self, src, *args):
        try:
            if not HAVE_JNIUS:
                return
            activity = get_activity()
            i = Intent()
            i.setAction(Intent.ACTION_SEND)
            i.setType('audio/mp4')
            if src.startswith('content:'):
                i.putExtra(Intent.EXTRA_STREAM, UriCls.parse(src))
            else:
                i.putExtra(Intent.EXTRA_STREAM, UriCls.fromFile(FileCls(src)))
            i.addFlags(0x1)  # FLAG_GRANT_READ_URI_PERMISSION
            activity.startActivity(Intent.createChooser(i, 'Поделиться записью'))
        except Exception as e:
            traceback.print_exc()
            self.set_status('Ошибка отправки: %s' % e, error=True)

    # ------------------------------------------------------------------
    def rebuild_list(self, *args):
        query = (self.search_input.text or '').strip().lower() if hasattr(self, 'search_input') else ''
        self.notes_grid.clear_widgets()
        colors = [
            (1.0, 0.96, 0.75, 1),   # жёлтый
            (0.78, 0.93, 0.93, 1),  # бирюзовый
            (1.0, 0.83, 0.77, 1),   # коралловый
        ]
        shown = 0
        for idx, note in enumerate(self.notes):
            text = (note.get('text') or '').lower()
            if query and query not in text:
                continue
            shown += 1
            row = BoxLayout(size_hint_y=None, height=dp(72), spacing=dp(4))
            lbl = Label(text='%s\n%s' % (note.get('time', ''), note.get('text') or '(без текста)'),
                        font_size='15sp', color=(0.1, 0.1, 0.1, 1), halign='left',
                        valign='middle', size_hint_x=0.62)
            bg_color = colors[idx % len(colors)]

            from kivy.graphics import Color, Rectangle

            def upd(widget, c):
                def _u(*a):
                    widget.canvas.before.clear()
                    with widget.canvas.before:
                        Color(*c)
                        Rectangle(pos=widget.pos, size=widget.size)
                return _u
            lbl.bind(pos=upd(lbl, bg_color), size=upd(lbl, bg_color))
            lbl.bind(texture_size=lambda inst, val: setattr(inst, 'text_size', inst.size))

            play_btn = Button(text='Слушать', font_size='13sp', bold=True,
                              size_hint_x=0.20,
                              background_color=(0.1, 0.4, 0.8, 1))
            play_btn.bind(on_press=lambda inst, s=note['src']: self.play_note(s))

            share_btn = Button(text='Отправить', font_size='12sp', bold=True,
                               size_hint_x=0.18,
                               background_color=(0.95, 0.5, 0.1, 1))
            share_btn.bind(on_press=lambda inst, s=note['src']: self.share_note(s))

            row.add_widget(lbl)
            row.add_widget(play_btn)
            row.add_widget(share_btn)
            self.notes_grid.add_widget(row)

        if shown == 0:
            msg = Label(text='Заметок пока нет — нажмите красную кнопку',
                        font_size='16sp', color=(0.3, 0.3, 0.3, 1),
                        size_hint_y=None, height=dp(40))
            self.notes_grid.add_widget(msg)

    def on_stop(self):
        self._safe_release()
        if self.player is not None:
            try:
                self.player.release()
            except Exception:
                pass


if __name__ == '__main__':
    SputnikApp().run()
