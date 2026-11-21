# -*- coding: utf-8 -*-
import os
import json
import time

from kivy.app import App
from kivy.clock import Clock
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
    ClipDataCls = autoclass('android.content.ClipData')
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

    def
