import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { go } from "../store.jsx";
import { cssRect, cssViewport } from "../lib/uiScale.js";
import { IN_TRAY_SHELL } from "../lib/shell.js";
import "../styles/tour.css";

// Гайд для первого запуска: проходит по вкладкам, подсвечивает пункт меню и главное на странице.
// Пройденный гайд помечается в localStorage; повторить — кнопкой в «Настройках».
const DONE_KEY = "tourDone";
const nav = (tab) => `.nav a[href="#${tab}"]`;

const STEPS = [
  {
    title: "Привет, это Пипо Алексей",
    text: "Он включает обход блокировок (zapret), поднимает прокси для Telegram и решает, какой трафик пускать через обход, а какой напрямую. Покажу за минуту, где что лежит.",
  },
  {
    tab: "panel", targets: ['[data-tour="engine"]'],
    title: "Пульт: служба запрета",
    text: "Лампа показывает, работает ли обход. Выберите стратегию, нажмите «Установить службу», потом «Запустить». Движков два — если с одним сайты не открываются, переключитесь на другой.",
  },
  {
    tab: "panel", targets: ['[data-tour="routes"]'],
    title: "Маршруты",
    text: "Что идёт через запрет (жёлтым) и что напрямую (бирюзовым). Правила для своих сайтов и игр добавляются во вкладках «Сплит» и «Игры».",
  },
  {
    targets: ['[data-tour="lamps"]'],
    title: "Лампы вверху",
    text: "Состояние запрета и прокси Telegram видно с любой вкладки. Клик открывает нужную вкладку, а правая кнопка — меню, где их можно сразу включить или выключить.",
  },
  {
    tab: "scan", targets: [nav("scan"), "main .intro"],
    title: "Подбор стратегии",
    text: "Не знаете, какую стратегию выбрать, или сайт не открывается — запустите подбор. Он проверит все стратегии на нужных сайтах и покажет, какие работают.",
  },
  {
    tab: "telegram", targets: [nav("telegram"), '[data-tour="tg"]'],
    title: "Прокси Telegram",
    text: "Запустите прокси и нажмите «Открыть в Telegram» — Telegram Desktop сам добавит его в настройки. Автозапуск включит прокси при входе в Windows.",
  },
  {
    tab: "services", targets: [nav("services"), "main .intro"],
    title: "Сервисы",
    text: "ChatGPT, Gemini и другие сами закрыли доступ из России — тут запрет не поможет. Эта вкладка направляет их через обратные прокси с помощью файла hosts.",
  },
  {
    tab: "games", targets: [nav("games"), "main .intro"],
    title: "Игры",
    text: "Заблокированную игру — через запрет, незаблокированную — напрямую, чтобы обход не трогал её пинг. Готовые профили есть в каталоге ниже.",
  },
  {
    tab: "split", targets: [nav("split"), "main .intro"],
    title: "Сплит",
    text: "Свои правила для сайтов и стран: что пускать через запрет, а что напрямую. Домен охватывает все поддомены.",
  },
  {
    tab: "diag", targets: [nav("diag"), "main .intro"],
    title: "Диагностика",
    text: "Проверяет, не подменяет ли провайдер DNS, и находит шифрованный DNS, который у вас работает. В системе ничего не меняет.",
  },
  {
    tab: "evolve", targets: [nav("evolve"), "main .intro"],
    title: "Эволюция",
    text: "Сам ищет новую стратегию под вашего провайдера: скрещивает и мутирует лучшие. Долго — удобно запустить на ночь.",
  },
  {
    tab: "updates", targets: [nav("updates"), "main .list-head"],
    title: "Обновления",
    text: "Новые версии запрета, zapret2, прокси Telegram и списков блокировок. Когда что-то вышло, на пункте меню появится точка.",
  },
  IN_TRAY_SHELL && {
    title: "Значок в трее",
    text: "Крестик не закрывает Пипо Алексея, а прячет его в трей — к часам. Правая кнопка по значку включает и выключает запрет и прокси Telegram, «Выход» там же закрывает программу совсем.",
  },
  {
    tab: "settings", targets: [nav("settings"), '[data-tour="tour"]'],
    title: "Готово",
    text: "Здесь можно поменять масштаб интерфейса и пройти этот гайд ещё раз. Начать стоит с «Пульта»: выбрать стратегию и запустить запрет.",
  },
].filter(Boolean);

const listeners = new Set();
let open = false;
const setOpen = (v) => { open = v; listeners.forEach((l) => l()); };
const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };

export const startTour = () => setOpen(true);
export const tourSeen = () => localStorage.getItem(DONE_KEY) === "1";
export const useTourOpen = () => useSyncExternalStore(subscribe, () => open);

const PAD = 6;
const CARD_W = 360;
const GAP = 14;

function rectsOf(selectors) {
  return selectors.map((s) => document.querySelector(s)).filter(Boolean).map((el) => {
    const r = cssRect(el);
    return { x: r.left - PAD, y: r.top - PAD, w: r.width + PAD * 2, h: r.height + PAD * 2 };
  });
}

const same = (a, b) => a.length === b.length && a.every((r, i) =>
  Math.abs(r.x - b[i].x) < .5 && Math.abs(r.y - b[i].y) < .5 && Math.abs(r.w - b[i].w) < .5 && Math.abs(r.h - b[i].h) < .5);

/** Карточка рядом с главной (последней) подсветкой: снизу, сверху, справа — где поместится. */
function placeCard(target, card, vp) {
  if (!target) return { left: (vp.width - card.w) / 2, top: (vp.height - card.h) / 2 };
  const clampX = (x) => Math.min(Math.max(16, x), vp.width - card.w - 16);
  const clampY = (y) => Math.min(Math.max(16, y), vp.height - card.h - 16);
  if (target.y + target.h + GAP + card.h <= vp.height - 16) return { left: clampX(target.x), top: target.y + target.h + GAP };
  if (target.y - GAP - card.h >= 16) return { left: clampX(target.x), top: target.y - GAP - card.h };
  if (target.x + target.w + GAP + card.w <= vp.width - 16) return { left: target.x + target.w + GAP, top: clampY(target.y) };
  return { left: clampX(target.x), top: clampY(vp.height - card.h - 16) };
}

export default function Tour() {
  const isOpen = useTourOpen();
  const [i, setI] = useState(0);
  const [rects, setRects] = useState([]);
  const [vp, setVp] = useState(cssViewport);
  const [cardSize, setCardSize] = useState({ w: CARD_W, h: 200 });
  const cardRef = useRef(null);
  const step = STEPS[i];

  const finish = useCallback(() => {
    localStorage.setItem(DONE_KEY, "1");
    setOpen(false);
    setI(0);
    go("panel");
  }, []);

  // переход на вкладку шага и прокрутка к главному элементу (ждём, пока страница дорисуется)
  useEffect(() => {
    if (!isOpen) return;
    if (step.tab) go(step.tab);
    if (!step.targets) return;
    let tries = 0;
    const t = setInterval(() => {
      const el = document.querySelector(step.targets.at(-1));
      if (el || ++tries > 30) {
        clearInterval(t);
        el?.scrollIntoView({ block: "nearest" });
      }
    }, 50);
    return () => clearInterval(t);
  }, [isOpen, step]);

  // подсветка следует за элементами: страница грузит данные, окно меняет размер
  useEffect(() => {
    if (!isOpen) return;
    let raf;
    const tick = () => {
      const next = step.targets ? rectsOf(step.targets) : [];
      setRects((prev) => (same(prev, next) ? prev : next));
      const v = cssViewport();
      setVp((p) => (p.width === v.width && p.height === v.height ? p : v));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [isOpen, step]);

  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const w = el.offsetWidth, h = el.offsetHeight;
    setCardSize((s) => (s.w === w && s.h === h ? s : { w, h }));
  });

  useEffect(() => {
    if (!isOpen) return;
    const key = (e) => {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); i < STEPS.length - 1 ? setI(i + 1) : finish(); }
      else if (e.key === "ArrowLeft" && i > 0) setI(i - 1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [isOpen, i, finish]);

  useEffect(() => { cardRef.current?.focus(); }, [isOpen, i]);

  if (!isOpen) return null;
  const last = i === STEPS.length - 1;
  const pos = placeCard(step.targets ? rects.at(-1) : null, cardSize, vp);

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <svg className="tour-dim" width={vp.width} height={vp.height} aria-hidden="true">
        <defs>
          <mask id="tour-holes">
            <rect width="100%" height="100%" fill="white" />
            {rects.map((r, k) => <rect key={k} x={r.x} y={r.y} width={r.w} height={r.h} rx="12" fill="black" />)}
          </mask>
        </defs>
        <rect width="100%" height="100%" mask="url(#tour-holes)" />
        {rects.map((r, k) => <rect key={k} className="tour-ring" x={r.x} y={r.y} width={r.w} height={r.h} rx="12" />)}
      </svg>
      <div ref={cardRef} className="tour-card" tabIndex={-1} style={{ left: pos.left, top: pos.top }}>
        <div className="tour-step">{i + 1} из {STEPS.length}</div>
        <h3 id="tour-title">{step.title}</h3>
        <p>{step.text}</p>
        <div className="tour-dots" aria-hidden="true">
          {STEPS.map((_, k) => <i key={k} className={k === i ? "on" : k < i ? "past" : ""} />)}
        </div>
        <div className="row">
          {!last && <button type="button" className="btn ghost small" onClick={finish}>Пропустить</button>}
          <span className="grow" />
          {i > 0 && <button type="button" className="btn small" onClick={() => setI(i - 1)}>Назад</button>}
          <button type="button" className="btn solid small" onClick={() => (last ? finish() : setI(i + 1))}>
            {last ? "Начать" : i === 0 ? "Показать" : "Дальше"}
          </button>
        </div>
      </div>
    </div>
  );
}
