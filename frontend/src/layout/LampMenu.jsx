import { useEffect, useRef, useState } from "react";
import { post } from "../lib/api.js";
import { tgView, zapretView } from "../lib/status.js";
import { cssViewport } from "../lib/uiScale.js";
import { go, useStore } from "../store.jsx";
import { useToast } from "../ui/Toasts.jsx";

/** Быстрое меню лампы в верхней панели (ПКМ): включить/выключить, не уходя со своей вкладки. */
export default function LampMenu({ kind, anchor, onClose }) {
  const { status, setZapret, setTg, refreshStatus, setRestartNeeded } = useStore();
  const toast = useToast();
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // своя лампа — не «мимо»: повторный ПКМ по ней закрывает меню в TopBar, а не открывает заново
    const outside = (e) => {
      if (!ref.current?.contains(e.target) && !e.target.closest?.(`.lamp[data-kind="${kind}"]`)) onClose();
    };
    const key = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", onClose);
    ref.current?.querySelector("button:not(:disabled)")?.focus();
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose, kind]);

  const run = (fn, msg) => async () => {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      onClose();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setBusy(false);
    }
  };

  let title, view, items;
  if (kind === "zapret") {
    const z = status.zapret;
    view = zapretView(z);
    const installed = z.service !== null;
    const running = z.service === "running";
    const zrun = (path) => async () => {
      setZapret(await post(path));
      if (!path.endsWith("stop")) setRestartNeeded(false);
    };
    title = "Запрет";
    items = [
      { label: "Запустить", disabled: !installed || running, fn: zrun("/api/zapret/start"), msg: "Запрет запущен" },
      { label: "Остановить", disabled: !running && !z.winws_running, fn: zrun("/api/zapret/stop"), msg: "Запрет остановлен" },
      { label: "Перезапустить", disabled: !running, fn: zrun("/api/zapret/restart"), msg: "Запрет перезапущен" },
    ];
    if (!installed) items.hint = "Служба не установлена — выберите стратегию на «Пульте»";
  } else {
    const tg = status.tg;
    view = tgView(tg);
    title = "Прокси Telegram";
    items = [
      { label: "Запустить", disabled: !tg.installed || tg.running, msg: "Прокси Telegram запущен",
        fn: async () => { setTg(await post("/api/tg/start")); setTimeout(refreshStatus, 1500); } },
      { label: "Остановить", disabled: !tg.running, msg: "Прокси Telegram остановлен",
        fn: async () => setTg(await post("/api/tg/stop")) },
    ];
    if (!tg.installed) items.hint = "Прокси не установлен — его можно поставить во вкладке «Обновления»";
  }
  const to = kind === "zapret" ? "panel" : "telegram";

  return (
    <div ref={ref} className="lamp-menu" role="menu" aria-label={title}
      style={{ top: anchor.bottom + 6, right: Math.max(8, cssViewport().width - anchor.right) }}>
      <div className="lamp-menu-head">
        <i className={view.lamp ? "on-" + view.lamp : ""} />
        <div>
          <b>{title}</b>
          <span>{view.label}</span>
        </div>
      </div>
      {items.map((it) => (
        <button key={it.label} type="button" role="menuitem" disabled={busy || it.disabled} onClick={run(it.fn, it.msg)}>
          {it.label}
        </button>
      ))}
      {items.hint && <p className="lamp-menu-hint">{items.hint}</p>}
      <div className="lamp-menu-sep" />
      <button type="button" role="menuitem" onClick={() => { go(to); onClose(); }}>
        Открыть вкладку «{kind === "zapret" ? "Пульт" : "Прокси Telegram"}»
      </button>
    </div>
  );
}
