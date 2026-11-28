[app]

title = MICROFON
package.name = sputnik
package.domain = org.vodolei
source.dir = .
source.include_exts = py,png,jpg,kv,txt,ttf
version = 1.2
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png

requirements = python3,kivy,pyjnius

orientation = portrait

fullscreen = 0

android.permissions = RECORD_AUDIO
android.api = 31
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = True

log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
