"""Работа с установленным запретом (сборка Flowseal zapret-discord-youtube).

Всё совместимо с service.bat: та же служба `zapret`, тот же ключ реестра со
стратегией, тот же формат utils/game_filter.enabled и режимов ipset-all.txt.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import winutil
from .settings import write_text_atomic

SERVICE = "zapret"
STRATEGY_REG_KEY = r"SYSTEM\CurrentControlSet\Services\zapret"
STRATEGY_REG_VALUE = "zapret-discord-youtube"

PLACEHOLDER_IP = "203.0.113.113/32"
PLACEHOLDER_DOMAIN = "domain.example.abc"
# порт-заглушка, которую service.bat подставляет при выключенном игровом фильтре
GAME_FILTER_OFF_PORT = "12"
DEFAULT_GAME_RANGE = "1024-65535"


# ---------- версия и стратегии ----------

def local_version(zdir: Path) -> str | None:
    try:
        m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', (zdir / "service.bat").read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    try:
        return (zdir / "version.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _natural_key(name: str):
    # как в service.bat: числа дополняются нулями до 8 знаков и сравниваются как строки
    return re.sub(r"\d+", lambda m: m.group(0).zfill(8), name).lower()


def list_strategies(zdir: Path) -> list[str]:
    """Имена .bat-стратегий без расширения, как их показывает service.bat."""
    names = [p.stem for p in zdir.glob("*.bat") if not p.name.lower().startswith("service")]
    return sorted(names, key=_natural_key)


# ---------- игровой фильтр ----------

@dataclass
class GameFilter:
    mode: str = "disabled"  # disabled | all | tcp | udp
    tcp: str = DEFAULT_GAME_RANGE
    udp: str = DEFAULT_GAME_RANGE

    @property
    def tcp_value(self) -> str:
        return self.tcp if self.mode in ("all", "tcp") else GAME_FILTER_OFF_PORT

    @property
    def udp_value(self) -> str:
        return self.udp if self.mode in ("all", "udp") else GAME_FILTER_OFF_PORT

    def to_dict(self) -> dict:
        return asdict(self)


_RANGE_ITEM = re.compile(r"^[1-9]\d{0,4}(-[1-9]\d{0,4})?$")


def validate_range(value: str) -> str | None:
    value = (value or "").replace(" ", "")
    if not value:
        return None
    for item in value.split(","):
        if not _RANGE_ITEM.match(item):
            return None
        a, _, b = item.partition("-")
        start, end = int(a), int(b or a)
        if start > 65535 or end > 65535 or start > end:
            return None
    return value


def game_filter_file(zdir: Path) -> Path:
    return zdir / "utils" / "game_filter.enabled"


def read_game_filter(zdir: Path) -> GameFilter:
    gf = GameFilter()
    try:
        text = game_filter_file(zdir).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return gf
    mode = "disabled"
    for raw in text.splitlines():
        key, _, val = raw.strip().partition("=")
        key, val = key.strip().lower(), val.strip()
        if key == "mode":
            mode = val.lower()
        elif key == "all":
            mode = "all"
        elif key in ("tcp", "udp"):
            if not val:
                mode = key
            elif validate_range(val):
                setattr(gf, key, validate_range(val))
    gf.mode = mode if mode in ("all", "tcp", "udp") else "disabled"
    return gf


def write_game_filter(zdir: Path, gf: GameFilter) -> None:
    write_text_atomic(game_filter_file(zdir), f"mode={gf.mode}\ntcp={gf.tcp}\nudp={gf.udp}\n")


# ---------- режим IPSet ----------

def ipset_all(zdir: Path) -> Path:
    return zdir / "lists" / "ipset-all.txt"


def ipset_mode(zdir: Path) -> str:
    """loaded | none | any — так же, как считает service.bat."""
    try:
        text = ipset_all(zdir).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "any"
    if not text:
        return "any"
    return "none" if PLACEHOLDER_IP in text else "loaded"


# ---------- разбор .bat ----------

class StrategyError(ValueError):
    pass


def extract_winws_command(bat_text: str) -> str:
    """Аргументы winws.exe из строки `start ... "%BIN%winws.exe" ... ^`."""
    parts: list[str] = []
    capture = False
    for line in bat_text.splitlines():
        s = line.strip()
        if not capture:
            low = s.lower()
            idx = low.find("winws.exe")
            if idx < 0 or not low.startswith("start"):
                continue
            capture = True
            s = s[idx + len("winws.exe"):]
            if s.startswith('"'):
                s = s[1:]
        cont = s.endswith("^")
        if cont:
            s = s[:-1]
        if s.strip():
            parts.append(s.strip())
        if not cont:
            break
    if not capture:
        raise StrategyError("в файле нет строки запуска winws.exe")
    return " ".join(parts)


def _cmd_unescape(s: str) -> str:
    """Снимаем экранирование cmd (^x -> x) вне кавычек."""
    out, in_quote, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == '"':
            in_quote = not in_quote
        elif c == "^" and not in_quote and i + 1 < len(s):
            i += 1
            c = s[i]
        out.append(c)
        i += 1
    return "".join(out)


def _split_args(s: str) -> list[str]:
    tokens, cur, in_quote, has = [], [], False, False
    for c in s:
        if c == '"':
            in_quote = not in_quote
            cur.append(c)
            has = True
        elif c.isspace() and not in_quote:
            if has:
                tokens.append("".join(cur))
            cur, has = [], False
        else:
            cur.append(c)
            has = True
    if has:
        tokens.append("".join(cur))
    return tokens


def build_args(zdir: Path, strategy: str, gf: GameFilter) -> list[str]:
    if strategy not in list_strategies(zdir):  # только .bat из папки запрета: «..\x» в реестр службы не попадёт
        raise StrategyError(f"нет стратегии «{strategy}» в {zdir}")
    bat = zdir / f"{strategy}.bat"
    try:
        text = bat.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise StrategyError(f"не найдена стратегия {bat.name}") from e
    cmd = extract_winws_command(text)
    root = str(zdir).rstrip("\\/") + "\\"
    values = {
        "BIN": root + "bin\\",
        "LISTS": root + "lists\\",
        "GAMEFILTER": gf.tcp_value if gf.mode != "udp" else gf.udp_value,
        "GAMEFILTERTCP": gf.tcp_value,
        "GAMEFILTERUDP": gf.udp_value,
    }
    cmd = cmd.replace("%~dp0", root)

    def sub(m: re.Match) -> str:
        name = m.group(1).upper()
        if name not in values:
            raise StrategyError(f"неизвестная переменная %{m.group(1)}% в {bat.name}")
        return values[name]

    cmd = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", sub, cmd)
    cmd = _cmd_unescape(cmd)
    args = []
    for tok in _split_args(cmd):
        plain = tok.replace('"', "")
        # кавычки нужны только путям с пробелами; иначе пишем как service.bat
        args.append(plain if not any(ch.isspace() for ch in plain) else tok)
    return args


def winws_exe(zdir: Path) -> Path:
    return zdir / "bin" / "winws.exe"


def build_bin_path(zdir: Path, strategy: str, gf: GameFilter) -> str:
    return f'"{winws_exe(zdir)}" ' + " ".join(build_args(zdir, strategy, gf))


# ---------- служба ----------

_STATES = {1: "stopped", 2: "start_pending", 3: "stop_pending", 4: "running", 5: "continue_pending", 6: "pause_pending", 7: "paused"}


def service_state(name: str = SERVICE) -> str | None:
    """None — служба не установлена."""
    r = winutil.run(["sc", "query", name])
    m = re.search(r"STATE\s*:\s*(\d+)", r.stdout)
    if not m:
        return None
    return _STATES.get(int(m.group(1)), "unknown")


def installed_strategy() -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, STRATEGY_REG_KEY) as k:
            return str(winreg.QueryValueEx(k, STRATEGY_REG_VALUE)[0])
    except OSError:
        return None


def _set_installed_strategy(strategy: str) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, STRATEGY_REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, STRATEGY_REG_VALUE, 0, winreg.REG_SZ, strategy)


class ServiceError(RuntimeError):
    pass


def _check(r, what: str) -> None:
    if r.returncode != 0:
        msg = (r.stdout + r.stderr).strip().splitlines()
        raise ServiceError(f"{what}: {msg[-1] if msg else 'код ' + str(r.returncode)}")


def _wait_state(want: str, timeout: float = 15) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if service_state() == want:
            return True
        time.sleep(0.4)
    return service_state() == want


def tcp_timestamps_enable() -> None:
    """Как :tcp_enable в service.bat — нужно части стратегий."""
    out = winutil.run(["netsh", "interface", "tcp", "show", "global"]).stdout.lower()
    if not any("timestamps" in l and "enabled" in l for l in out.splitlines()):
        winutil.run(["netsh", "interface", "tcp", "set", "global", "timestamps=enabled"])


def autostart_enabled(name: str = SERVICE) -> bool | None:
    """True — служба стартует с Windows (AUTO_START), None — службы нет."""
    r = winutil.run(["sc", "qc", name])
    m = re.search(r"START_TYPE\s*:\s*(\d+)", r.stdout)
    if not m:
        return None
    return int(m.group(1)) == 2


def set_autostart(enabled: bool) -> None:
    if service_state() is None:
        raise ServiceError("служба не установлена")
    _check(winutil.run(["sc", "config", SERVICE, "start=", "auto" if enabled else "demand"]), "sc config")


def install_service(zdir: Path, strategy: str, start: bool, autostart: bool | None = None) -> None:
    """autostart=None — для новой службы выключен, для существующей не меняется."""
    if not winws_exe(zdir).exists():
        raise ServiceError(f"нет {winws_exe(zdir)}")
    bin_path = build_bin_path(zdir, strategy, read_game_filter(zdir))
    tcp_timestamps_enable()
    if service_state() is None:
        start_type = "auto" if autostart else "demand"
        r = winutil.run(["sc", "create", SERVICE, "binPath=", bin_path, "DisplayName=", "zapret", "start=", start_type])
        _check(r, "sc create")
        winutil.run(["sc", "description", SERVICE, "Zapret DPI bypass software"])
    else:
        args = ["sc", "config", SERVICE, "binPath=", bin_path]
        if autostart is not None:
            args += ["start=", "auto" if autostart else "demand"]
        _check(winutil.run(args), "sc config")
    _set_installed_strategy(strategy)
    if start:
        start_service()


def reconfigure_service(zdir: Path) -> bool:
    """Пересобрать binPath установленной службы (после смены игрового фильтра/обновления).
    Возвращает True, если служба запущена и её нужно перезапустить."""
    strategy = installed_strategy()
    if service_state() is None or not strategy:
        return False
    bin_path = build_bin_path(zdir, strategy, read_game_filter(zdir))
    _check(winutil.run(["sc", "config", SERVICE, "binPath=", bin_path]), "sc config")
    return service_state() == "running"


def start_service() -> None:
    if winutil.process_running("winws.exe") and service_state() != "running":
        raise ServiceError("winws.exe уже запущен отдельно (через .bat). Закройте его или нажмите «Остановить».")
    tcp_timestamps_enable()
    r = winutil.run(["sc", "start", SERVICE])
    if r.returncode not in (0, 1056):  # 1056 — уже запущена
        _check(r, "sc start")
    if not _wait_state("running", 10):
        raise ServiceError("служба не запустилась — посмотрите «Диагностику» в service.bat")


def stop_all(stop_driver: bool = False) -> None:
    """Остановить службу и любой winws.exe. stop_driver — ещё и выгрузить WinDivert (для обновления файлов)."""
    if service_state() not in (None, "stopped"):
        winutil.run(["sc", "stop", SERVICE])
        _wait_state("stopped", 15)
    if winutil.process_running("winws.exe"):
        winutil.kill_process("winws.exe")
        time.sleep(0.5)
    if stop_driver:
        for drv in ("WinDivert", "WinDivert14"):
            if service_state(drv) not in (None, "stopped"):
                winutil.run(["sc", "stop", drv])
        time.sleep(0.5)


def restart_service() -> None:
    stop_all()
    start_service()


def remove_service() -> None:
    stop_all()
    if service_state() is not None:
        _check(winutil.run(["sc", "delete", SERVICE]), "sc delete")
    for drv in ("WinDivert", "WinDivert14"):
        if service_state(drv) is not None:
            winutil.run(["sc", "stop", drv])
            winutil.run(["sc", "delete", drv])


def status(zdir: Path) -> dict:
    state = service_state()
    return {
        "dir": str(zdir),
        "exists": winws_exe(zdir).exists(),
        "version": local_version(zdir),
        "service": state,  # None — не установлена
        "strategy": installed_strategy() if state is not None else None,
        "autostart": autostart_enabled() if state is not None else False,
        "winws_running": winutil.process_running("winws.exe"),
        "strategies": list_strategies(zdir),
        "game_filter": read_game_filter(zdir).to_dict(),
        "ipset_mode": ipset_mode(zdir),
    }
