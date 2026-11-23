"""Диагностика DNS: подменяет ли провайдер ответы и перехватывает ли запросы.

Методика повторяет dpi-detector (Runnin4ik/dpi-detector, MIT), оттуда же списки
доменов и серверов:
  * «правда» — объединение A-записей, полученных по шифрованным каналам (DoH и DoT):
    их провайдер прочитать и подменить не может;
  * подмена — обычный DNS (UDP/53) вернул адреса, которых нет в «правде», или
    NXDOMAIN/пустой ответ/тишину на домене, который DoH знает;
  * заглушка — адрес, который подменённые ответы возвращают для разных доменов;
  * перехват UDP/53 — запрос whoami.akamai.net возвращает адрес резолвера, который
    на самом деле ответил. Если «Google», «Cloudflare» и «Quad9» отвечают из одной
    сети /24 — запросы к ним заворачивает к себе провайдер.

    report = run()                       # всё по умолчанию
    report = run(["example.org"])        # свои домены к стандартным

Сеть спрятана за транспортом (Transport): тесты подставляют свой, без сети.
"""
from __future__ import annotations

import ipaddress
import json
import random
import socket
import ssl
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

TIMEOUT = 3.0
PARALLEL = 32  # по потоку на сервер

# заблокированные в РФ домены (из dpi-detector) — на них видно подмену.
# Без доменов за CDN: у Cloudflare разные серверы честно отдают разные адреса, это не подмена
BLOCKED_DOMAINS = ["rutor.info", "flibusta.is", "rezka.ag", "clubtone.do.am"]
# точно открытые — по ним понятно, что сервер вообще отвечает
CONTROL_DOMAINS = ["vk.ru", "gosuslugi.ru"]
WHOAMI = "whoami.akamai.net"


@dataclass(frozen=True)
class Server:
    addr: str  # IP для UDP, URL для DoH, имя или IP для DoT
    name: str
    operator: str = ""  # одна организация — общая сеть ответов не значит перехват
    truth: bool = True  # годится в источник «правды» (не переписывает ответы сам)
    ru: bool = False  # российский резолвер: обязан выполнять блокировки РКН

    @property
    def op(self) -> str:
        return self.operator or self.name


UDP_SERVERS = [
    Server("8.8.8.8", "Google"), Server("1.1.1.1", "Cloudflare"), Server("9.9.9.9", "Quad9"),
    Server("94.140.14.14", "AdGuard"), Server("208.67.222.222", "OpenDNS"), Server("185.222.222.222", "DNS.SB"),
    Server("77.88.8.8", "Яндекс", ru=True),
    Server("62.76.62.76", "MSK-IX", operator="msk-ix", ru=True), Server("195.208.4.1", "НСДИ", operator="msk-ix", ru=True),
]
# шифрованные: источник «правды» и подсказка, какой DoH у вас работает.
# (Quad9 и Mullvad по DoH говорят только HTTP/2 — Quad9 проверяем через DoT.)
# Comss.one и XboxDNS намеренно отдают свои прокси вместо заблокированных сайтов — в «правду» не берём
DOH_SERVERS = [
    Server("https://1.1.1.1/dns-query", "Cloudflare"), Server("https://dns.google/dns-query", "Google"),
    Server("https://dns.adguard-dns.com/dns-query", "AdGuard"), Server("https://dns.sb/dns-query", "DNS.SB"),
    Server("https://dns.comss.one/dns-query", "Comss.one", truth=False, ru=True),
    Server("https://xbox-dns.ru/dns-query", "XboxDNS", truth=False, ru=True),
]
DOT_SERVERS = [
    Server("1.1.1.1", "Cloudflare"), Server("dns.google", "Google"), Server("dns.quad9.net", "Quad9"),
    Server("dns.adguard-dns.com", "AdGuard"), Server("dns.comss.one", "Comss.one", truth=False, ru=True),
]
# адреса, которые никогда не «правда»: FakeIP VPN-клиентов, частные сети, 0.0.0.0
_FAKEIP = ipaddress.ip_network("198.18.0.0/15")  # так отвечают VPN-клиенты в режиме FakeIP (sing-box, Clash)
_JUNK = [ipaddress.ip_network(n) for n in ("198.18.0.0/15", "0.0.0.0/8", "127.0.0.0/8", "10.0.0.0/8",
                                           "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]


@dataclass
class Answer:
    ips: list[str] = field(default_factory=list)
    rcode: int | None = None  # 0 — ок, 3 — NXDOMAIN; None — ответа нет
    ms: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.rcode is not None


# ---------- формат DNS (RFC 1035): только A-запрос и разбор ответа ----------

def build_query(name: str, qid: int | None = None) -> bytes:
    qid = random.randint(0, 0xFFFF) if qid is None else qid
    q = b"".join(bytes([len(p)]) + p.encode("idna") for p in name.strip(".").split(".")) + b"\0"
    return struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + q + struct.pack(">HH", 1, 1)


def _skip_name(buf: bytes, off: int) -> int:
    while True:
        n = buf[off]
        if n == 0:
            return off + 1
        if n & 0xC0 == 0xC0:  # сжатие — указатель на 2 байта
            return off + 2
        off += n + 1


def parse_answer(buf: bytes) -> tuple[int, list[str]]:
    """(rcode, A-записи). Бросает ValueError на мусоре."""
    if len(buf) < 12:
        raise ValueError("короткий ответ")
    _, flags, qd, an, _, _ = struct.unpack(">HHHHHH", buf[:12])
    rcode = flags & 0xF
    off = 12
    for _ in range(qd):
        off = _skip_name(buf, off) + 4
    ips = []
    for _ in range(an):
        off = _skip_name(buf, off)
        rtype, _, _, rdlen = struct.unpack(">HHIH", buf[off:off + 10])
        off += 10
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(buf[off:off + 4]))
        off += rdlen
    return rcode, ips


# ---------- транспорты ----------

def _timed(fn: Callable[[], bytes]) -> Answer:
    t0 = time.perf_counter()
    try:
        raw = fn()
        rcode, ips = parse_answer(raw)
        return Answer(ips=ips, rcode=rcode, ms=round((time.perf_counter() - t0) * 1000))
    except socket.timeout:
        return Answer(error="нет ответа")
    except (OSError, ValueError, ssl.SSLError, IndexError, struct.error) as e:
        return Answer(error=(type(e).__name__ + ": " + str(e))[:120])


def udp(server: str, name: str) -> Answer:
    def go() -> bytes:
        q = build_query(name)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(TIMEOUT)
            s.sendto(q, (server, 53))
            end = time.monotonic() + TIMEOUT
            while time.monotonic() < end:
                data, _ = s.recvfrom(4096)
                if data[:2] == q[:2]:  # чужой id — не наш ответ
                    return data
            raise socket.timeout()
    return _timed(go)


def _tls(host: str, port: int, alpn: list[str] | None = None) -> ssl.SSLSocket:
    ctx = ssl.create_default_context()
    if alpn:
        ctx.set_alpn_protocols(alpn)  # иначе часть DoH-серверов сразу говорит HTTP/2
    raw = socket.create_connection((host, port), timeout=TIMEOUT)
    try:
        s = ctx.wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise
    s.settimeout(TIMEOUT)
    return s


def _read_all(s: ssl.SSLSocket) -> bytes:
    chunks = []
    while True:
        try:
            c = s.recv(65536)
        except ssl.SSLZeroReturnError:
            break
        if not c:
            break
        chunks.append(c)
    return b"".join(chunks)


def doh(url: str, name: str) -> Answer:
    """RFC 8484, POST application/dns-message. Своим сокетом: не зависим от системного прокси."""
    def go() -> bytes:
        u = urlsplit(url)
        q = build_query(name, qid=0)  # для DoH id рекомендуется 0
        with _tls(u.hostname, u.port or 443, ["http/1.1"]) as s:
            head = (f"POST {u.path or '/'} HTTP/1.1\r\nHost: {u.netloc}\r\nContent-Type: application/dns-message\r\n"
                    f"Accept: application/dns-message\r\nContent-Length: {len(q)}\r\nConnection: close\r\n\r\n")
            s.sendall(head.encode() + q)
            resp = _read_all(s)
        head, _, body = resp.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 200" not in status:
            raise ValueError(status.decode("latin-1", "replace")[:60] or "пустой ответ")
        if b"transfer-encoding: chunked" in head.lower():
            body = _dechunk(body)
        return body
    return _timed(go)


def _dechunk(body: bytes) -> bytes:
    out, off = b"", 0
    while True:
        line_end = body.index(b"\r\n", off)
        size = int(body[off:line_end].split(b";")[0], 16)
        if size == 0:
            return out
        out += body[line_end + 2:line_end + 2 + size]
        off = line_end + 2 + size + 2


def dot(host: str, name: str) -> Answer:
    """RFC 7858: тот же DNS-пакет поверх TLS:853 с двухбайтовой длиной впереди."""
    def go() -> bytes:
        q = build_query(name)
        with _tls(host, 853) as s:
            s.sendall(struct.pack(">H", len(q)) + q)
            buf = b""
            while len(buf) < 2 or len(buf) < 2 + struct.unpack(">H", buf[:2])[0]:
                c = s.recv(4096)
                if not c:
                    raise ValueError("соединение закрыто")
                buf += c
        return buf[2:2 + struct.unpack(">H", buf[:2])[0]]
    return _timed(go)


def system(name: str) -> Answer:
    """Как домен видит Windows (и браузер без своего DoH): системный резолвер."""
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(name, 443, socket.AF_INET, socket.SOCK_STREAM)
        ips = list(dict.fromkeys(i[4][0] for i in infos))
        return Answer(ips=ips, rcode=0, ms=round((time.perf_counter() - t0) * 1000))
    except socket.gaierror as e:
        # «нет такого имени» — ответ (NXDOMAIN), а не тишина
        if e.errno in (socket.EAI_NONAME, getattr(socket, "EAI_NODATA", -5), 11001, 11004):
            return Answer(rcode=3, ms=round((time.perf_counter() - t0) * 1000))
        return Answer(error=str(e)[:120])


@dataclass
class Transport:
    udp: Callable[[str, str], Answer] = udp
    doh: Callable[[str, str], Answer] = doh
    dot: Callable[[str, str], Answer] = dot
    system: Callable[[str], Answer] = system


# ---------- анализ ----------

def _real(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not any(a in n for n in _JUNK)


def _net24(ip: str) -> str:
    return str(ipaddress.ip_network(ip + "/24", strict=False))


# что считаем вмешательством: однозначные признаки. «Другой адрес» сам по себе — не подмена (CDN)
SUBST = ("nxdomain", "empty", "junk", "stub")


def _in(ip: str, net: ipaddress.IPv4Network) -> bool:
    try:
        return ipaddress.ip_address(ip) in net
    except ValueError:
        return False


def _verdict(ans: Answer, truth: set[str]) -> str:
    """ok | other | nxdomain | empty | junk | refused | timeout | unknown (стаб уточняется позже)."""
    if not ans.ok:
        return "timeout"
    if ans.rcode == 3:
        return "nxdomain" if truth else "ok"
    if ans.rcode != 0:
        return "refused"
    if not ans.ips:
        return "empty" if truth else "ok"
    if all(_in(ip, _FAKEIP) for ip in ans.ips):
        return "fakeip"  # это VPN на компьютере подставил свой адрес, а не провайдер
    if not any(_real(ip) for ip in ans.ips):
        return "junk"  # 0.0.0.0, 127.0.0.1, частные адреса
    if not truth:
        return "unknown"
    return "ok" if set(ans.ips) & truth else "other"


def run(extra_domains: list[str] | None = None, transport: Transport | None = None) -> dict:
    t = transport or Transport()
    blocked = list(dict.fromkeys(BLOCKED_DOMAINS + [d.strip().lower() for d in extra_domains or [] if d.strip()]))
    domains = blocked + [d for d in CONTROL_DOMAINS if d not in blocked]
    t0 = time.perf_counter()

    groups = [("udp", UDP_SERVERS, t.udp), ("doh", DOH_SERVERS, t.doh), ("dot", DOT_SERVERS, t.dot)]
    # к одному серверу — по очереди (сотня TLS-рукопожатий разом душит и серверы, и канал),
    # разные серверы — параллельно. Контрольные домены первыми: молчит на них — сервер мёртв, дальше не ждём
    order = CONTROL_DOMAINS + [d for d in domains if d not in CONTROL_DOMAINS]

    def one_server(kind: str, addr: str, fn: Callable[[str], Answer], names: list[str]) -> dict[tuple, Answer]:
        out: dict[tuple, Answer] = {}
        for d in names:
            controls = [out[(kind, addr, c)] for c in CONTROL_DOMAINS if (kind, addr, c) in out]
            if d not in CONTROL_DOMAINS and len(controls) == len(CONTROL_DOMAINS) and not any(a.ok for a in controls):
                out[(kind, addr, d)] = Answer(error="сервер не отвечает")
            else:
                a = fn(d)
                if not a.ok and kind in ("udp", "system"):
                    a = fn(d)  # UDP теряется — «молчит на запрещённое» засчитываем только со второй попытки
                out[(kind, addr, d)] = a
        return out

    tasks = [("system", "", t.system, domains)]
    for kind, servers, fn in groups:
        for s in servers:
            tasks.append((kind, s.addr, lambda d, fn=fn, a=s.addr: fn(a, d), order))
    tasks += [("whoami", s.addr, lambda d, a=s.addr: t.udp(a, d), [WHOAMI]) for s in UDP_SERVERS]
    answers: dict[tuple, Answer] = {}
    with ThreadPoolExecutor(PARALLEL) as ex:
        for part in ex.map(lambda task: one_server(*task), tasks):
            answers.update(part)

    truth_src = {(kind, s.addr) for kind, servers, _ in groups[1:] for s in servers if s.truth}
    truth = {d: {ip for (kind, addr, dd), a in answers.items() if (kind, addr) in truth_src and dd == d
                 for ip in a.ips if _real(ip)} for d in domains}

    def row(kind: str, s: Server | None) -> dict:
        addr = s.addr if s else ""
        res = {}
        for d in domains:
            a = answers[(kind, addr, d)]
            res[d] = {"verdict": _verdict(a, truth[d]), "ips": a.ips[:4], "ms": a.ms, "error": a.error}
        alive = any(answers[(kind, addr, d)].rcode == 0 and answers[(kind, addr, d)].ips for d in CONTROL_DOMAINS)
        ms = [res[d]["ms"] for d in CONTROL_DOMAINS if res[d]["ms"] is not None]
        return {"kind": kind, "addr": addr, "name": s.name if s else "Системный DNS Windows",
                "ru": bool(s and s.ru), "truth_source": bool(s and s.truth and kind != "udp"),
                "rewrites": bool(s and not s.truth),  # сам отдаёт свои адреса вместо заблокированных — так задумано
                "alive": alive, "ms": min(ms) if ms else None, "domains": res}

    system_row = row("system", None)
    udp_rows = [row("udp", s) for s in UDP_SERVERS]
    enc_rows = [row(kind, s) for kind, servers, _ in groups[1:] for s in servers]

    # заглушка: один и тот же «чужой» адрес у разных запрещённых доменов
    seen: dict[str, set[str]] = {}
    for r in [system_row] + udp_rows:
        for d in blocked:
            if r["domains"][d]["verdict"] == "other":
                for ip in r["domains"][d]["ips"]:
                    seen.setdefault(ip, set()).add(d)
    stubs = sorted(ip for ip, ds in seen.items() if len(ds) >= 2)

    for r in [system_row] + udp_rows + enc_rows:
        for d in blocked:
            v = r["domains"][d]
            if v["verdict"] == "other" and set(v["ips"]) & set(stubs):
                v["verdict"] = "stub"
        subst = [] if r["rewrites"] else [d for d in blocked if r["domains"][d]["verdict"] in SUBST]
        # сервер жив, а на запрещённое молчит — тоже вмешательство (так ведут себя ТСПУ).
        # Только для открытого DNS: шифрованный провайдер не читает, обрыв там — сбой сервера
        if r["alive"] and r["kind"] in ("system", "udp"):
            subst += [d for d in blocked if r["domains"][d]["verdict"] == "timeout"]
        r["substituted"] = subst
        r["differs"] = [d for d in blocked if r["domains"][d]["verdict"] == "other"]

    # перехват: серверы разных организаций отвечают из одной сети /24
    egress: dict[str, set[str]] = {}
    who = {}
    for s in UDP_SERVERS:
        a = answers[("whoami", s.addr, WHOAMI)]
        if a.ips and _real(a.ips[0]):
            who[s.addr] = a.ips[0]
            egress.setdefault(_net24(a.ips[0]), set()).add(s.op)
    hijack_nets = {net for net, ops in egress.items() if len(ops) >= 2}
    names = {s.addr: s.name for s in UDP_SERVERS}
    hijack = [{"net": net, "names": sorted(names[a] for a, ip in who.items() if _net24(ip) == net)} for net in sorted(hijack_nets)]
    for r in udp_rows:
        r["egress"] = who.get(r["addr"])
        r["hijacked"] = bool(r["egress"]) and _net24(r["egress"]) in hijack_nets

    working_enc = [{"kind": r["kind"], "addr": r["addr"], "name": r["name"], "ms": r["ms"], "rewrites": r["rewrites"]}
                   for r in enc_rows if r["alive"] and not r["substituted"]]
    foreign_subst = [r["name"] for r in udp_rows if r["substituted"] and not r["ru"]]
    fakeip = any(system_row["domains"][d]["verdict"] == "fakeip" for d in domains)
    if not system_row["alive"] and not any(r["alive"] for r in udp_rows + enc_rows):
        verdict = "offline"  # не ответил никто — сравнивать нечего, «чисто» тут было бы неправдой
    elif fakeip:
        verdict = "fakeip"  # запущен VPN-клиент с FakeIP: системный DNS проверить нельзя
    elif system_row["substituted"]:
        verdict = "system"  # ваш DNS отдаёт неправду — сайты не откроются при любой стратегии
    elif hijack or foreign_subst:
        verdict = "udp"  # ваш DNS честный, но обычные запросы к публичным DNS провайдер портит
    else:
        verdict = "clean"
    return {
        "verdict": verdict,
        "blocked": blocked,
        "control": CONTROL_DOMAINS,
        "truth": {d: sorted(v) for d, v in truth.items()},
        "no_truth": [d for d in blocked if not truth[d]],
        "system": system_row,
        "udp": udp_rows,
        "encrypted": enc_rows,
        "working_encrypted": working_enc,
        "foreign_substituted": foreign_subst,
        "stubs": stubs,
        "hijack": hijack,
        "ms": round((time.perf_counter() - t0) * 1000),
        "checked_at": time.time(),
    }


# ---------- последний результат ----------

def _last_file():
    from .settings import DATA_DIR
    return DATA_DIR / "dns-last.json"


def save_last(report: dict) -> None:
    from .settings import write_text_atomic
    write_text_atomic(_last_file(), json.dumps(report, ensure_ascii=False))


def load_last() -> dict | None:
    try:
        return json.loads(_last_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
