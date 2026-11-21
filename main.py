# -*- coding: utf-8 -*-
import os
import json
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, PushMatrix, PopMatrix, Rotate

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
    ClipDataCls = autoclass('android.content.ClipData')
    StringCls = autoclass('java.lang.String')
    ArrayListCls = autoclass('java.util.ArrayList')
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


class WatermarkLabel(Label):
    def __init__(self, angle=-30, **kwargs):
        super(WatermarkLabel, self).__init__(**kwargs)
        self._angle = angle
        with self.canvas.before:
            PushMatrix()
            self._rot = Rotate()
        with self.canvas.after:
            PopMatrix()
        self.bind(pos=self._sync_rot, size=self._sync_rot)

    def _sync_rot(self, *args):
        self._rot.origin = self.center
        self._rot.axis = (0, 0, 1)
        self._rot.angle = self._angle


class WrapLabel(Label):
    def __init__(self, on_layout_change=None, **kwargs):
        super(WrapLabel, self).__init__(**kwargs)
        self._on_layout_change = on_layout_change
        self.size_hint_y = None
        self.halign = 'left'
        self.bind(width=self._upd, texture_size=self._upd)
        Clock.schedule_once(self._upd, 0)

    def _upd(self, *args):
        self.text_size = (self.width, None)
        if self._on_layout_change:
            self._on_layout_change(self.texture_size[1])


def fmt_mmss(total_ms):
    total_sec = int(total_ms // 1000)
    return '{:d}:{:02d}'.format(total_sec // 60, total_sec % 60)


class NoteItem(BoxLayout):
    PALETTE = [
        (1.0, 0.97, 0.6, 1),
        (0.6, 0.93, 0.87, 1),
        (1.0, 0.68, 0.6, 1),
    ]

    def __init__(self, note, index, on_play, on_share, on_delete, **kwargs):
        super(NoteItem, self).__init__(**kwargs)
        self.note = note
        self._armed = False
        self.orientation = 'horizontal'
        self.spacing = 4
        self.padding = (6, 5, 6, 5)
        self.size_hint_y = None
        self.height = 78
        with_bg(self, self.PALETTE[index % len(self.PALETTE)])

        left = BoxLayout(
            orientation='vertical',
            size_hint_x=0.48,
            size_hint_y=None,
            spacing=2,
        )
        left.add_widget(Label(
            text=note.get('date', ''),
            font_name=FONT_BOLD,
            color=(0.1, 0.1, 0.1, 1),
            font_size='13sp',
            size_hint_y=None,
            height=22,
        ))

        def _relayout(text_height):
            new_h = max(78, text_height + 22 + 14)
            if new_h != self.height:
                self.height = new_h

        lbl_text = WrapLabel(
            text=note.get('text') or '(без текста)',
            font_name=FONT_REGULAR,
            color=(0.15, 0.15, 0.15, 1),
            font_size='12sp',
            on_layout_change=_relayout,
        )
        left.add_widget(lbl_text)
        self.add_widget(left)

        right = BoxLayout(orientation='horizontal', size_hint_x=0.52, spacing=3)
        btn_play = Button(
            text='СЛУШАТЬ',
            font_name=FONT_REGULAR,
            font_size='9sp',
            background_color=(0.12, 0.45, 0.85, 1),
        )
        btn_play.bind(on_release=lambda *a: on_play(self.note))
        btn_share = Button(
            text='ОТПРАВИТЬ',
            font_name=FONT_REGULAR,
            font_size='9sp',
            background_color=(0.95, 0.55, 0.05, 1),
        )
        btn_share.bind(on_release=lambda *a: on_share(self.note))
        btn_delete = Button(
            text='УДАЛИТЬ',
            font_name=FONT_REGULAR,
            font_size='9sp',
            background_color=(0.7, 0.15, 0.15, 1),
        )
        btn_delete.bind(on_release=lambda *a: self._delete_tap(on_delete))
        right.add_widget(btn_play)
        right.add_widget(btn_share)
        right.add_widget(btn_delete)
        self.add_widget(right)

        self.btn_delete = btn_delete

    def _delete_tap(self, on_delete):
        if not self._armed:
            self._armed = True
            self.btn_delete.text = 'ТОЧНО?'
            self.btn_delete.background_color = (0.45, 0.05, 0.05, 1)
            Clock.schedule_once(self._disarm, 3)
        else:
            self._armed = False
            on_delete(self.note)

    def _disarm(self, dt):
        self._armed = False
        self.btn_delete.text = 'УДАЛИТЬ'
        self.btn_delete.background_color = (0.7, 0.15, 0.15, 1)


def save_to_music(temp_path):
    filename = 'rec_' + time.strftime('%Y%m%d_%H%M%S') + '.m4a'
    result = {'path': '', 'uri': '', 'note': None}
    if not ANDROID:
        result['path'] = temp_path
        result['note'] = 'no android modules'
        return result

    private_path = os.path.join(
        os.path.dirname(temp_path),
        filename.replace('.m4a', '_p.m4a'))
    try:
        os.rename(temp_path, private_path)
    except Exception:
        private_path = temp_path
    result['path'] = private_path

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
            with open(private_path, 'rb') as f:
                data = f.read()
            out_stream.write(data)
            out_stream.close()
            try:
                up = ContentValues()
                up.put('is_pending', '0')
                resolver.update(uri, up, None, None)
            except Exception as e:
                print('pending update failed:', e)
            result['uri'] = str(uri)
            return result
        except Exception as e:
            result['note'] = 'MediaStore: ' + str(e)[:120]
            return result
    try:
        base = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
        folder = os.path.join(str(base), 'Sputnik')
        if not os.path.isdir(folder):
            os.makedirs(folder)
        target = os.path.join(folder, filename)
        with open(private_path, 'rb') as f:
            data = f.read()
        with open(target, 'wb') as f:
            f.write(data)
        result['path'] = target
        return result
    except Exception as e:
        result['note'] = 'Copy: ' + str(e)[:120]
        return result


class DictaphoneApp(App):
    def __init__(self, **kwargs):
        super(DictaphoneApp, self).__init__(**kwargs)
        self.notes = []
        self.is_recording = False
        self.recorder = None
        self.temp_path = None
        self.rec_start = 0.0
        self.timer_event = None
        self.player = None
        self.play_event = None
        self.load_notes()

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        root = FloatLayout()
        content = BoxLayout(orientation='vertical', padding=10, spacing=8)
        content.size_hint = (1, 1)

        wm_center = WatermarkLabel(
            text='SPUTNIK',
            font_name=FONT_BOLD,
            font_size='70sp',
            color=(0.05, 0.2, 0.5, 0.05),
        )
        root.add_widget(wm_center)

        wm_corner = WatermarkLabel(
            text='SPUTNIK • v1.0',
            font_name=FONT_REGULAR,
            font_size='14sp',
            color=(0.05, 0.2, 0.5, 0.12),
            size_hint=(1, None),
            height=30,
        )

        def _sync_corner(inst, w):
            inst.text_size = (w, inst.height)

        wm_corner.bind(width=_sync_corner)
        wm_corner.pos_hint = {'x': 0.02, 'y': 0.005}
        root.add_widget(wm_corner)

        header = with_bg(Label(
            text='ДИКТОФОН С ЗАМЕТКАМИ',
            font_name=FONT_BOLD,
            color=(1, 1, 1, 1),
            font_size='22sp',
            size_hint_y=None,
            height=52,
        ), (0.05, 0.4, 0.75, 1))
        content.add_widget(header)

        self.lbl_status = Label(
            text='Готов к записи',
            font_name=FONT_REGULAR,
            color=(0.6, 0.1, 0.1, 1),
            font_size='12sp',
            halign='left',
            valign='middle',
            size_hint_y=None,
            height=84,
        )

        def _sync_status(inst, w):
            inst.text_size = (w, inst.height)

        self.lbl_status.bind(width=_sync_status)
        content.add_widget(self.lbl_status)

        if not ANDROID and ANDROID_ERR:
            self.show_status('Сборка без Android-модулей: ' + ANDROID_ERR)

        self.btn_record = Button(
            text='НАЧАТЬ ЗАПИСЬ',
            font_name=FONT_BOLD,
            font_size='20sp',
            background_color=(0.85, 0.2, 0.2, 1),
            size_hint_y=None,
            height=70,
        )
        self.btn_record.bind(on_release=self.toggle_recording)
        content.add_widget(self.btn_record)

        content.add_widget(Label(
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
        content.add_widget(self.txt_note)

        self.txt_search = TextInput(
            hint_text='Поиск по заметкам',
            font_name=FONT_REGULAR,
            multiline=False,
            size_hint_y=None,
            height=48,
        )
        self.txt_search.bind(text=self.on_search)
        content.add_widget(self.txt_search)

        self.list_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
        self.list_container.bind(minimum_height=self.list_container.setter('height'))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.list_container)
        content.add_widget(scroll)

        self.refresh_notes_ui()

        root.add_widget(content)

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

    def stop_play(self):
        if self.play_event:
            self.play_event.cancel()
            self.play_event = None
        if self.player:
            try:
                if self.player.isPlaying():
                    self.player.stop()
                self.player.release()
            except Exception as e:
                print('player release failed:', e)
            self.player = None

    def tick_play(self, dt):
        if not self.player:
            return
        try:
            pos = self.player.getCurrentPosition()
            dur = self.player.getDuration()
            if self.player.isPlaying() and pos < dur - 50:
                self.show_status('Воспроизведение: {} / {}'.format(
                    fmt_mmss(pos), fmt_mmss(dur)))
            else:
                self.stop_play()
                self.show_status('Воспроизведение завершено')
        except Exception:
            self.stop_play()
            self.show_status('Конец воспроизведения')

    def delete_note(self, note):
        uri_str = note.get('uri', '')
        if uri_str and uri_str != 'None' and ANDROID:
            try:
                resolver = PythonActivity.mActivity.getContentResolver()
                resolver.delete(UriCls.parse(uri_str), None, None)
            except Exception as e:
                print('delete uri failed:', e)
        path = note.get('path', '')
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print('delete file failed:', e)
        if note in self.notes:
            self.notes.remove(note)
        self.save_notes()
        self.refresh_notes_ui()
        self.show_status('Заметка удалена')

    def stop_timer(self):
        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None

    def tick_timer(self, dt):
        elapsed = int(time.time() - self.rec_start)
        self.lbl_status.text = 'Идёт запись: {:02d}:{:02d}'.format(elapsed // 60, elapsed % 60)

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
            self.rec_start = time.time()
            self.btn_record.text = 'ОСТАНОВИТЬ'
            self.btn_record.background_color = (0.1, 0.6, 0.3, 1)
            self.tick_timer(0)
            self.timer_event = Clock.schedule_interval(self.tick_timer, 1)
        except Exception as e:
            self.stop_timer()
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
            self.stop_timer()
            self.is_recording = False
            self.btn_record.text = 'НАЧАТЬ ЗАПИСЬ'
            self.btn_record.background_color = (0.85, 0.2, 0.2, 1)
            self.publish_record()
        except Exception as e:
            self.stop_timer()
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
            self.show_status('Сохранено только внутри приложения: ' + result['note'])
        else:
            self.show_status('Запись сохранена (Music/Sputnik)')

    def play_note(self, note):
        if not ANDROID:
            self.show_status('Воспроизведение доступно на Android')
            return
        uri_str = note.get('uri', '')
        path = note.get('path', '')
        errors = []

        self.stop_play()

        def start_with(p):
            p.prepare()
            p.start()
            self.player = p
            self.play_event = Clock.schedule_interval(self.tick_play, 0.5)
            self.tick_play(0)
            return True

        def try_path():
            if not path or not os.path.exists(path):
                return None
            try:
                p = MediaPlayer()
                p.setDataSource(path)
                return start_with(p)
            except Exception as e:
                errors.append('path: ' + str(e)[:60])
                return None

        def try_pfd():
            if not uri_str or uri_str == 'None':
                return None
            try:
                resolver = PythonActivity.mActivity.getContentResolver()
                pfd = resolver.openFileDescriptor(UriCls.parse(uri_str), 'r')
                p = MediaPlayer()
                p.setDataSource(pfd.getFileDescriptor())
                return start_with(p)
            except Exception as e:
                errors.append('pfd: ' + str(e)[:60])
                return None

        def try_copy():
            if not uri_str or uri_str == 'None':
                return None
            try:
                resolver = PythonActivity.mActivity.getContentResolver()
                src = resolver.openInputStream(UriCls.parse(uri_str))
                try:
                    data = bytes(src.readAllBytes())
                except Exception:
                    buf = bytearray()
                    while True:
                        c = src.read()
                        if c == -1 or c is None:
                            break
                        buf.append(c)
                    data = bytes(buf)
                src.close()
                tmp = os.path.join(self.user_data_dir, 'play_tmp.m4a')
                with open(tmp, 'wb') as f:
                    f.write(data)
                p = MediaPlayer()
                p.setDataSource(tmp)
                return start_with(p)
            except Exception as e:
                errors.append('copy: ' + str(e)[:60])
                return None

        started = try_path() or try_pfd() or try_copy()
        if not started:
            self.show_status('Ошибка воспроизведения: ' + (errors[0] if errors else 'нет файла'))
            print('play errors:', errors)

    def share_note(self, note):
        if not ANDROID:
            self.show_status('Отправка доступна на Android')
            return
        uri_str = note.get('uri', '')
        if uri_str and uri_str != 'None':
            uri_obj = UriCls.parse(uri_str)
        else:
            path = note.get('path', '')
            if not path or not os.path.exists(path):
                self.show_status('Файл записи не найден')
                return
            uri_obj = UriCls.fromFile(FileCls(path))
        activity = PythonActivity.mActivity
        errors = []
        attached = []

        intent = IntentCls()
        intent.setAction(IntentCls.ACTION_SEND)
        intent.setType('audio/mp4')
        intent.addFlags(1)

        try:
            resolver = cast('android.content.ContentResolver',
                            activity.getContentResolver())
            label = cast('java.lang.CharSequence', StringCls('запись'))
            clip = ClipDataCls.newUri(resolver, label, uri_obj)
            intent.setClipData(clip)
            attached.append('ClipData')
        except Exception as e:
            errors.append('ClipData: ' + str(e)[:90])

        try:
            arr = ArrayListCls()
            arr.add(cast('android.os.Parcelable', uri_obj))
            intent.putParcelableArrayListExtra(IntentCls.EXTRA_STREAM, arr)
            attached.append('ArrayList')
        except Exception as e:
            errors.append('ArrayList: ' + str(e)[:90])

        try:
            intent.putExtra(IntentCls.EXTRA_STREAM,
                            cast('android.os.Parcelable', uri_obj))
            attached.append('putExtra')
        except Exception as e:
            errors.append('putExtra: ' + str(e)[:90])

        if not attached:
            print('share errors:', errors)
            self.show_status('Ошибка отправки: ' + '; '.join(errors)[:300])
            return

        launched = False

        try:
            chooser_title = cast('java.lang.CharSequence',
                                 StringCls('Отправить запись'))
            chooser = IntentCls.createChooser(intent, chooser_title)
        except Exception as e:
            errors.append('chooser: ' + str(e)[:90])
            chooser = None

        for send_intent in ([chooser, intent] if chooser else [intent]):
            try:
                activity.startActivity(send_intent)
                launched = True
                break
            except Exception as e:
                errors.append('start: ' + str(e)[:90])

        if launched:
            self.show_status('Меню отправки [mp4] (' + ', '.join(attached) + ')')
            return

        print('share errors:', errors)
        fallback = '; '.join(errors)[:300]
        try:
            view_intent = IntentCls(IntentCls.ACTION_VIEW)
            view_intent.setDataAndType(uri_obj, 'audio/mp4')
            view_intent.addFlags(1)
            activity.startActivity(view_intent)
            self.show_status('ОТКРЫЛ ПЛЕЕР. Ошибки: ' + fallback)
        except Exception:
            self.show_status('Ошибка отправки: ' + (fallback or 'нет файла'))

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
            empty_lbl = Label(
                text='Заметок пока нет — нажмите кнопку Начать запись',
                font_name=FONT_REGULAR,
                color=(0.45, 0.45, 0.45, 1),
                font_size='13sp',
                size_hint_y=None,
                height=44,
                halign='center',
            )
            empty_lbl.bind(width=lambda inst, w: setattr(
                inst, 'text_size', (w, inst.height)))
            self.list_container.add_widget(empty_lbl)
            return
        for index, note in enumerate(notes):
            self.list_container.add_widget(
                NoteItem(note, index, self.play_note, self.share_note, self.delete_note)
            )

    def show_status(self, text):
        self.lbl_status.text = text
        print('[STATUS]', text)


if __name__ == '__main__':
    DictaphoneApp().run()
