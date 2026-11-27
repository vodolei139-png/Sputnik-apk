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


class RaiseButton(Button):
    """Кнопка с выпуклостью. База — штатная заливка Kivy с подкраской,
    объёмные кромки рисуются поверх и защищены: если рисунка не удастся,
    кнопка всё равно останется видимой."""

    def __init__(self, base=(0.5, 0.5, 0.5, 1), **kwargs):
        self.base_color = tuple(base)
        kwargs.setdefault('background_color', tuple(base))
        super(RaiseButton, self).__init__(**kwargs)
        try:
            with self.canvas.after:
                self._col_a = Color(1, 1, 1, 0.22)
                self._rect_a = Rectangle()
                self._col_b = Color(0, 0, 0, 0.3)
                self._rect_b = Rectangle()
            self.bind(pos=self._redraw, size=self._redraw, state=self._redraw)
            Clock.schedule_once(self._redraw, 0)
        except Exception as e:
            print('RaiseButton init failed:', e)

    def set_base(self, color):
        self.base_color = tuple(color)
        try:
            self.background_color = self.base_color
            self._redraw()
        except Exception as e:
            print('RaiseButton set_base failed:', e)

    def _redraw(self, *args):
        try:
            pressed = (self.state == 'down')
            if pressed:
                self.background_color = (
                    self.base_color[0] * 0.7,
                    self.base_color[1] * 0.7,
                    self.base_color[2] * 0.7,
                    1)
            else:
                self.background_color = self.base_color
            strip = max(2.0, self.height * 0.12)
            if pressed:
                self._col_a.rgba = (0, 0, 0, 0.35)
                self._rect_a.pos = (self.x, self.y + self.height - strip)
                self._rect_a.size = (self.width, strip)
                self._col_b.rgba = (1, 1, 1, 0.18)
                self._rect_b.pos = (self.x, self.y)
                self._rect_b.size = (self.width, strip)
            else:
                self._col_a.rgba = (1, 1, 1, 0.22)
                self._rect_a.pos = (self.x, self.y + self.height - strip)
                self._rect_a.size = (self.width, strip)
                self._col_b.rgba = (0, 0, 0, 0.3)
                self._rect_b.pos = (self.x, self.y)
                self._rect_b.size = (self.width, strip)
        except Exception as e:
            print('RaiseButton redraw failed:', e)


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
        self.valign = 'top'
        self.bind(width=self._upd, texture_size=self._upd)
        Clock.schedule_once(self._upd, 0)

    def _upd(self, *args):
        if not self.width or self.width <= 0:
            return
        self.text_size = (self.width, None)
        self.height = self.texture_size[1]
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

    def __init__(self,
