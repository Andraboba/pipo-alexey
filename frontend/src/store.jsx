import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { get } from "./lib/api.js";
import { useToast } from "./ui/Toasts.jsx";

const StoreCtx = createContext(null);
export const useStore = () => useContext(StoreCtx);

export const JOB_TITLE = {
  zapret: "Обновление запрета",
  tg: "Обновление TG WS Proxy",
  ipset: "Обновление списков",
  asn: "Обновление подсетей игр",
  scan: "Подбор стратегии",
};

/** Всё состояние UI: статус служб, сплит, обновления, текущая фоновая задача. */
export function StoreProvider({ children }) {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [offline, setOffline] = useState(false);
  const [split, setSplitRaw] = useState(null);
  const [updates, setUpdates] = useState(null);
  const [presets, setPresets] = useState([]);
  const [job, setJob] = useState(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const watching = useRef(null);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await get("/api/status"));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  const setZapret = useCallback((z) => setStatus((s) => ({ ...s, zapret: z })), []);
  const setTg = useCallback((tg) => setStatus((s) => ({ ...s, tg })), []);

  const loadPresets = useCallback(async () => {
    try { setPresets(await get("/api/presets")); } catch { /* каталог не критичен */ }
  }, []);

  /** Ответы сплит-API: снимок + флаг «запрет работает, нужен перезапуск». */
  const setSplit = useCallback((sp) => {
    setSplitRaw(sp);
    if (sp?.restart_needed) setRestartNeeded(true);
    loadPresets();
  }, [loadPresets]);

  const loadSplit = useCallback(async () => {
    try { setSplit(await get("/api/split")); } catch (e) { toast(e.message, true); }
  }, [setSplit, toast]);

  const checkUpdates = useCallback(async (force = false) => {
    setUpdates(await get("/api/updates" + (force ? "?force=1" : "")));
  }, []);

  const watchJob = useCallback(async (j) => {
    if (watching.current === j.id) return;
    watching.current = j.id;
    setJob(j);
    while (j.state === "running") {
      await new Promise((r) => setTimeout(r, 700));
      try { j = await get(`/api/jobs/${j.id}`); } catch { continue; }
      setJob(j);
    }
    watching.current = null;
    if (j.state === "done") {
      toast(JOB_TITLE[j.kind] + ": готово");
      checkUpdates(true).catch(() => {});
      loadSplit();
    } else {
      toast(JOB_TITLE[j.kind] + ": ошибка — " + (j.log.at(-2)?.text || "подробности в журнале"), true);
    }
    refreshStatus();
  }, [toast, checkUpdates, loadSplit, refreshStatus]);

  // старт: статус, сплит, проверка версий (только сравнение номеров, ничего не скачивается)
  useEffect(() => {
    refreshStatus();
    loadSplit();
    checkUpdates(false).catch(() => {});
    const t = setInterval(() => { if (!document.hidden && !watching.current) refreshStatus(); }, 5000);
    return () => clearInterval(t);
  }, [refreshStatus, loadSplit, checkUpdates]);

  // задача, начатая в другой вкладке браузера, тоже подхватывается
  useEffect(() => { if (status?.job && !watching.current) watchJob(status.job); }, [status?.job, watchJob]);

  // запрет остановлен — баннер «перезапустите» не нужен
  const running = status?.zapret?.service === "running" || status?.zapret?.winws_running;
  useEffect(() => { if (status && !running) setRestartNeeded(false); }, [status, running]);

  const value = {
    status, offline, refreshStatus, setZapret, setTg,
    split, setSplit, loadSplit,
    updates, checkUpdates,
    presets, loadPresets,
    job, watchJob,
    restartNeeded, setRestartNeeded,
    /** для ответов вида { status, restart_needed } */
    applyResp: (r) => { if (r.status) setZapret(r.status); if (r.restart_needed) setRestartNeeded(true); },
  };
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}

export function useHashTab(tabs, fallback) {
  const read = () => {
    const h = location.hash.slice(1);
    return tabs.includes(h) ? h : fallback;
  };
  const [tab, setTab] = useState(read);
  useEffect(() => {
    const on = () => setTab(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  });
  return tab;
}

export const go = (tab) => { location.hash = tab; };
