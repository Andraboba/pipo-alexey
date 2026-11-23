# -*- mode: python ; coding: utf-8 -*-
# Сборка: build_exe.bat  (или: python -m PyInstaller pipo.spec --noconfirm)
# Результат — один файл dist\PipoAlexey.exe: окно приложения на WebView2 (движок Edge),
# внутри локальный сервер на 127.0.0.1. Данные (сплит, кеши, бэкапы, лог) — в папке data
# рядом с exe, сам запрет — в C:\Zapret (меняется в «Настройках»).
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("webview")
    + ["app.api", "clr", "clr_loader", "pythonnet"]
)
datas = [("web/dist", "web/dist")] + collect_data_files("webview") + collect_data_files("clr_loader") + collect_data_files("pythonnet")
binaries = collect_dynamic_libs("webview") + collect_dynamic_libs("pythonnet") + collect_dynamic_libs("clr_loader")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "test", "unittest", "pydoc_data", "webview.platforms.gtk", "webview.platforms.qt",
              "webview.platforms.cocoa", "webview.platforms.android"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PipoAlexey",
    icon="assets/icon.ico",
    console=False,      # своё окно, без консоли; лог — data\pipo.log
    uac_admin=True,     # Windows сама спросит права администратора при запуске
    upx=False,          # UPX часто вызывает ложные срабатывания антивирусов
    debug=False,
    strip=False,
    runtime_tmpdir=None,
)
