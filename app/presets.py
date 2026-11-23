"""Каталог игровых пресетов: домены + ASN серверов.

Префиксы ASN подтягиваются из RIPEstat при добавлении и кнопкой «Обновить подсети».
Все ASN проверены через RIPEstat as-overview / announced-prefixes (ноябрь 2026).
Гигантские облака (AWS, Google, Azure, Cloudflare, Akamai) сюда сознательно не входят:
целиком это половина интернета. Для игр, живущих в облаках, работают домены.

default_route — маршрут, с которым пресет добавляется по умолчанию.
probe — реальные адреса для подбора стратегии: голые домены вроде steamstatic.com сами по
себе часто не открываются (живут только поддомены), поэтому для проверки нужны конкретные хосты.
"""
from __future__ import annotations


def _a(asn: int, holder: str) -> dict:
    return {"asn": asn, "holder": holder}


PRESETS: list[dict] = [
    {
        "id": "iracing", "name": "iRacing", "confidence": "high", "default_route": "zapret",
        "probe": ["members-ng.iracing.com", "www.iracing.com"],
        "domains": ["iracing.com"],
        "asns": [_a(397127, "iRacing.com Motorsport Simulations"), _a(398123, "iRacing.com Motorsport Simulations (corporate)")],
        "note": "Свои ASN iRacing плюс 333 подсети серверов из lists/ipset-iracing.txt (AWS)",
    },
    {
        "id": "apex", "name": "Apex Legends", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.ea.com", "accounts.ea.com", "www.respawn.com"],
        "domains": ["ea.com", "origin.com", "respawn.com", "tnt-ea.com"],
        "asns": [_a(35028, "Multiplay (Unity)")],
        "note": "Сервера Multiplay; часть матчей идёт через AWS и Google Cloud",
    },
    {
        "id": "valve", "name": "Counter-Strike 2 / Dota 2", "confidence": "high", "default_route": "zapret",
        "probe": ["store.steampowered.com", "steamcommunity.com", "cdn.cloudflare.steamstatic.com"],
        "domains": ["steampowered.com", "steamcommunity.com", "steamstatic.com", "steamcontent.com", "steamserver.net",
                    "valvesoftware.com", "steam-chat.com"],
        "asns": [_a(32590, "Valve Corporation")],
        "note": "Игровые сервера и Steam Datagram Relay Valve",
    },
    {
        "id": "riot", "name": "Valorant / League of Legends", "confidence": "high", "default_route": "zapret",
        "probe": ["auth.riotgames.com", "playvalorant.com", "www.leagueoflegends.com"],
        "domains": ["riotgames.com", "leagueoflegends.com", "playvalorant.com", "pvp.net", "riotcdn.net", "lolstatic.com"],
        "asns": [_a(6507, "Riot Games (Riot Direct)"), _a(62830, "Riot Games (corporate)")],
        "note": "Авторизация и pvp.net — за Cloudflare, их покрывают домены",
    },
    {
        "id": "fortnite", "name": "Fortnite", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.epicgames.com", "www.fortnite.com", "account-public-service-prod.ol.epicgames.com"],
        "domains": ["epicgames.com", "epicgames.dev", "fortnite.com", "unrealengine.com", "epicgames.net"],
        "asns": [_a(4356, "Epic Games")],
        "note": "Игровые сервера в AWS — основное покрывают домены",
    },
    {
        "id": "pubg", "name": "PUBG: Battlegrounds", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.pubg.com", "accounts.pubg.com"],
        "domains": ["pubg.com", "playbattlegrounds.com", "krafton.com"],
        "asns": [_a(18321, "Krafton"), _a(35028, "Multiplay (Unity)")],
        "note": "Европейские сервера Multiplay; часть в Azure и AWS",
    },
    {
        "id": "r6s", "name": "Rainbow Six Siege", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.ubisoft.com", "public-ubiservices.ubi.com", "connect.ubisoft.com"],
        "domains": ["ubi.com", "ubisoft.com", "ubisoftconnect.com", "ubisoft.org", "uplay.com"],
        "asns": [],
        "note": "Сервера в Azure, у ASN Ubisoft нет анонсов — только домены",
    },
    {
        "id": "ea", "name": "Battlefield / EA FC", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.ea.com", "accounts.ea.com", "gateway.ea.com"],
        "domains": ["ea.com", "origin.com", "tnt-ea.com"],
        "asns": [_a(57052, "Electronic Arts Ireland"), _a(22220, "Electronic Arts"), _a(393349, "Electronic Arts (Santa Clara)"),
                 _a(393342, "Electronic Arts (Ashburn)"), _a(31223, "Electronic Arts (London)")],
        "note": "Онлайн-сервисы EA; EA FC частично в Google Cloud",
    },
    {
        "id": "cod", "name": "Call of Duty / Warzone", "confidence": "low", "default_route": "zapret",
        "probe": ["s.activision.com", "profile.callofduty.com"],
        "domains": ["activision.com", "callofduty.com", "demonware.net", "battle.net"],
        "asns": [_a(40551, "Activision Publishing"), _a(60229, "Demonware"), _a(57976, "Blizzard Entertainment")],
        "note": "Бэкенд Demonware и сеть Activision Blizzard; хостинг матчей не задокументирован",
    },
    {
        "id": "blizzard", "name": "Overwatch 2 / Battle.net", "confidence": "high", "default_route": "zapret",
        "probe": ["account.battle.net", "www.blizzard.com", "us.version.battle.net"],
        "domains": ["battle.net", "blizzard.com", "blz-contentstack.com"],
        "asns": [_a(57976, "Blizzard Entertainment")],
        "note": "Игровые сервера Blizzard",
    },
    {
        "id": "tarkov", "name": "Escape from Tarkov", "confidence": "low", "default_route": "zapret",
        "probe": ["www.escapefromtarkov.com", "launcher.escapefromtarkov.com", "prod.escapefromtarkov.com"],
        "domains": ["escapefromtarkov.com", "battlestategames.com", "tarkov.com"],
        "asns": [_a(199524, "G-Core Labs")],
        "note": "Европейские сервера в Gcore — это большой хостинг, через запрет пойдёт и чужое",
    },
    {
        "id": "wargaming", "name": "World of Tanks / Warships (EU)", "confidence": "medium", "default_route": "zapret",
        "probe": ["wargaming.net", "worldoftanks.eu", "worldofwarships.eu"],
        "domains": ["wargaming.net", "worldoftanks.eu", "worldofwarships.eu", "worldoftanks.com", "worldofwarships.com", "wotblitz.com"],
        "asns": [_a(210366, "Wargaming Group"), _a(203663, "Wargaming Group (HQ)"), _a(199524, "G-Core Labs")],
        "note": "Европейские сервера Wargaming; домены отвечают из Gcore",
    },
    {
        "id": "lesta", "name": "Мир танков / Мир кораблей", "confidence": "high", "default_route": "direct",
        "probe": ["lesta.games", "tanki.su", "korabli.su"],
        "domains": ["lesta.ru", "lesta.games", "tanki.su", "korabli.su", "tanksblitz.ru"],
        "asns": [_a(57572, "Lesta"), _a(210756, "EdgeCenter")],
        "note": "Российская инфраструктура Лесты — обход не нужен, лучше напрямую",
    },
    {
        "id": "rust", "name": "Rust", "confidence": "low", "default_route": "zapret",
        "probe": ["facepunch.com", "rust.facepunch.com", "playrust.com"],
        "domains": ["facepunch.com", "playrust.com"],
        "asns": [_a(56876, "GPORTAL"), _a(16276, "OVH"), _a(24940, "Hetzner")],
        "note": "Сервера сообществ на OVH, Hetzner и GPORTAL — огромные хостинги, через запрет пойдёт много лишнего",
    },
    {
        "id": "genshin", "name": "Genshin Impact", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.hoyoverse.com", "genshin.hoyoverse.com", "www.hoyolab.com"],
        "domains": ["hoyoverse.com", "mihoyo.com", "hoyolab.com", "yuanshen.com", "hoyo.link"],
        "asns": [_a(203923, "HoYoverse Network")],
        "note": "Свой ASN HoYoverse; диспетчер за Cloudflare — его покрывают домены",
    },
    {
        "id": "roblox", "name": "Roblox", "confidence": "high", "default_route": "zapret",
        "probe": ["www.roblox.com", "apis.roblox.com", "auth.roblox.com"],
        "domains": ["roblox.com", "rbxcdn.com", "rbx.com", "robloxlabs.com"],
        "asns": [_a(22697, "Roblox (production)"), _a(11281, "Roblox (corporate)")],
        "note": "Заблокирован РКН с 3 декабря 2025",
    },
    {
        "id": "photon", "name": "Игры на Photon: R.E.P.O., VRChat", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.photonengine.com", "ns.photonengine.io", "vrchat.com"],
        "domains": ["photonengine.io", "photonengine.com", "exitgames.com", "vrchat.com", "vrchat.cloud"],
        "asns": [],
        "note": "Сервера Photon за Cloudflare — только домены",
    },
    {
        "id": "faceit", "name": "FACEIT", "confidence": "medium", "default_route": "zapret",
        "probe": ["www.faceit.com", "api.faceit.com", "cdn.faceit.com"],
        "domains": ["faceit.com", "faceit-cdn.net"],
        "asns": [_a(59835, "EFG Sweden (DreamHack)")],
        "note": "Сайт и античит; часть за Cloudflare",
    },
    {
        "id": "acc", "name": "Assetto Corsa Competizione", "confidence": "low", "default_route": "zapret",
        "probe": ["www.kunos-simulazioni.com", "www.assettocorsa.net"],
        "domains": ["kunos-simulazioni.com", "assettocorsa.net", "assettocorsacompetizione.com"],
        "asns": [],
        "note": "Лобби-сервер не задокументирован, сервера у сообщества — только домены",
    },
]


def get(preset_id: str) -> dict | None:
    return next((p for p in PRESETS if p["id"] == preset_id), None)
