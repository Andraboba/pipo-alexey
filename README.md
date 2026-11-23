<div align="center">

<img src="assets/logo.svg" width="96" height="96" alt="Пипо Алексей">

# Пипо Алексей

Пульт для обхода блокировок на Windows: служба запрета, сплит «напрямую / через обход», игры, подбор стратегии и Telegram-прокси в одном окне

</div>

> [!IMPORTANT]
> **Пипо Алексей — это не запрет и не его форк.** Это графическая оболочка, которая управляет уже установленными у вас
> [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) от Flowseal и
> [TG WS Proxy](https://github.com/Flowseal/tg-ws-proxy). Сам обход DPI делает `winws.exe` из проекта
> [zapret](https://github.com/bol-van/zapret) (bol-van). Программы этих авторов здесь не распространяются:
> приложение работает с вашей папкой запрета и скачивает обновления с их официальных страниц на GitHub.

![Пульт](docs/screenshots/panel.png)

## Что умеет

- **Пульт.** Запуск и остановка службы запрета, выбор стратегии (`general*.bat`), тумблер автозапуска (по умолчанию выключен), режим IPSet. Схема маршрутов показывает, сколько подсетей и доменов идёт через обход, а сколько напрямую.
- **Сплит.** Домен, ссылка, IP или подсеть — «напрямую» или «через запрет». Незаблокированным сайтам обход не нужен. GeoIP-правило отправляет целую страну напрямую; заблокированное из списков Flowseal из неё автоматически вычитается.
- **Игры.** Тумблер игрового фильтра (TCP + UDP / TCP / UDP) и профили игр: «через запрет», «напрямую» или «не трогать». Каталог из 19 игр с доменами и сетями серверов по ASN (подсети подтягиваются из RIPEstat): CS2/Dota 2, Valorant/LoL, Apex, Fortnite, PUBG, Battlefield, CoD, Overwatch, Tarkov, Roblox, iRacing и другие. Можно добавить свою игру.
- **Подбор стратегии.** По очереди запускает стратегии и проверяет выбранные цели: сайты (TLS 1.2 и 1.3), ваши IP и сети игр, заморозку 16–20 КБ (набор [hyperion-cs/dpi-checkers](https://github.com/hyperion-cs/dpi-checkers)). Сначала прогон без запрета — видно, что заблокировано и что именно чинит каждая стратегия. Лучшая применяется одной кнопкой.
- **Сервисы.** Нейросети и сервисы, которые сами закрыли доступ из России (ChatGPT, Gemini, Grok, Copilot и другие), через hosts и обратные прокси [GeoHide DNS](https://github.com/Internet-Helper/GeoHideDNS) или [dns.malw.link](https://github.com/ImMALWARE/dns.malw.link). Правила пишутся отдельным блоком, исходный hosts сохраняется, всё откатывается одной кнопкой.
- **Telegram.** Запуск TG WS Proxy, ссылка `tg://proxy` для Telegram Desktop, автозапуск.
- **Обновления.** Проверка версий запрета и TG WS Proxy. Новая версия скачивается только после подтверждения, сверяется по sha256, перед установкой делается бэкап; ваши списки и настройки сохраняются.

| Игры | Подбор стратегии | Сервисы |
| --- | --- | --- |
| ![Игры](docs/screenshots/games.png) | ![Подбор](docs/screenshots/scan.png) | ![Сервисы](docs/screenshots/services.png) |

## Установка

1. Установите [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube/releases) от Flowseal, например в `C:\Zapret` (другую папку можно указать в «Настройках»).
2. Скачайте `PipoAlexey.exe` со страницы [Releases](../../releases) и запустите. Windows попросит права администратора — без них нельзя управлять службой и писать списки.

Данные приложения (сплит, кеши, бэкапы, лог) лежат в папке `data` рядом с exe. Нужна Windows 10/11 с WebView2 (в Windows 11 он встроен).

Антивирусы иногда ложно реагируют на программы, собранные PyInstaller. Исходный код открыт — можно собрать exe самостоятельно.

## Важно знать

- Запрет меняет только то, как выглядит ваш трафик для DPI провайдера. Он не прячет IP и не шифрует данные.
- Раздел «Сервисы» направляет запросы к выбранным сервисам через чужие прокси-серверы. Их владельцы видят, к какому сервису и с какого IP вы обращаетесь (содержимое HTTPS — нет). Это обход ограничений самих сервисов: их правила такое запрещают, аккаунт могут заблокировать.
- **Claude и сервисы Anthropic не поддерживаются намеренно** — их домены отбрасываются при разборе любого списка.

## Сборка из исходников

Нужны Python 3.14 и Node.js.

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install fastapi uvicorn pywebview pyinstaller
build_exe.bat
```

Результат — `dist\PipoAlexey.exe`. Для разработки: `start.bat` запускает приложение из исходников; фронтенд (React + Vite) лежит в `frontend/`.

Тесты: `.venv\Scripts\python.exe -m unittest discover -s tests -t .`

## Благодарности

- [Flowseal](https://github.com/Flowseal) — [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) и [tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy)
- [bol-van](https://github.com/bol-van) — [zapret](https://github.com/bol-van/zapret)
- [hyperion-cs](https://github.com/hyperion-cs/dpi-checkers) — тест заморозки 16–20 КБ
- [GeoHide DNS](https://github.com/Internet-Helper/GeoHideDNS) и [dns.malw.link](https://github.com/ImMALWARE/dns.malw.link) — списки hosts
- [ipverse](https://github.com/ipverse/country-ip-blocks) — диапазоны стран, [RIPEstat](https://stat.ripe.net) — сети по ASN
- Идеи интерфейса подбора — [NetFix](https://github.com/rupleide/NetFix)

## Лицензия

[MIT](LICENSE). Лицензия относится к коду этого репозитория; запрет, TG WS Proxy и списки hosts распространяются их авторами на их собственных условиях.
