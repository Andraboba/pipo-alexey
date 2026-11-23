"""Подбор стратегии: по очереди запускаем каждую стратегию и проверяем цели.

Методика повторяет официальный тестер Flowseal (utils/test zapret.ps1):
  * сайт — curl HEAD по HTTPS отдельно с TLS 1.2 и TLS 1.3; ошибка сертификата =
    подмена (блокировка), а не «работает». Если сайт ответил — ещё POST 64 КБ на него же:
    ТСПУ часто пропускает рукопожатие и короткий ответ, но замораживает соединение после
    16–20 КБ. Так HEAD зелёный, а Discord висит на загрузке — это считаем блокировкой;
  * «16–20 КБ» — набор hyperion-cs/dpi-checkers: POST 64 КБ; если отправили, а в ответ
    ничего и упёрлись в таймаут — характерная заморозка соединения DPI;
  * IP/подсеть игры — TCP-подключение к порту + ping.
Сначала прогон без запрета (базовая линия), чтобы видеть, что вообще заблокировано.
На время подбора IPSet переводится в «Все» (как у Flowseal) — иначе цели вне
списков запрет просто не трогал бы. В конце всё возвращается как было.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import split, suspend, winutil, zapret
from .jobs import Job

CURL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
DPI_SUITE_URL = "https://hyperion-cs.github.io/dpi-checkers/ru/tcp-16-20/suite.v2.json"
URL_TIMEOUT = 4
DPI_TIMEOUT = 5
DPI_BYTES = 65536
PARALLEL = 12


class ScanError(RuntimeError):
    pass


# ---------- цели ----------

def target(tid: str, name: str, kind: str, group: str, **kw) -> dict:
    return {"id": tid, "name": name, "kind": kind, "group": group, **kw}


def parse_targets_txt(zdir: Path) -> list[dict]:
    """utils/targets.txt из сборки (Flowseal или zapret2): Name = "https://…" или "PING:1.2.3.4"."""
    out = []
    try:
        text = (zdir / "utils" / "targets.txt").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return out
    group = zapret.engine_of(zdir).title
    for line in text.splitlines():
        if line.startswith("###"):
            group = line.strip("# ").strip() or group
            continue
        m = re.match(r'^\s*(\w+)\s*=\s*"(.+)"\s*$', line)
        if not m:
            continue
        name, val = m.groups()
        if val.upper().startswith("PING:"):
            out.append(target("ft-" + name, name, "ip", group, host=val[5:].strip(), port=None))
        else:
            out.append(target("ft-" + name, name, "url", group, url=val))
    return out


def available_targets(zdir: Path) -> list[dict]:
    """Цели Flowseal + реальные адреса игровых профилей.

    Для игр берём только хосты, которые точно отвечают (поле probe в каталоге). Голые домены
    вроде steamstatic.com часто не открываются сами по себе, а «первый адрес подсети» —
    случайный IP, на котором может не быть сервера: такие цели не говорят о блокировке.
    Игровой UDP-трафик так не проверить — только сайт, лаунчер и API игры.
    """
    from . import presets
    targets = parse_targets_txt(zdir)
    for t in targets:
        t["about"] = f"{t['group']} · utils\\targets.txt сборки"
    for p in split.snapshot(zdir)["profiles"]:
        group = "Игра: " + p["name"]
        pr = presets.get(p["preset"]) if p.get("preset") else None
        hosts = pr["probe"] if pr and pr.get("probe") else p["domains"]
        for h in hosts:
            targets.append(target(f"g-{p['id']}-{h}", h, "url", group, url="https://" + h,
                                   about=f"{p['name']} · сайт, лаунчер или API"))
    return targets


def parse_custom(text: str) -> list[dict]:
    """Свои цели: домен/URL, IP, IP:порт — по одной в строке."""
    out = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        # IPv4[:порт], [IPv6][:порт] или голый IPv6
        m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?$", s) or re.match(r"^\[([0-9a-fA-F:]+)\](?::(\d{1,5}))?$", s)
        host, port = (m.group(1), m.group(2)) if m else (s, None)
        try:
            ipaddress.ip_address(host)
            out.append(target("c-" + s, s, "ip", "Свои", host=host, port=int(port or 443),
                               about=f"Своя цель · TCP {port or 443} и ping"))
            continue
        except ValueError:
            pass
        url = s if re.match(r"^https?://", s, re.I) else "https://" + s
        out.append(target("c-" + s, s, "url", "Свои", url=url, about="Своя цель · HTTPS"))
    return out


def dpi_suite(fetch=None) -> list[dict]:
    from . import updater
    fetch = fetch or (lambda u: updater.http_get(u, 10).decode("utf-8", "replace"))
    data = json.loads(fetch(DPI_SUITE_URL))
    return [target("dpi-" + str(e["id"]), f"{e.get('provider', '')} {e.get('country', '')}".strip() or e["host"], "dpi",
                    "Заморозка 16–20 КБ", host=e["host"], about=f"Набор hyperion-cs · {e['host']}") for e in data]


# ---------- проверки ----------

def _run_curl(args: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        r = subprocess.run([str(CURL), *args], capture_output=True, text=True, timeout=timeout,
                           creationflags=winutil.CREATE_NO_WINDOW, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 28, "", "timeout"


_CERT = re.compile(r"certificate|SSL certificate problem|self[- ]?signed|unable to get local issuer", re.I)
_UNSUP = re.compile(r"not supported|unsupported|Unknown option|Unrecognized option", re.I)


def check_url(t: dict, payload: Path | None = None) -> dict:
    parts, oks = [], 0
    t0 = time.perf_counter()
    for label, extra in (("TLS1.2", ["--tlsv1.2", "--tls-max", "1.2"]), ("TLS1.3", ["--tlsv1.3", "--tls-max", "1.3"])):
        code, out, err = _run_curl(["-I", "-s", "-S", "-m", str(URL_TIMEOUT), "--connect-timeout", "2",
                                    "-o", "NUL", "-w", "%{http_code}", *extra, t["url"]], URL_TIMEOUT + 3)
        if code == 0:
            oks += 1
            parts.append(f"{label} {out}")
        elif _CERT.search(err):
            parts.append(f"{label} подмена сертификата")
        elif code == 35 and _UNSUP.search(err):
            oks += 0.5  # клиент не умеет — не вина стратегии
            parts.append(f"{label} не поддерживается")
        else:
            parts.append(f"{label} ошибка {code}")
    score = oks / 2
    if payload is not None and score > 0:
        frozen, _, detail = _freeze_probe(t["url"], payload)
        if frozen:
            score = 0
            parts.append(detail)
    return {"score": score, "detail": "; ".join(parts), "ms": round((time.perf_counter() - t0) * 1000)}


def _freeze_probe(url: str, payload: Path) -> tuple[bool, bool, str]:
    """POST 64 КБ (методика hyperion-cs/dpi-checkers). -> (заморозка, ответ пришёл, подробность).
    Заморозка — данные ушли, а в ответ ничего до таймаута: так DPI «душит» соединение после 16–20 КБ."""
    code, out, err = _run_curl(["--range", f"0-{DPI_BYTES - 1}", "-m", str(DPI_TIMEOUT), "--connect-timeout", "3",
                                "-w", "%{http_code} %{size_upload} %{size_download} %{time_total}", "-o", "NUL",
                                "-X", "POST", "--data-binary", f"@{payload}", "-s", url], DPI_TIMEOUT + 3)
    m = re.match(r"^(\d{3})\s+(\d+)\s+(\d+)\s+([\d.]+)$", out)
    up, down, took = (int(m.group(2)), int(m.group(3)), float(m.group(4))) if m else (0, 0, 0.0)
    if up > 0 and down == 0 and took >= DPI_TIMEOUT and code != 0:
        return True, False, f"заморозка: отправлено {up // 1024} КБ, ответа нет"
    if code == 0:
        return False, True, f"HTTP {m.group(1) if m else '?'}, {down // 1024} КБ"
    return False, False, f"ошибка {code}"


def check_dpi(t: dict, payload: Path) -> dict:
    t0 = time.perf_counter()
    _, answered, detail = _freeze_probe("https://" + t["host"], payload)
    return {"score": 1 if answered else 0, "detail": detail, "ms": round((time.perf_counter() - t0) * 1000)}


def _ping(host: str) -> int | None:
    try:
        r = winutil.run(["ping", "-n", "1", "-w", "1000", host], timeout=5)
    except TimeoutError:
        return None
    m = re.search(r"(?:time|время)[=<](\d+)", r.stdout)
    return int(m.group(1)) if r.returncode == 0 and m else None


def check_ip(t: dict) -> dict:
    t0 = time.perf_counter()
    parts, score = [], 0.0
    if t.get("port"):
        try:
            with socket.create_connection((t["host"], t["port"]), timeout=3):
                score += 0.5
                parts.append(f"TCP {t['port']} открыт")
        except OSError:
            parts.append(f"TCP {t['port']} нет")
    rtt = _ping(t["host"])
    if rtt is not None:
        score += 0.5 if t.get("port") else 1
        parts.append(f"ping {rtt} мс")
    else:
        parts.append("ping нет")
    return {"score": score, "detail": "; ".join(parts), "ms": round((time.perf_counter() - t0) * 1000)}


def make_payload() -> Path:
    """Случайные 64 КБ для проверки заморозки 16–20 КБ. Удаляет вызывающий."""
    fd, name = tempfile.mkstemp(prefix="pipo-dpi-", suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(os.urandom(DPI_BYTES))
    return Path(name)


def check_all(targets: list[dict], payload: Path) -> dict[str, dict]:
    def one(t):
        if t["kind"] == "url":
            return t["id"], check_url(t, payload)
        if t["kind"] == "dpi":
            return t["id"], check_dpi(t, payload)
        return t["id"], check_ip(t)

    with ThreadPoolExecutor(PARALLEL) as ex:
        return dict(ex.map(one, targets))


# ---------- оценка ----------

def grade(res: dict) -> dict:
    """Оценка стратегий относительно базовой линии.

    Для каждой цели «потолок» — лучший результат без запрета или с любой стратегией:
      * потолок 0 — цель не отвечает вообще (мёртвый адрес или её не пробивает ничто) — не учитываем;
      * без запрета уже на потолке — цель открыта, стратегия не должна её сломать;
      * без запрета ниже потолка — цель заблокирована, стратегии её чинят.
    Счёт стратегии — сумма долей от потолка по учитываемым целям. Так сервер без TLS 1.3
    («наполовину» везде) не отнимает баллы ни у одной стратегии.
    """
    targets = res["targets"]
    done = [r for r in res["rows"] if r["state"] == "done"]
    meta = {}
    for t in targets:
        tid = t["id"]
        base = res["baseline"].get(tid, {}).get("score", 0)
        cap = max([base] + [r["results"].get(tid, {}).get("score", 0) for r in done])
        meta[tid] = {"cap": cap, "status": "dead" if cap == 0 else "open" if base >= cap else "blocked"}
    counted = [t["id"] for t in targets if meta[t["id"]]["status"] != "dead"]
    n = len(counted)
    for r in res["rows"]:
        if r["state"] != "done":
            r["grade"] = "failed"
            continue
        part = {tid: min(1.0, r["results"].get(tid, {}).get("score", 0) / meta[tid]["cap"]) for tid in counted}
        r["score"] = round(sum(part.values()), 2)
        r["of"] = n
        r["fixed"] = sum(1 for tid in counted if meta[tid]["status"] == "blocked" and part[tid] >= 1)
        r["broke"] = sum(1 for tid in counted if meta[tid]["status"] == "open" and part[tid] < 1)
        # идеальная — всё учитываемое проходит, частичная — хоть что-то
        r["grade"] = "ideal" if n and r["score"] >= n - 1e-9 else "partial" if r["score"] > 0 else "broken"
        r["avg_ms"] = round(r["ms"] / max(1, len(targets)))
    res["meta"] = meta
    res["counted"] = n
    res["blocked"] = sum(1 for m in meta.values() if m["status"] == "blocked")
    res["best"] = None
    if done:
        res["best"] = max(done, key=lambda r: (r["score"], -r["broke"], -r["avg_ms"]))["strategy"]
    return res


# ---------- последний результат (не пересканировать каждый раз) ----------

# у каждого движка свой: стратегии у них разные, «применить лучшую» чужого движка не сработает

def _last_file(engine: str) -> Path:
    from .settings import DATA_DIR
    # у Flowseal имя прежнее — результат, сохранённый до появления второго движка, не теряется
    return DATA_DIR / ("scan-last.json" if engine == "flowseal" else f"scan-last-{engine}.json")


def save_last(res: dict) -> None:
    from .settings import write_text_atomic
    write_text_atomic(_last_file(res.get("engine") or "flowseal"), json.dumps(res, ensure_ascii=False))


def load_last(engine: str = "flowseal") -> dict | None:
    try:
        return json.loads(_last_file(engine).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------- запуск стратегии ----------

def start_winws(zdir: Path, strategy: str) -> subprocess.Popen:
    return launch(zdir, zapret.build_args(zdir, strategy, zapret.read_game_filter(zdir)))


def launch(zdir: Path, args: list[str]) -> subprocess.Popen:
    """Запустить winws/winws2 папки zdir с аргументами в формате build_args и дождаться, пока он поднимется."""
    args = [a.replace('"', "") for a in args]
    proc = subprocess.Popen([str(zapret.winws_exe(zdir)), *args], cwd=str(zdir / "bin"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=winutil.CREATE_NO_WINDOW)
    time.sleep(2.0)  # драйвер WinDivert и списки грузятся ~1–2 с
    if proc.poll() is not None:
        raise ScanError(f"{zapret.engine_of(zdir).exe} завершился с кодом {proc.returncode}")
    return proc


def stop_winws(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass
    zapret.kill_winws()
    time.sleep(0.5)


def run_scan(job: Job, zdir: Path, strategies: list[str], targets: list[dict]) -> dict:
    if not CURL.exists():
        raise ScanError(f"нет {CURL}")
    if not targets:
        raise ScanError("не выбрано ни одной цели")
    all_strats = zapret.list_strategies(zdir)
    strategies = [s for s in strategies if s in all_strats] or all_strats

    engine = zapret.engine_of(zdir)
    res = {"engine": engine.id, "engine_title": engine.title, "targets": targets, "baseline": {}, "rows": [{"strategy": s, "state": "pending", "results": {}, "score": 0}
                                                        for s in strategies], "best": None}
    job.result = res

    job.say(f"Движок: {engine.title}. Стратегий: {len(strategies)}, целей: {len(targets)}")

    payload = make_payload()
    proc = None
    try:
        with suspend.suspended(zdir, job.say, ipset="any") as was:
            job.say(f"Служба: {was.service or 'не установлена'}, IPSet: {was.ipset} → временно «Все», чтобы стратегия трогала все цели")
            job.say("Прогон без запрета — что вообще заблокировано")
            res["baseline"] = check_all(targets, payload)
            blocked = sum(1 for r in res["baseline"].values() if r["score"] < 1)
            job.say(f"Без запрета не проходит {blocked} из {len(targets)} целей")

            for i, row in enumerate(res["rows"]):
                if job.cancelled:
                    job.say("Остановлено пользователем", "warn")
                    break
                job.progress = i / len(res["rows"])
                row["state"] = "running"
                try:
                    proc = start_winws(zdir, row["strategy"])
                    row["results"] = check_all(targets, payload)
                    row["score"] = round(sum(r["score"] for r in row["results"].values()), 2)
                    row["ms"] = sum(r["ms"] for r in row["results"].values())
                    row["state"] = "done"
                    job.say(f"{row['strategy']}: {row['score']:g} из {len(targets)}")
                except (ScanError, zapret.StrategyError, OSError) as e:
                    row["state"] = "failed"
                    row["error"] = str(e)
                    job.say(f"{row['strategy']}: {e}", "warn")
                finally:
                    stop_winws(proc)
                    proc = None

            for row in res["rows"]:
                if row["state"] == "pending":
                    row["state"] = "skipped"  # остановили раньше — в сохранённом результате не «в очереди»
            grade(res)
            if res["best"]:
                best = next(r for r in res["rows"] if r["strategy"] == res["best"])
                job.say(f"Лучшая: {best['strategy']} — {best['score']:g} из {res['counted']}, в среднем {best['avg_ms']} мс", "ok")
            dead = [t["name"] for t in targets if res["meta"][t["id"]]["status"] == "dead"]
            if dead:
                job.say("Не отвечают ни без запрета, ни с одной стратегией — в оценке не учтены: " + ", ".join(dead), "warn")
            res["finished_at"] = time.time()
            save_last(res)
            job.progress = 1
            return res
    finally:
        stop_winws(proc)
        payload.unlink(missing_ok=True)
