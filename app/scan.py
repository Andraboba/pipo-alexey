"""Подбор стратегии: по очереди запускаем каждую стратегию и проверяем цели.

Методика повторяет официальный тестер Flowseal (utils/test zapret.ps1):
  * сайт — curl HEAD по HTTPS отдельно с TLS 1.2 и TLS 1.3; ошибка сертификата =
    подмена (блокировка), а не «работает»;
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

from . import split, winutil, zapret
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

def _target(tid: str, name: str, kind: str, group: str, **kw) -> dict:
    return {"id": tid, "name": name, "kind": kind, "group": group, **kw}


def parse_targets_txt(zdir: Path) -> list[dict]:
    """utils/targets.txt из сборки Flowseal: Name = "https://…" или "PING:1.2.3.4"."""
    out = []
    try:
        text = (zdir / "utils" / "targets.txt").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return out
    group = "Flowseal"
    for line in text.splitlines():
        if line.startswith("###"):
            group = line.strip("# ").strip() or group
            continue
        m = re.match(r'^\s*(\w+)\s*=\s*"(.+)"\s*$', line)
        if not m:
            continue
        name, val = m.groups()
        if val.upper().startswith("PING:"):
            out.append(_target("ft-" + name, name, "ip", group, host=val[5:].strip(), port=None))
        else:
            out.append(_target("ft-" + name, name, "url", group, url=val))
    return out


def sample_hosts(networks: list[str], limit: int = 3) -> list[str]:
    """Несколько адресов из подсетей игры: первый узел из первых сетей (IPv4)."""
    out = []
    for n in networks:
        try:
            net = ipaddress.ip_network(n, strict=False)
        except ValueError:
            continue
        if net.version != 4:
            continue
        host = net.network_address + 1 if net.num_addresses > 2 else net.network_address
        out.append(str(host))
        if len(out) >= limit:
            break
    return out


def available_targets(zdir: Path) -> list[dict]:
    targets = parse_targets_txt(zdir)
    snap = split.snapshot(zdir)
    for p in snap["profiles"]:
        group = "Игра: " + p["name"]
        for d in p["domains"]:
            targets.append(_target(f"g-{p['id']}-{d}", d, "url", group, url="https://" + d))
        st = split.load(zdir)
        prof = next((x for x in st.profiles if x.id == p["id"]), None)
        nets = split.profile_networks(zdir, prof) if prof else []
        for ip in sample_hosts(nets):
            targets.append(_target(f"g-{p['id']}-{ip}", ip, "ip", group, host=ip, port=443))
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
            out.append(_target("c-" + s, s, "ip", "Свои", host=host, port=int(port or 443)))
            continue
        except ValueError:
            pass
        url = s if re.match(r"^https?://", s, re.I) else "https://" + s
        out.append(_target("c-" + s, s, "url", "Свои", url=url))
    return out


def dpi_suite(fetch=None) -> list[dict]:
    from . import updater
    fetch = fetch or (lambda u: updater.http_get(u, 10).decode("utf-8", "replace"))
    data = json.loads(fetch(DPI_SUITE_URL))
    return [_target("dpi-" + str(e["id"]), f"{e.get('provider', '')} {e.get('country', '')}".strip() or e["host"], "dpi",
                    "Заморозка 16–20 КБ", host=e["host"]) for e in data]


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


def check_url(t: dict) -> dict:
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
    return {"score": oks / 2, "detail": "; ".join(parts), "ms": round((time.perf_counter() - t0) * 1000)}


def check_dpi(t: dict, payload: Path) -> dict:
    t0 = time.perf_counter()
    code, out, err = _run_curl(["--range", f"0-{DPI_BYTES - 1}", "-m", str(DPI_TIMEOUT), "--connect-timeout", "3",
                                "-w", "%{http_code} %{size_upload} %{size_download} %{time_total}", "-o", "NUL",
                                "-X", "POST", "--data-binary", f"@{payload}", "-s", "https://" + t["host"]], DPI_TIMEOUT + 3)
    m = re.match(r"^(\d{3})\s+(\d+)\s+(\d+)\s+([\d.]+)$", out)
    up, down, took = (int(m.group(2)), int(m.group(3)), float(m.group(4))) if m else (0, 0, 0.0)
    ms = round((time.perf_counter() - t0) * 1000)
    if up > 0 and down == 0 and took >= DPI_TIMEOUT and code != 0:
        return {"score": 0, "detail": f"заморозка: отправлено {up // 1024} КБ, ответа нет", "ms": ms}
    if code == 0:
        return {"score": 1, "detail": f"HTTP {m.group(1) if m else '?'}, {down // 1024} КБ", "ms": ms}
    return {"score": 0, "detail": f"ошибка {code}", "ms": ms}


def _ping(host: str) -> int | None:
    r = winutil.run(["ping", "-n", "1", "-w", "1000", host], timeout=5)
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


def check_all(targets: list[dict], payload: Path) -> dict[str, dict]:
    def one(t):
        if t["kind"] == "url":
            return t["id"], check_url(t)
        if t["kind"] == "dpi":
            return t["id"], check_dpi(t, payload)
        return t["id"], check_ip(t)

    with ThreadPoolExecutor(PARALLEL) as ex:
        return dict(ex.map(one, targets))


# ---------- последний результат (как кеш у NetFix: не пересканировать каждый раз) ----------

def _last_file() -> Path:
    from .settings import DATA_DIR
    return DATA_DIR / "scan-last.json"


def save_last(res: dict) -> None:
    from .settings import write_text_atomic
    write_text_atomic(_last_file(), json.dumps(res, ensure_ascii=False))


def load_last() -> dict | None:
    try:
        return json.loads(_last_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------- запуск стратегии ----------

def start_winws(zdir: Path, strategy: str) -> subprocess.Popen:
    args = [a.replace('"', "") for a in zapret.build_args(zdir, strategy, zapret.read_game_filter(zdir))]
    proc = subprocess.Popen([str(zapret.winws_exe(zdir)), *args], cwd=str(zdir / "bin"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=winutil.CREATE_NO_WINDOW)
    time.sleep(2.0)  # драйвер WinDivert и списки грузятся ~1–2 с
    if proc.poll() is not None:
        raise ScanError(f"winws завершился с кодом {proc.returncode}")
    return proc


def stop_winws(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass
    if winutil.process_running("winws.exe"):
        winutil.kill_process("winws.exe")
    time.sleep(0.5)


def run_scan(job: Job, zdir: Path, strategies: list[str], targets: list[dict]) -> dict:
    if not CURL.exists():
        raise ScanError(f"нет {CURL}")
    if not targets:
        raise ScanError("не выбрано ни одной цели")
    all_strats = zapret.list_strategies(zdir)
    strategies = [s for s in strategies if s in all_strats] or all_strats

    res = {"targets": targets, "baseline": {}, "rows": [{"strategy": s, "state": "pending", "results": {}, "score": 0}
                                                        for s in strategies], "best": None}
    job.result = res

    was_service = zapret.service_state()
    mode = zapret.ipset_mode(zdir)
    job.say(f"Стратегий: {len(strategies)}, целей: {len(targets)}. Служба: {was_service or 'не установлена'}, IPSet: {mode}")

    fd, payload_name = tempfile.mkstemp(prefix="pipo-dpi-", suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(os.urandom(DPI_BYTES))
    payload = Path(payload_name)

    proc = None
    try:
        zapret.stop_all()
        job.say("Прогон без запрета — что вообще заблокировано")
        res["baseline"] = check_all(targets, payload)
        blocked = sum(1 for r in res["baseline"].values() if r["score"] < 1)
        job.say(f"Без запрета не проходит {blocked} из {len(targets)} целей")

        if mode != "any":
            split.set_ipset_mode(zdir, "any")
            job.say("IPSet временно в режиме «Все», чтобы стратегия трогала все цели")

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

        n = len(targets)
        for r in res["rows"]:
            # как у NetFix: идеальная — прошли все цели, частичная — хоть что-то
            r["grade"] = "failed" if r["state"] != "done" else "ideal" if r["score"] >= n else "partial" if r["score"] > 0 else "broken"
            if r["state"] == "done":
                r["avg_ms"] = round(r["ms"] / max(1, n))
        done = [r for r in res["rows"] if r["state"] == "done"]
        if done:
            best = max(done, key=lambda r: (r["score"], -r["avg_ms"]))
            res["best"] = best["strategy"]
            job.say(f"Лучшая: {best['strategy']} — {best['score']:g} из {n}, в среднем {best['avg_ms']} мс", "ok")
        res["finished_at"] = time.time()
        save_last(res)
        job.progress = 1
        return res
    finally:
        stop_winws(proc)
        payload.unlink(missing_ok=True)
        if zapret.ipset_mode(zdir) != mode:
            split.set_ipset_mode(zdir, mode)
            job.say("Режим IPSet возвращён")
        if was_service == "running":
            try:
                zapret.start_service()
                job.say("Служба запрета снова запущена")
            except zapret.ServiceError as e:
                job.say(f"Не удалось вернуть службу: {e}", "error")
