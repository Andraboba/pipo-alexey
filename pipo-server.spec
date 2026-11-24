# -*- mode: python ; coding: utf-8 -*-
# Сервер для окна на Tauri (папка desktop): тот же main.py, но без pywebview.
# Сборка: build_exe.bat (или: python -m PyInstaller pipo-server.spec --noconfirm).
# Готовый dist\pipo-server.exe вшивается в PipoAlexey.exe при сборке оболочки.
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("web/dist", "web/dist")],
    hiddenimports=collect_submodules("uvicorn") + ["app.api"],
    excludes=["tkinter", "test", "unittest", "pydoc_data", "webview", "clr", "clr_loader", "pythonnet"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pipo-server",
    console=False,      # окно у оболочки; лог — data\pipo.log
    uac_admin=False,    # права администратора наследуются от оболочки
    upx=False,          # UPX часто вызывает ложные срабатывания антивирусов
    debug=False,
    strip=False,
    runtime_tmpdir=None,
)
