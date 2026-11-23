"""Проверка и установка обновлений запрета и TG WS Proxy с GitHub.

Ничего не скачивается без явного подтверждения: проверка только читает номер
версии, а установка запускается отдельным запросом с confirm=true.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import platform
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from . import split, suspend, tgproxy, zapret
from .jobs import Job
from .settings import DATA_DIR, write_text_atomic

ZAPRET_REPO = "Flowseal/zapret-discord-youtube"
TG_REPO = "Flowseal/tg-ws-proxy"
ZAPRET_VERSION_URL = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/version.txt"
IPSET_URL = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
USER_AGENT = "pipo-alexey"

# Файлы, которые при обновлении запрета не трогаем: пользовательские списки,
# собранный нами ipset-all и переключатели service.bat.
PRESERVE = [
    "lists/*-user.txt",
    "lists/ipset-all.txt",
    "lists/ipset-all.txt.backup",
    "utils/*.enabled",
]


class UpdateError(RuntimeError):
    pass


# ---------- HTTP ----------

def http_get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dest: Path, sha256: str | None, job: Job | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if job and total:
                job.progress = done / total
    if sha256 and h.hexdigest().lower() != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise UpdateError("контрольная сумма скачанного файла не совпала — файл не установлен")
    tmp.replace(dest)
    if job:
        job.progress = None
        job.say(f"Скачано {done / 1024 / 1024:.1f} МБ" + (", sha256 совпадает" if sha256 else ""))
        if not sha256:
            job.say("GitHub не прислал контрольную сумму — файл не проверен", "warn")
    return dest


# ---------- версии ----------

def parse_version(v: str | None) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) or (0,)


def is_newer(remote: str | None, local: str | None) -> bool:
    if not remote:
        return False
    if not local:
        return True
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def latest_release(repo: str) -> dict:
    data = json.loads(http_get(f"https://api.github.com/repos/{repo}/releases/latest"))
    assets = []
    for a in data.get("assets", []):
        digest = a.get("digest") or ""
        assets.append({
            "name": a["name"],
            "url": a["browser_download_url"],
            "size": a.get("size"),
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None,
        })
    return {
        "version": data["tag_name"],
        "published": data.get("published_at"),
        "page": data.get("html_url"),
        "notes": (data.get("body") or "")[:4000],
        "assets": assets,
    }


_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 30 * 60


def _cached_release(repo: str, force: bool) -> dict:
    hit = _cache.get(repo)
    if hit and not force and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    rel = latest_release(repo)
    _cache[repo] = (time.time(), rel)
    return rel


def check(zdir: Path, force: bool = False) -> dict:
    out = {}
    zl = zapret.local_version(zdir)
    try:
        rel = _cached_release(ZAPRET_REPO, force)
        out["zapret"] = {"local": zl, "latest": rel["version"], "newer": is_newer(rel["version"], zl),
                         "published": rel["published"], "page": rel["page"], "notes": rel["notes"]}
    except Exception as e:  # noqa: BLE001
        try:  # запасной путь — тот же файл, что читает service.bat
            v = http_get(ZAPRET_VERSION_URL, 8).decode().strip()
            out["zapret"] = {"local": zl, "latest": v, "newer": is_newer(v, zl)}
        except Exception:  # noqa: BLE001
            out["zapret"] = {"local": zl, "error": f"не удалось проверить: {e}"}
    exe = tgproxy.find_exe()
    tl = tgproxy.local_version(exe)
    try:
        rel = _cached_release(TG_REPO, force)
        out["tg"] = {"local": tl, "installed": exe is not None, "latest": rel["version"],
                     "newer": is_newer(rel["version"], tl) if exe else False,
                     "published": rel["published"], "page": rel["page"], "notes": rel["notes"]}
    except Exception as e:  # noqa: BLE001
        out["tg"] = {"local": tl, "installed": exe is not None, "error": f"не удалось проверить: {e}"}
    out["checked_at"] = time.time()
    return out


# ---------- обновление запрета ----------

def is_preserved(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel.lower(), pat) for pat in PRESERVE)


def safe_extract(zip_path: Path, dest: Path) -> Path:
    """Распаковка с защитой от путей ../ ; возвращает корневую папку релиза."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            p = PurePosixPath(info.filename.replace("\\", "/"))
            if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
                raise UpdateError(f"подозрительный путь в архиве: {info.filename}")
        z.extractall(dest)
    entries = [e for e in dest.iterdir()]
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else dest
    if not (root / "service.bat").is_file() or not (root / "bin" / "winws.exe").is_file():
        raise UpdateError("в архиве нет service.bat / bin/winws.exe — это не похоже на релиз запрета")
    return root


def plan_files(new_root: Path) -> tuple[list[str], list[str]]:
    """(копируем, пропускаем как пользовательские) — относительные пути с '/'."""
    copy, keep = [], []
    for f in sorted(new_root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(new_root).as_posix()
            (keep if is_preserved(rel) else copy).append(rel)
    return copy, keep


def install_files(new_root: Path, zdir: Path, files: list[str], backup_zip: Path, job: Job | None = None) -> None:
    """Копирует файлы релиза поверх zdir. Перезаписываемые файлы сначала уходят в backup_zip;
    при любой ошибке всё возвращается как было."""
    backup_zip.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as bz:
        for rel in files:
            target = zdir / rel
            if target.is_file():
                bz.write(target, rel)
    try:
        for rel in files:
            target = zdir / rel
            if not target.exists():
                created.append(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".pipo-new")
            shutil.copy2(new_root / rel, tmp)
            tmp.replace(target)
    except Exception:
        if job:
            job.say("Откат: возвращаю прежние файлы", "warn")
        with zipfile.ZipFile(backup_zip) as bz:
            bz.extractall(zdir)
        for p in created:
            p.unlink(missing_ok=True)
        raise


def update_zapret(job: Job, zdir: Path, expected: str | None) -> dict:
    old = zapret.local_version(zdir)
    rel = _cached_release(ZAPRET_REPO, force=True)
    ver = rel["version"]
    if expected and ver != expected:
        raise UpdateError(f"на GitHub уже другая версия ({ver}), проверьте обновления ещё раз")
    asset = next((a for a in rel["assets"] if a["name"].lower().endswith(".zip")), None)
    if not asset:
        raise UpdateError("в релизе нет .zip")
    job.say(f"Скачиваю {asset['name']}")
    dl = DATA_DIR / "downloads"
    zip_path = download(asset["url"], dl / asset["name"], asset["sha256"], job)
    new_root = safe_extract(zip_path, dl / f"zapret-{ver}")
    copy, keep = plan_files(new_root)
    job.say(f"Файлов к установке: {len(copy)}; сохраняю ваши: {', '.join(keep) or '—'}")

    strategy = zapret.installed_strategy()
    backup = DATA_DIR / "backups" / f"zapret-{old or 'unknown'}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    job.say("Останавливаю запрет и драйвер WinDivert")
    # что бы ни случилось с файлами, запрет вернётся в прежнее состояние
    with suspend.suspended(zdir, job.say, stop_driver=True) as was:
        install_files(new_root, zdir, copy, backup, job)
        write_text_atomic(zdir / "version.txt", ver)
        job.say(f"Файлы обновлены, бэкап прежних: {backup}")

        try:
            split.apply(zdir)
            job.say("Сплит-правила и игровые профили применены заново")
        except Exception as e:  # noqa: BLE001
            job.say(f"Не удалось применить сплит-правила: {e}", "warn")

        if was.service is not None and strategy:
            if strategy in zapret.list_strategies(zdir):
                zapret.reconfigure_service(zdir)
                job.say(f"Служба перенастроена на стратегию «{strategy}» из новой версии")
            else:
                job.say(f"Стратегии «{strategy}» нет в новой версии — выберите другую", "warn")
    shutil.rmtree(new_root.parent if new_root.parent.name.startswith("zapret-") else new_root, ignore_errors=True)
    _cache.pop(ZAPRET_REPO, None)
    job.say(f"Готово: {old} → {ver}", "ok")
    return {"from": old, "to": ver, "backup": str(backup)}


def update_ipset(job: Job, zdir: Path) -> dict:
    job.say("Скачиваю актуальный IPSet из репозитория Flowseal")
    text = http_get(IPSET_URL, 20).decode("utf-8", errors="replace")
    nets, bad = split.parse_networks(text)
    if len(nets) < 100:
        raise UpdateError(f"список подозрительно короткий ({len(nets)} строк) — не применяю")
    split.set_base(nets)
    job.say(f"Базовый IPSet: {len(nets)} подсетей" + (f", пропущено строк: {len(bad)}" if bad else ""))
    st = split.load(zdir)
    for cc in sorted({r.value for r in st.rules if r.kind == "geo"}):
        try:
            job.say(f"GeoIP {cc}: {len(split.fetch_geo(cc))} подсетей")
        except split.SplitError as e:
            job.say(str(e), "warn")
    for p in st.profiles:
        for asn in p.asns:
            try:
                job.say(f"{p.name}: AS{asn} — {len(split.fetch_asn(asn))} префиксов")
            except split.SplitError as e:
                job.say(str(e), "warn")
    written = split.apply(zdir)
    job.say("Обновлено: " + (", ".join(written) or "ничего не изменилось"), "ok")
    return {"networks": len(nets), "written": written}


# ---------- обновление TG WS Proxy ----------

def tg_asset_name() -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "TgWsProxy_windows_arm64.exe"
    return "TgWsProxy_windows.exe"


def update_tg(job: Job, expected: str | None) -> dict:
    exe = tgproxy.find_exe()
    if not exe:
        from . import settings
        exe = Path(settings.load()["zapret_dir"]) / tgproxy.EXE_NAME
        job.say(f"TG WS Proxy не найден, установлю в {exe}")
    old = tgproxy.local_version(exe) if exe.exists() else None
    rel = _cached_release(TG_REPO, force=True)
    ver = rel["version"]
    if expected and ver != expected:
        raise UpdateError(f"на GitHub уже другая версия ({ver}), проверьте обновления ещё раз")
    name = tg_asset_name()
    asset = next((a for a in rel["assets"] if a["name"] == name), None)
    if not asset:
        raise UpdateError(f"в релизе нет {name}")
    job.say(f"Скачиваю {name}")
    new = download(asset["url"], DATA_DIR / "downloads" / name, asset["sha256"], job)

    was_running = tgproxy.running(exe)
    if was_running:
        job.say("Останавливаю TG WS Proxy")
        tgproxy.stop(exe)
        for _ in range(20):
            if not tgproxy.running(exe):
                break
            time.sleep(0.25)
    backup = None
    tmp = exe.with_name(exe.name + ".pipo-new")
    try:
        if exe.exists():
            backup = DATA_DIR / "backups" / f"TgWsProxy-{old or 'unknown'}-{time.strftime('%Y%m%d-%H%M%S')}.exe"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe, backup)
        exe.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(new, tmp)
        tmp.replace(exe)
        tgproxy.write_version(exe, ver)
        new.unlink(missing_ok=True)
        job.say(f"Установлено: {old or '—'} → {ver}" + (f", бэкап: {backup}" if backup else ""))
    finally:
        tmp.unlink(missing_ok=True)
        if was_running:  # даже если exe был занят и замена не удалась — прокси не оставляем выключенным
            try:
                tgproxy.start(exe)
                job.say("TG WS Proxy снова запущен")
            except OSError as e:
                job.say(f"Не удалось запустить TG WS Proxy: {e}", "error")
    _cache.pop(TG_REPO, None)
    job.say("Готово", "ok")
    return {"from": old, "to": ver}
