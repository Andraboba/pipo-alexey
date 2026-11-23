"""Доступ к сервисам, закрывшим себя для РФ (ChatGPT, Gemini, Grok…), через hosts.

В системный hosts пишутся адреса обратных прокси из открытых списков
(GeoHide DNS, dns.malw.link). Запрет тут не участвует — эти сервисы ограничивают
доступ сами, по региону.

Claude/Anthropic не поддерживается намеренно: секции и домены Anthropic
отбрасываются при разборе любого списка и при записи в hosts.

Наши строки живут в одном помеченном блоке; всё остальное в hosts не трогаем.
"""
from __future__ import annotations

import ipaddress
import json
import locale
import os
import re
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import winutil
from .settings import DATA_DIR, write_text_atomic

HOSTS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
BEGIN = "# >>> pipo: доступ к сервисам (управляется приложением, не редактируйте)"
END = "# <<< pipo"
ANSI = locale.getencoding()  # hosts нередко сохранён в кодовой странице Windows, а не в UTF-8
_lock = threading.Lock()

SOURCES = {
    "geohide": {
        "name": "GeoHide DNS",
        "url": "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/refs/heads/main/hosts/hosts",
        "page": "https://github.com/Internet-Helper/GeoHideDNS",
    },
    "malw": {
        "name": "dns.malw.link",
        "url": "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts",
        "page": "https://github.com/ImMALWARE/dns.malw.link",
    },
}

# Claude/Anthropic — никогда. Проверяется и по названию секции, и по каждому домену.
EXCLUDED_SECTION = re.compile(r"claude|anthropic", re.I)
EXCLUDED_DOMAIN = re.compile(r"(^|\.)(claude\.ai|claude\.com|anthropic\.com|claudeusercontent\.com|claudemcpclient\.com"
                             r"|claude\.site|anthropic\.ai|clau\.de)$|claude|anthropic", re.I)

# секции, которые показываем первыми и помечаем как нейросети
AI_HINT = re.compile(r"\bAI\b|openai|chatgpt|gemini|grok|copilot|deepl|elevenlabs|cursor|perplexity|mistral|notion|"
                     r"groq|genspark|hume|cerebras|suno|midjourney|runway|character|poe|xai", re.I)

_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$", re.I)


class HostsError(RuntimeError):
    pass


@dataclass
class Section:
    name: str
    entries: list[tuple[str, str]] = field(default_factory=list)  # (ip, domain)

    @property
    def ai(self) -> bool:
        return bool(AI_HINT.search(self.name))


def excluded(domain: str) -> bool:
    return bool(EXCLUDED_DOMAIN.search(domain))


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _routable(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 0.0.0.0 / 127.x / ::1 — это блокировка или localhost, не обход
    return not (a.is_unspecified or a.is_loopback or a.is_private or a.is_multicast or a.is_reserved)


def parse(text: str, dropped: list[dict] | None = None) -> list[Section]:
    """Секции по заголовкам «# Название». Без Claude/Anthropic и без 0.0.0.0-блокировок.
    dropped — если передан список, в него пишется каждая отброшенная строка с причиной."""
    sections: list[Section] = []
    cur: Section | None = None

    def drop(reason: str, line: str) -> None:
        if dropped is not None:
            dropped.append({"section": cur.name if cur else "", "reason": reason, "line": line})

    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            # служебные шапки и одиночные IP в комментариях — не секции
            if line.startswith("###") or not title or _is_ip(title) \
                    or title.lower().startswith(("последнее обновление", "регион", "эти ip", "остальные ip")):
                continue
            cur = Section(title)
            sections.append(cur)
            continue
        parts = line.split()
        if len(parts) < 2:
            drop("не строка hosts", line)
            continue
        ip, domain = parts[0], parts[1].lower()
        if cur is not None and EXCLUDED_SECTION.search(cur.name):
            drop("секция Claude/Anthropic", line)
            continue
        if excluded(domain):
            drop("домен Claude/Anthropic", line)
            continue
        if not _routable(ip):
            drop("не прокси (0.0.0.0/localhost — блокировка)", line)
            continue
        if not _DOMAIN.match(domain):
            drop("некорректный домен", line)
            continue
        if cur is None:
            cur = Section("Прочее")
            sections.append(cur)
        cur.entries.append((ip, domain))
    return [s for s in sections if s.entries and not EXCLUDED_SECTION.search(s.name)]


# ---------- кеш списков и состояние ----------

def _cache(source: str) -> Path:
    return DATA_DIR / "hosts" / f"{source}.txt"


def _state_file() -> Path:
    return DATA_DIR / "hosts.json"


def load_state() -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": "geohide", "sections": [], "applied_at": None}


def save_state(st: dict) -> None:
    write_text_atomic(_state_file(), json.dumps(st, ensure_ascii=False, indent=2))


def fetch(source: str, fetch_fn=None) -> list[Section]:
    if source not in SOURCES:
        raise HostsError("неизвестный источник")
    from . import updater
    fetch_fn = fetch_fn or (lambda u: updater.http_get(u, 20).decode("utf-8", "replace"))
    text = fetch_fn(SOURCES[source]["url"])
    secs = parse(text)
    if len(secs) < 3:
        raise HostsError(f"{SOURCES[source]['name']}: список подозрительно короткий — не сохраняю")
    write_text_atomic(_cache(source), text)
    return secs


def sections(source: str) -> list[Section]:
    try:
        return parse(_cache(source).read_text(encoding="utf-8"))
    except OSError:
        return []


def cache_time(source: str) -> float | None:
    try:
        return _cache(source).stat().st_mtime
    except OSError:
        return None


# ---------- hosts ----------

def _read_raw() -> bytes:
    try:
        return HOSTS.read_bytes()
    except OSError as e:
        raise HostsError(f"не читается {HOSTS}: {e}") from e


def _decode(line: bytes) -> str:
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return line.decode(ANSI, "replace")


def split_block(raw: bytes, replacing: set[str] = frozenset()) -> tuple[list[bytes], list[str]]:
    """(строки пользователя байт в байт, строки нашего блока).

    Блок — только BEGIN…END. Если END кто-то стёр, хвост после BEGIN считается
    строками пользователя: лишнее не удалим, а сам BEGIN выкинем и запишем блок заново.
    Из такого хвоста выпадают только записи на домены из replacing — те, что мы пишем
    заново: иначе старый IP выше нового блока перекрыл бы свежий (hosts берёт первое совпадение).
    """
    out: list[bytes] = []
    ours: list[str] = []
    pending: list[bytes] | None = None
    for b in raw.splitlines():
        s = _decode(b).strip()
        if pending is None:
            if s == BEGIN:
                pending = []
            else:
                out.append(b)
        elif s == END:
            ours += [_decode(x) for x in pending]
            pending = None
        else:
            pending.append(b)
    if pending is not None:
        out += [b for b in pending if _entry_domain(_decode(b)) not in replacing]
    while out and not out[-1].strip():
        out.pop()
    return out, ours


def _entry_domain(line: str) -> str | None:
    """«1.2.3.4 example.com» → example.com; комментарии и прочее — None."""
    parts = line.split("#", 1)[0].split()
    return parts[1].lower() if len(parts) == 2 else None


def _encoding_of(lines: list[bytes]) -> str:
    """В какой кодировке писать наш блок: в той же, что у файла (кириллический маркер)."""
    try:
        b"\n".join(lines).decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return ANSI


def render_block(entries: list[tuple[str, str]]) -> list[str]:
    seen, lines = set(), []
    for ip, domain in entries:
        if excluded(domain) or domain in seen:  # второй рубеж: Anthropic не пишем никогда
            continue
        seen.add(domain)
        lines.append(f"{ip} {domain}")
    return lines


def _backup_original() -> None:
    dest = DATA_DIR / "backups" / "hosts.original"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(HOSTS.read_bytes() if HOSTS.exists() else b"")


def write_hosts(entries: list[tuple[str, str]]) -> int:
    with _lock:
        lines = render_block(entries)
        base, _ = split_block(_read_raw(), replacing={l.split()[1].lower() for l in lines})
        enc = _encoding_of(base)
        block = "\r\n".join([BEGIN, *lines, END]).encode(enc, "replace")
        data = b"\r\n".join(base) + (b"\r\n\r\n" + block if lines else b"") + b"\r\n"
        _backup_original()
        tmp = HOSTS.with_name(f"hosts.pipo-{os.getpid()}-{threading.get_ident()}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, HOSTS)
        except PermissionError as e:
            raise HostsError("нет доступа к hosts — нужны права администратора, либо файл заблокирован антивирусом") from e
        finally:
            tmp.unlink(missing_ok=True)
    winutil.run(["ipconfig", "/flushdns"])
    return len(lines)


def apply(source: str, names: list[str]) -> dict:
    if source not in SOURCES:
        raise HostsError("неизвестный источник")
    names = [n for n in names if not EXCLUDED_SECTION.search(n)]
    secs = {s.name: s for s in sections(source)}
    if names and not secs:
        raise HostsError("список ещё не загружен — нажмите «Обновить списки»")
    entries = [e for n in names if n in secs for e in secs[n].entries]
    count = write_hosts(entries)
    st = {"source": source, "sections": [n for n in names if n in secs], "applied_at": time.time() if count else None}
    save_state(st)
    return st | {"written": count}


def remove() -> None:
    write_hosts([])
    save_state(load_state() | {"sections": [], "applied_at": None})


def status() -> dict:
    """Что сейчас реально в hosts. Если блок пропал — его откатил антивирус или кто-то вручную."""
    st = load_state()
    try:
        _, ours = split_block(_read_raw())
        readable = True
    except HostsError:
        ours, readable = [], False
    in_hosts = len([l for l in ours if l.strip() and not l.startswith("#")])
    expected = bool(st.get("sections"))
    return {
        **st,
        "hosts_path": str(HOSTS),
        "readable": readable,
        "in_hosts": in_hosts,
        "reverted": expected and in_hosts == 0,
        "backup": str(DATA_DIR / "backups" / "hosts.original"),
    }


def check(domain: str) -> dict:
    """Куда сейчас резолвится домен и отвечает ли он по HTTPS."""
    from .scan import _run_curl
    if excluded(domain):
        raise HostsError("Claude/Anthropic не поддерживаются")
    try:
        ip = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)[0][4][0]
    except socket.gaierror as e:
        return {"domain": domain, "ip": None, "ok": False, "detail": f"DNS: {e}"}
    code, out, err = _run_curl(["-s", "-S", "-o", "NUL", "-m", "8", "-w", "%{http_code}", f"https://{domain}/"], 12)
    ok = code == 0 and out[:1] in ("2", "3")
    detail = f"HTTP {out}" if code == 0 else (err or f"ошибка {code}")[:160]
    return {"domain": domain, "ip": ip, "ok": ok, "detail": detail}


def overview() -> dict:
    out = {"status": status(), "sources": {}}
    for key, meta in SOURCES.items():
        secs = sections(key)
        out["sources"][key] = {
            **meta,
            "updated": cache_time(key),
            # в списках у домена бывает по 4 IP прокси; в hosts пишется один — считаем уникальные домены
            "sections": [{"name": s.name, "ai": s.ai, "count": len(dict.fromkeys(d for _, d in s.entries)),
                          "domains": list(dict.fromkeys(d for _, d in s.entries)), "ips": sorted({ip for ip, _ in s.entries})}
                         for s in sorted(secs, key=lambda s: (not s.ai, s.name.lower()))],
        }
    return out
