import { useState } from "react";
import { post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const GRADE = { ideal: "Идеальная", partial: "Частично", broken: "Не работает", failed: "Не запустилась" };

function cellClass(r) {
  if (!r) return "cell";
  return "cell " + (r.score >= 1 ? "ok" : r.score > 0 ? "half" : "bad");
}

/** Полоса клеток: одна клетка — одна цель. Подсказка — что именно произошло. */
function Cells({ targets, results }) {
  return (
    <div className="cells">
      {targets.map((t) => {
        const r = results?.[t.id];
        return <i key={t.id} className={cellClass(r)} title={`${t.name}: ${r ? r.detail : "ещё не проверено"}`} />;
      })}
    </div>
  );
}

export default function ScanResults({ result, running, job, current, onApplied }) {
  const { status, setZapret, setRestartNeeded } = useStore();
  const confirm = useConfirm();
  const toast = useToast();
  const [open, setOpen] = useState(null);
  const n = result.targets.length;
  const baselineOk = Object.values(result.baseline || {}).filter((r) => r.score >= 1).length;

  const rows = [...result.rows].sort((a, b) =>
    running ? 0 : (b.state === "done") - (a.state === "done") || b.score - a.score || (a.avg_ms ?? 1e9) - (b.avg_ms ?? 1e9));

  const apply = async (strategy) => {
    const installed = status.zapret.service !== null;
    const ok = await confirm({
      title: `Применить «${strategy}»?`,
      ok: "Применить",
      body: installed
        ? "Служба переключится на эту стратегию. Если запрет работает — перезапустите его после этого."
        : <>Служба будет создана со стратегией <b>{strategy}</b> без автозапуска и не запустится сама.</>,
    });
    if (!ok) return;
    const z = await post("/api/zapret/install", { strategy, start: false });
    setZapret(z);
    if (z.service === "running") setRestartNeeded(true);
    toast("Стратегия применена: " + strategy);
    onApplied?.();
  };

  return (
    <div className="card scan-results">
      <div className="list-head">
        <div className="card-title">
          Результаты
          {result.finished_at && !running && <span className="sub">от {new Date(result.finished_at * 1000).toLocaleString("ru")}</span>}
        </div>
        {running && job && (
          <div className="progress"><i style={{ width: Math.round((job.progress || 0) * 100) + "%" }} /></div>
        )}
      </div>

      <div className="srow baseline">
        <div className="sname">Без запрета<span className="sub">проходит {baselineOk} из {n}</span></div>
        <Cells targets={result.targets} results={result.baseline} />
        <div className="sscore" />
        <div className="sact" />
      </div>

      {rows.map((r) => (
        <div key={r.strategy}>
          <div className={"srow " + (r.grade || r.state) + (r.strategy === result.best && !running ? " best" : "")}>
            <button className="sname link-row" onClick={() => setOpen(open === r.strategy ? null : r.strategy)}>
              {r.strategy}
              <span className="sub">
                {r.state === "running" ? "проверяю…" : r.state === "pending" ? "в очереди" : GRADE[r.grade] || ""}
                {r.strategy === current ? " · сейчас в службе" : ""}
              </span>
            </button>
            <Cells targets={result.targets} results={r.results} />
            <div className="sscore">
              {r.state === "done" && <><span className="num">{r.score}</span> / {n}<span className="sub">{r.avg_ms} мс</span></>}
            </div>
            <div className="sact">
              {r.state === "done" && r.score > 0 && !running && (
                <Button small kind={r.strategy === result.best ? "solid" : ""} disabled={!status.admin} onClick={() => apply(r.strategy)}>
                  Применить
                </Button>
              )}
            </div>
          </div>
          {open === r.strategy && (
            <div className="sdetail">
              {r.error && <div className="t-bad">{r.error}</div>}
              {result.targets.map((t) => {
                const x = r.results?.[t.id];
                const b = result.baseline?.[t.id];
                return (
                  <div key={t.id} className="drow">
                    <i className={cellClass(x)} />
                    <span className="dname">{t.name}</span>
                    <span className="ddetail">{x ? x.detail : "—"}</span>
                    {b && b.score < 1 && x?.score >= 1 && <span className="fixed">починила</span>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
