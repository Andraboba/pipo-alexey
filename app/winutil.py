"""Мелкие обёртки над Windows: запуск утилит без окон, права, процессы, версии exe."""
from __future__ import annotations

import ctypes
import csv
import io
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

CREATE_NO_WINDOW = 0x08000000


def run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    """Зависшая утилита — TimeoutError (это OSError): его уже ловят API и подбор, а TimeoutExpired — никто."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            # системные утилиты пишут в OEM-кодировке консоли
            encoding="oem" if sys.platform == "win32" else "utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"{Path(args[0]).name} не ответил за {timeout:g} с") from e


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def pid_alive(pid: int) -> bool:
    """Жив ли процесс с этим PID (для сервера, которым управляет окно-оболочка)."""
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def process_running(image: str) -> bool:
    out = run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"]).stdout
    for row in csv.reader(io.StringIO(out)):
        if row and row[0].lower() == image.lower():
            return True
    return False


def kill_process(image: str, force: bool = True) -> None:
    args = ["taskkill", "/IM", image]
    if force:
        args.append("/F")
    run(args)


def launch_unelevated(exe: Path) -> None:
    """Запуск GUI-программы от обычного пользователя, даже если мы под админом.

    explorer.exe всегда работает без повышения и запускает файл от своего имени,
    поэтому трей-приложение не получит лишних прав.
    """
    if is_admin():
        subprocess.Popen(["explorer.exe", str(exe)], creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=0x00000008)  # DETACHED_PROCESS


def open_url_unelevated(url: str) -> None:
    subprocess.Popen(["explorer.exe", url], creationflags=CREATE_NO_WINDOW)


def file_version(path: Path) -> str | None:
    """ProductVersion из ресурсов exe, например '1.11.4.0'."""
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
            return None

        class VSFixed(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint32) for n in (
                "sig", "struc", "fv_ms", "fv_ls", "pv_ms", "pv_ls", "mask", "flags", "os", "type", "sub", "d_ms", "d_ls")]

        fi = VSFixed.from_address(ptr.value)
        return f"{fi.pv_ms >> 16}.{fi.pv_ms & 0xFFFF}.{fi.pv_ls >> 16}.{fi.pv_ls & 0xFFFF}"
    except (AttributeError, OSError, ValueError):
        return None


# SetThreadExecutionState: не давать Windows уснуть, пока идёт долгая задача (действует на поток)
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def keep_awake() -> Iterator[None]:
    """Компьютер не уйдёт в сон, пока поток внутри блока. Экран гаснуть может."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    except (AttributeError, OSError):
        pass
    try:
        yield
    finally:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        except (AttributeError, OSError):
            pass
