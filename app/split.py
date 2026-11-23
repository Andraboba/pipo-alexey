"""Сплит-туннелирование: что идёт через запрет, а что — напрямую.

Запрет не прокси: он «ломает» DPI только для трафика, попавшего под его
списки. Поэтому сплит — это управление списками:

    домен  + «через запрет» -> lists/list-general-user.txt
    домен  + «напрямую»     -> lists/list-exclude-user.txt
    IP/CIDR + «через запрет»-> добавляется в lists/ipset-all.txt
    IP/CIDR + «напрямую»    -> lists/ipset-exclude-user.txt (исключение сильнее включения)

Игровые профили — наборы подсетей в lists/ipset-<slug>.txt (например iRacing).
У профиля три состояния: off (не трогаем), zapret, direct.

ipset-all.txt собирается как «базовый список» (data/ipset-base.txt, обновляется
кнопкой «Обновить IPSet») + всё, что пользователь направил через запрет.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path

from . import zapret
from .settings import DATA_DIR, write_text_atomic

PLACEHOLDER_IP = zapret.PLACEHOLDER_IP
PLACEHOLDER_DOMAIN = zapret.PLACEHOLDER_DOMAIN
ROUTES_RULE = ("direct", "zapret")
ROUTES_PROFILE = ("off", "direct", "zapret")
HEADER = "# Managed by Pipo Alexey. Edit rules in the UI, manual edits will be overwritten.\n"

_lock = threading.RLock()


class SplitError(ValueError):
    pass


@dataclass
class Rule:
    value: str
    kind: str  # domain | ip | geo (value — код страны ISO, например RU)
    route: str  # direct | zapret
    note: str = ""
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class Profile:
    name: str
    slug: str
    route: str = "off"
    note: str = ""
    created_by_app: bool = False
    # домены игры (лаунчер, сайт, API) — идут тем же маршрутом, что и подсети
    domains: list[str] = field(default_factory=list)
    # автономные системы серверов игры; их анонсируемые префиксы кешируются в data/asn
    asns: list[int] = field(default_factory=list)
    preset: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class State:
    rules: list[Rule] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    ipset_all_sha: str | None = None  # что мы записали в ipset-all.txt последним
    applied_at: float | None = None


# ---------- нормализация ----------

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")


def normalize(raw: str) -> tuple[str, str]:
    """('domain'|'ip', нормализованное значение). Принимает и ссылки целиком."""
    v = (raw or "").strip()
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v, flags=re.I)
    v = re.split(r"[/?#]", v, maxsplit=1)[0] if not _looks_like_cidr(v) else v
    if not v:
        raise SplitError("пустое значение")
    try:
        net = ipaddress.ip_network(v.strip("[]"), strict=False)
        full = net.prefixlen == net.max_prefixlen
        return "ip", str(net.network_address) if full else str(net)
    except ValueError:
        pass
    host = v.rsplit("@", 1)[-1]
    host = re.sub(r":\d+$", "", host).lstrip("*.").rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as e:
        raise SplitError(f"некорректный домен: {raw}") from e
    if not _DOMAIN_RE.match(host):
        raise SplitError(f"это не похоже ни на домен, ни на IP/подсеть: {raw}")
    return "domain", host


def _looks_like_cidr(v: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F:.]+/\d{1,3}$", v))


def parse_networks(text: str) -> tuple[list[str], list[str]]:
    """Строки подсетей -> (валидные, ошибочные). Комментарии # и пустые строки пропускаем."""
    good, bad, seen = [], [], set()
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith(("#", ";", "//")):
            continue
        try:
            net = str(ipaddress.ip_network(line, strict=False))
        except ValueError:
            bad.append(line)
            continue
        if net not in seen:
            seen.add(net)
            good.append(net)
    return good, bad


_cover_cache: dict[tuple, dict] = {}


def _intervals(pool: list[str]) -> dict[int, tuple[list[int], list[int]]]:
    key = (len(pool), hash(tuple(pool[:50])), hash(tuple(pool[-50:])))
    if key in _cover_cache:
        return _cover_cache[key]
    by_ver: dict[int, list] = {4: [], 6: []}
    for s in pool:
        try:
            net = ipaddress.ip_network(s, strict=False)
        except ValueError:
            continue
        by_ver[net.version].append(net)
    out = {}
    for ver, nets in by_ver.items():
        merged = list(ipaddress.collapse_addresses(nets))
        out[ver] = ([int(n.network_address) for n in merged], [int(n.broadcast_address) for n in merged])
    if len(_cover_cache) > 8:
        _cover_cache.pop(next(iter(_cover_cache)))
    _cover_cache[key] = out
    return out


def coverage(nets: list[str], pool: list[str]) -> int:
    """Сколько подсетей из nets целиком входят в pool (с учётом более крупных подсетей)."""
    from bisect import bisect_right
    iv = _intervals(pool)
    n_cov = 0
    for s in nets:
        n = ipaddress.ip_network(s, strict=False)
        starts, ends = iv[n.version]
        i = bisect_right(starts, int(n.network_address)) - 1
        if i >= 0 and ends[i] >= int(n.broadcast_address):
            n_cov += 1
    return n_cov


def read_list(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith(("#", ";", "//"))]


# ---------- хранилище ----------

def _state_file() -> Path:
    return DATA_DIR / "split.json"


def base_file() -> Path:
    return DATA_DIR / "ipset-base.txt"


def lists_dir(zdir: Path) -> Path:
    return zdir / "lists"


def profile_file(zdir: Path, p: Profile) -> Path:
    return lists_dir(zdir) / f"ipset-{p.slug}.txt"


def _save_state(st: State) -> None:
    write_text_atomic(_state_file(), json.dumps(asdict(st), indent=2, ensure_ascii=False))


def load(zdir: Path) -> State:
    with _lock:
        sf = _state_file()
        try:
            raw = json.loads(sf.read_text(encoding="utf-8"))
            return State(
                rules=[_from_dict(Rule, r) for r in raw.get("rules", [])],
                profiles=[_from_dict(Profile, p) for p in raw.get("profiles", [])],
                ipset_all_sha=raw.get("ipset_all_sha"),
                applied_at=raw.get("applied_at"),
            )
        except FileNotFoundError:
            pass
        except (ValueError, TypeError, AttributeError):
            # битый файл не затираем молча: откладываем рядом, правила можно достать руками.
            # Не удалось отложить — ошибка наружу, но не bootstrap поверх правил.
            sf.replace(sf.with_name(f"{sf.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"))
        # прочие OSError (файл занят антивирусом, нет доступа) — это не порча: летят наружу, файл цел
        st = _bootstrap(zdir)
        _save_state(st)
        return st


def _from_dict(cls, d: dict):
    """Поля из другой версии приложения не ломают загрузку."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


def _bootstrap(zdir: Path) -> State:
    """Первый запуск: импортируем то, что уже есть в пользовательских списках запрета."""
    L = lists_dir(zdir)
    st = State()
    for fname, route in (("list-general-user.txt", "zapret"), ("list-exclude-user.txt", "direct")):
        for line in read_list(L / fname):
            if line == PLACEHOLDER_DOMAIN:
                continue
            try:
                kind, val = normalize(line)
                st.rules.append(Rule(value=val, kind=kind, route=route, note="импорт"))
            except SplitError:
                pass
    profile_sets: dict[str, set[str]] = {}
    for f in sorted(L.glob("ipset-*.txt")):
        slug = f.stem[len("ipset-"):]
        if slug.startswith(("all", "exclude")):
            continue
        nets, _ = parse_networks(f.read_text(encoding="utf-8-sig", errors="replace"))
        profile_sets[slug] = set(nets)
        from . import presets
        pr = presets.get(slug)
        st.profiles.append(Profile(
            name=pr["name"] if pr else _pretty(slug), slug=slug,
            domains=list(pr["domains"]) if pr else [],
            asns=[a["asn"] for a in pr["asns"]] if pr else [],
            preset=slug if pr else None,
        ))
    exclude_user = set(read_list(L / "ipset-exclude-user.txt"))
    for line in exclude_user - {PLACEHOLDER_IP}:
        if not any(line in s for s in profile_sets.values()):
            try:
                kind, val = normalize(line)
                st.rules.append(Rule(value=val, kind=kind, route="direct", note="импорт"))
            except SplitError:
                pass
    current_all = read_list(zapret.ipset_all(zdir) if zapret.ipset_mode(zdir) == "loaded" else L / "ipset-all.txt.backup")
    for p in st.profiles:
        nets = profile_sets.get(p.slug, set())
        if nets and nets <= exclude_user:
            p.route = "direct"
        elif nets and coverage(sorted(nets), current_all) == len(nets):
            p.route = "zapret"
    _ensure_base(zdir, profile_sets)
    return st


def _pretty(slug: str) -> str:
    return {"iracing": "iRacing"}.get(slug.lower(), slug.replace("-", " ").replace("_", " ").title())


# ---------- GeoIP ----------
# Диапазоны стран из данных региональных регистраторов (RIR), обновляются ежедневно.
GEO_URLS = [
    "https://raw.githubusercontent.com/ipverse/country-ip-blocks/master/country/{cc}/ipv{v}-aggregated.txt",
    "https://raw.githubusercontent.com/ipverse/rir-ip/master/country/{cc}/ipv{v}-aggregated.txt",
]


def geo_file(cc: str) -> Path:
    return DATA_DIR / "geo" / f"{cc.lower()}.txt"


def normalize_country(raw: str) -> str:
    cc = (raw or "").strip().upper()
    if cc.startswith("GEO:"):
        cc = cc[4:]
    if not re.fullmatch(r"[A-Z]{2}", cc):
        raise SplitError("код страны — две латинские буквы, например RU")
    return cc


def fetch_geo(cc: str, fetch=None) -> list[str]:
    """Скачать диапазоны страны (IPv4+IPv6) в data/geo/<cc>.txt."""
    from . import updater
    fetch = fetch or (lambda url: updater.http_get(url, 20).decode("utf-8", "replace"))
    nets: list[str] = []
    for v in (4, 6):
        last_err = None
        for tpl in GEO_URLS:
            try:
                nets += parse_networks(fetch(tpl.format(cc=cc.lower(), v=v)))[0]
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
        else:
            if v == 4:
                raise SplitError(f"не удалось скачать диапазоны страны {cc}: {last_err}")
    if not nets:
        raise SplitError(f"для страны {cc} нет диапазонов")
    write_text_atomic(geo_file(cc), "\n".join(nets) + "\n")
    return nets


def geo_networks(cc: str) -> list[str]:
    return read_list(geo_file(cc))


# ---------- ASN ----------
RIPESTAT_URL = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}&sourceapp=pipo-alexey"


def asn_file(asn: int) -> Path:
    return DATA_DIR / "asn" / f"AS{int(asn)}.txt"


def fetch_asn(asn: int, fetch=None) -> list[str]:
    from . import updater
    fetch = fetch or (lambda url: updater.http_get(url, 30).decode("utf-8", "replace"))
    try:
        data = json.loads(fetch(RIPESTAT_URL.format(asn=int(asn))))
        prefixes = [p["prefix"] for p in data["data"]["prefixes"]]
    except Exception as e:  # noqa: BLE001
        raise SplitError(f"RIPEstat не отдал префиксы AS{asn}: {e}") from e
    nets, _ = parse_networks("\n".join(prefixes))
    if nets:  # пустой ответ не затирает прошлый кеш
        write_text_atomic(asn_file(asn), "\n".join(nets) + "\n")
    return nets


def asn_networks(asn: int) -> list[str]:
    return read_list(asn_file(asn))


def _to_intervals(nets: list[str]) -> dict[int, list[tuple[int, int]]]:
    by_ver: dict[int, list] = {4: [], 6: []}
    for s in nets:
        try:
            n = ipaddress.ip_network(s, strict=False)
        except ValueError:
            continue
        by_ver[n.version].append(n)
    return {v: [(int(n.network_address), int(n.broadcast_address)) for n in ipaddress.collapse_addresses(ns)]
            for v, ns in by_ver.items()}


def subtract(nets: list[str], minus: list[str]) -> list[str]:
    """nets − minus по диапазонам адресов (а не по строкам), результат — минимальный набор CIDR."""
    a, b = _to_intervals(nets), _to_intervals(minus)
    out: list[str] = []
    for v, cls in ((4, ipaddress.IPv4Address), (6, ipaddress.IPv6Address)):
        holes, j = b[v], 0
        for start, end in a[v]:
            cur = start
            while j < len(holes) and holes[j][1] < cur:
                j += 1
            k = j
            while k < len(holes) and holes[k][0] <= end and cur <= end:
                hs, he = holes[k]
                if hs > cur:
                    out += [str(n) for n in ipaddress.summarize_address_range(cls(cur), cls(hs - 1))]
                cur = max(cur, he + 1)
                k += 1
            if cur <= end:
                out += [str(n) for n in ipaddress.summarize_address_range(cls(cur), cls(end))]
    return out


def _ensure_base(zdir: Path, profile_sets: dict[str, set[str]] | None = None) -> None:
    if base_file().exists():
        return
    L = lists_dir(zdir)
    src = zapret.ipset_all(zdir) if zapret.ipset_mode(zdir) == "loaded" else L / "ipset-all.txt.backup"
    lines = read_list(src)
    # если ipset-all уже содержит вмёрженный профиль (add-iracing-ipset.ps1) и есть
    # «чистая» копия до слияния — берём её как базу
    for pre in L.glob("ipset-all.txt.pre-*"):
        slug = pre.name.split(".pre-", 1)[1]
        prof = (profile_sets or {}).get(slug) or set(read_list(L / f"ipset-{slug}.txt"))
        pre_lines = read_list(pre)
        if pre_lines and set(pre_lines) | prof == set(lines):
            lines = pre_lines
            break
    write_text_atomic(base_file(), "\n".join(lines) + ("\n" if lines else ""))


def set_base(lines: list[str]) -> None:
    write_text_atomic(base_file(), "\n".join(lines) + "\n")


# ---------- операции ----------

def _find(items, item_id: str):
    for it in items:
        if it.id == item_id:
            return it
    raise SplitError("не найдено")


def add_rule(zdir: Path, value: str, route: str, note: str = "", kind: str | None = None) -> Rule:
    if route not in ROUTES_RULE:
        raise SplitError("route: direct или zapret")
    if kind == "geo" or str(value).strip().lower().startswith("geo:"):
        kind, val = "geo", normalize_country(value)
        if not geo_networks(val):
            fetch_geo(val)
    else:
        kind, val = normalize(value)
    with _lock:
        st = load(zdir)
        for r in st.rules:
            if r.value == val and r.kind == kind:
                r.route, r.enabled = route, True
                if note:
                    r.note = note
                apply(zdir, st)
                return r
        rule = Rule(value=val, kind=kind, route=route, note=note.strip()[:200])
        st.rules.append(rule)
        apply(zdir, st)
        return rule


def update_rule(zdir: Path, rule_id: str, patch: dict) -> Rule:
    with _lock:
        st = load(zdir)
        r = _find(st.rules, rule_id)
        if "route" in patch:
            if patch["route"] not in ROUTES_RULE:
                raise SplitError("route: direct или zapret")
            r.route = patch["route"]
        if "enabled" in patch:
            r.enabled = bool(patch["enabled"])
        if "note" in patch:
            r.note = str(patch["note"]).strip()[:200]
        apply(zdir, st)
        return r


def delete_rule(zdir: Path, rule_id: str) -> None:
    with _lock:
        st = load(zdir)
        st.rules.remove(_find(st.rules, rule_id))
        apply(zdir, st)


def _slugify(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "game"
    if base.startswith(("all", "exclude")):
        base = "game-" + base
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def manual_networks(zdir: Path, p: Profile) -> list[str]:
    """Подсети из файла lists/ipset-<slug>.txt (редактируются вручную)."""
    try:
        return parse_networks(profile_file(zdir, p).read_text(encoding="utf-8-sig", errors="replace"))[0]
    except OSError:
        return []


def profile_networks(zdir: Path, p: Profile) -> list[str]:
    """Ручные подсети + префиксы ASN профиля."""
    nets = manual_networks(zdir, p)
    for asn in p.asns:
        nets += asn_networks(asn)
    return list(dict.fromkeys(nets))


def _write_profile_networks(zdir: Path, p: Profile, text: str) -> None:
    good, bad = parse_networks(text)
    if bad:
        raise SplitError("не похоже на IP/подсеть: " + ", ".join(bad[:5]) + (" …" if len(bad) > 5 else ""))
    write_text_atomic(profile_file(zdir, p), "\n".join(good) + ("\n" if good else ""))


def add_profile(zdir: Path, name: str, networks: str, route: str = "off", domains=None, asns=None,
                preset: str | None = None) -> Profile:
    name = name.strip()[:60]
    if not name:
        raise SplitError("нужно название")
    if route not in ROUTES_PROFILE:
        raise SplitError("route: off, direct или zapret")
    with _lock:
        st = load(zdir)
        taken = {p.slug for p in st.profiles} | {f.stem[len("ipset-"):] for f in lists_dir(zdir).glob("ipset-*.txt")}
        p = Profile(name=name, slug=_slugify(preset or name, taken), route=route, created_by_app=True,
                    domains=_clean_domains(domains or []), asns=_clean_asns(asns or []), preset=preset)
        if preset and any(x.preset == preset for x in st.profiles):
            raise SplitError(f"профиль «{name}» уже добавлен")
        for asn in p.asns:
            if not asn_networks(asn):
                fetch_asn(asn)
        _write_profile_networks(zdir, p, networks)
        st.profiles.append(p)
        apply(zdir, st)
        return p


def _clean_domains(items) -> list[str]:
    out = []
    for raw in items if isinstance(items, list) else str(items).splitlines():
        if not str(raw).strip() or str(raw).strip().startswith("#"):
            continue
        kind, val = normalize(str(raw))
        if kind != "domain":
            raise SplitError(f"в списке доменов IP-адрес: {raw}")
        if val not in out:
            out.append(val)
    return out


def _clean_asns(items) -> list[int]:
    out = []
    for raw in items if isinstance(items, list) else re.split(r"[\s,;]+", str(items)):
        s = str(raw).strip().upper().removeprefix("AS")
        if not s:
            continue
        if not s.isdigit() or not 0 < int(s) < 2**32:
            raise SplitError(f"некорректный номер ASN: {raw}")
        if int(s) not in out:
            out.append(int(s))
    return out


def refresh_profile_asns(zdir: Path, profile_id: str | None = None, log=print) -> int:
    """Перекачать префиксы ASN (одного профиля или всех) и пересобрать списки."""
    with _lock:
        st = load(zdir)
        targets = [p for p in st.profiles if profile_id in (None, p.id)]
    total = 0
    for p in targets:
        for asn in p.asns:
            nets = fetch_asn(asn)
            total += len(nets)
            log(f"{p.name}: AS{asn} — {len(nets)} префиксов")
    apply(zdir)
    return total


def update_profile(zdir: Path, profile_id: str, patch: dict) -> Profile:
    with _lock:
        st = load(zdir)
        p = _find(st.profiles, profile_id)
        if "route" in patch:
            if patch["route"] not in ROUTES_PROFILE:
                raise SplitError("route: off, direct или zapret")
            p.route = patch["route"]
        if "name" in patch and str(patch["name"]).strip():
            p.name = str(patch["name"]).strip()[:60]
        if "networks" in patch:
            _write_profile_networks(zdir, p, str(patch["networks"]))
        if "domains" in patch:
            p.domains = _clean_domains(patch["domains"])
        if "asns" in patch:
            p.asns = _clean_asns(patch["asns"])
            for asn in p.asns:
                if not asn_networks(asn):
                    fetch_asn(asn)
        apply(zdir, st)
        return p


def delete_profile(zdir: Path, profile_id: str) -> None:
    with _lock:
        st = load(zdir)
        p = _find(st.profiles, profile_id)
        st.profiles.remove(p)
        apply(zdir, st)
        if p.created_by_app:
            profile_file(zdir, p).unlink(missing_ok=True)


# ---------- сборка файлов ----------

def _zapret_extra(zdir: Path, st: State) -> list[str]:
    """Всё, что пользователь явно направил через запрет поверх базы."""
    extra = [r.value for r in st.rules if r.enabled and r.kind == "ip" and r.route == "zapret"]
    for r in st.rules:
        if r.enabled and r.kind == "geo" and r.route == "zapret":
            extra += geo_networks(r.value)
    for p in st.profiles:
        if p.route == "zapret":
            extra += profile_networks(zdir, p)
    return extra


def _merged_ipset(zdir: Path, st: State) -> list[str]:
    lines = read_list(base_file())
    seen = set(lines)
    for e in _zapret_extra(zdir, st):
        if e not in seen:
            seen.add(e)
            lines.append(e)
    return lines


def geo_direct_networks(zdir: Path, st: State) -> list[str]:
    """Страны «напрямую» минус всё, что должно идти через запрет (база Flowseal,
    ваши IP-правила и игровые профили). Иначе заблокированные ресурсы, живущие на
    IP этой страны, перестали бы обходиться."""
    geo = [n for r in st.rules if r.enabled and r.kind == "geo" and r.route == "direct" for n in geo_networks(r.value)]
    if not geo:
        return []
    return subtract(geo, read_list(base_file()) + _zapret_extra(zdir, st))


def render(zdir: Path, st: State) -> dict[str, str]:
    """Имя файла в lists/ -> содержимое (без ipset-all, он отдельно)."""
    dom = lambda route: [r.value for r in st.rules if r.enabled and r.kind == "domain" and r.route == route]
    inc, exc = dom("zapret"), dom("direct")
    for p in st.profiles:
        if p.route == "zapret":
            inc += p.domains
        elif p.route == "direct":
            exc += p.domains
    inc, exc = list(dict.fromkeys(inc)), [d for d in dict.fromkeys(exc) if d not in inc]
    ip_direct = [r.value for r in st.rules if r.enabled and r.kind == "ip" and r.route == "direct"]
    for p in st.profiles:
        if p.route == "direct":
            ip_direct += profile_networks(zdir, p)
    ip_direct = list(dict.fromkeys(ip_direct + geo_direct_networks(zdir, st)))
    return {
        "list-general-user.txt": "# Never leave this file empty\n" + HEADER + "\n".join(inc or [PLACEHOLDER_DOMAIN]) + "\n",
        "list-exclude-user.txt": HEADER + "\n".join(exc or [PLACEHOLDER_DOMAIN]) + "\n",
        # без комментариев: ipset-файлы держим максимально простыми; заглушка гарантирует,
        # что файл не пустой (пустой ipset = «все адреса» = исключить всё)
        "ipset-exclude-user.txt": "\n".join([PLACEHOLDER_IP] + ip_direct) + "\n",
    }


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _backup_originals(zdir: Path) -> None:
    """Перед первой записью сохраняем исходные пользовательские файлы."""
    dest = DATA_DIR / "backups" / "lists-original"
    if dest.exists():
        return
    dest.mkdir(parents=True)
    for name in ("list-general-user.txt", "list-exclude-user.txt", "ipset-exclude-user.txt", "ipset-all.txt", "ipset-all.txt.backup"):
        src = lists_dir(zdir) / name
        if src.exists():
            (dest / name).write_bytes(src.read_bytes())


def _write_ipset_all(zdir: Path, st: State, mode: str) -> None:
    all_file = zapret.ipset_all(zdir)
    # кто-то обновил ipset-all мимо нас (service.bat → Update IPSet List) — берём его как новую базу
    # смотрим на то, что лежит сейчас, а не на целевой режим: иначе переход в «Все» затрёт свежий список
    cur_sha = _sha(all_file)
    if zapret.ipset_mode(zdir) == "loaded" and st.ipset_all_sha and cur_sha and cur_sha != st.ipset_all_sha:
        set_base(read_list(all_file))
    merged = _merged_ipset(zdir, st)
    if not merged:
        raise SplitError("базовый IPSet пуст — нажмите «Обновить IPSet»")
    text = "\n".join(merged) + "\n"
    write_text_atomic(lists_dir(zdir) / "ipset-all.txt.backup", text)
    if mode == "loaded":
        write_text_atomic(all_file, text)
    elif mode == "none":
        write_text_atomic(all_file, PLACEHOLDER_IP + "\n")
    else:  # any
        write_text_atomic(all_file, "")
    st.ipset_all_sha = _sha(all_file)


def apply(zdir: Path, st: State | None = None, ipset_mode: str | None = None) -> list[str]:
    with _lock:
        st = st or load(zdir)
        _ensure_base(zdir)
        _backup_originals(zdir)
        written = []
        for name, text in render(zdir, st).items():
            path = lists_dir(zdir) / name
            try:
                if path.read_text(encoding="utf-8") == text:
                    continue
            except OSError:
                pass
            write_text_atomic(path, text)
            written.append(name)
        before = _sha(zapret.ipset_all(zdir))
        _write_ipset_all(zdir, st, ipset_mode or zapret.ipset_mode(zdir))
        if _sha(zapret.ipset_all(zdir)) != before:
            written.append("ipset-all.txt")
        st.applied_at = time.time()
        _save_state(st)
        return written


def set_ipset_mode(zdir: Path, mode: str) -> list[str]:
    if mode not in ("loaded", "none", "any"):
        raise SplitError("режим: loaded, none или any")
    return apply(zdir, ipset_mode=mode)


def snapshot(zdir: Path) -> dict:
    st = load(zdir)
    base = read_list(base_file())
    profiles = []
    for p in st.profiles:
        nets = profile_networks(zdir, p)
        profiles.append(asdict(p) | {
            "networks": manual_networks(zdir, p),
            "total": len(nets),
            "asn_counts": {str(a): len(asn_networks(a)) for a in p.asns},
            "file": profile_file(zdir, p).name,
            # сколько подсетей игры уже накрыто общим списком Flowseal — их запрет
            # обрабатывает даже в режиме «не трогать»
            "covered_by_base": coverage(nets, base) if base else 0,
        })
    rules = []
    for r in st.rules:
        d = asdict(r)
        if r.kind == "geo":
            d["size"] = len(geo_networks(r.value))
            if r.route == "direct":
                # сколько подсетей базового списка блокировок лежит в этой стране — они
                # останутся через запрет
                d["kept_blocked"] = coverage(base, geo_networks(r.value)) if base else 0
        rules.append(d)
    return {
        "rules": rules,
        "profiles": profiles,
        "base_size": len(base),
        "applied_at": st.applied_at,
    }
