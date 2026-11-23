import { useState } from "react";
import { post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import CellTip from "./CellTip.jsx";
import { cellState } from "./cellState.js";
import { humanDetail } from "./humanDetail.js";

const GRADE = { ideal: "Идеальная", partial: "Частично", broken: "Не работает", failed: "Не запустилась" };

function groupsOf(targets) {
  const groups = [];
  for (const t of targets) {
    const g = groups.at(-1);
    g && g.name === t.group ? g.items.push(t) : groups.push({ name: t.group, items: [t] });
  }
  return groups;
}

/** Полоса клеток, разбитая по группам целей. */
function Cells({ groups, results, meta, onHover }) {
  return (
    <div className="cells">
      {groups.map((g) => (
        <span className="cgroup" key={g.name}>
          {g.items.map((t) => (
            <i key={t.id} className={"cell " + cellState(results?.[t.id], meta?.[t.id])}
              onMouseEnter={(e) => onHover({ t, el: e.currentTarget, r: results?.[t.id] })}
              onMouseLeave={() => onHover(null)} />
          ))}
        </span>
      ))}
    </div>
  );
}

function Legend() {
  return (
    <div className="legend">
      <span><i className="cell ok" /> проходит</span>
      <span><i className="cell half" /> частично</span>
      <span><i className="cell bad" /> не проходит</span>
      <span><i className="cell dead" /> не отвечает нигде — не учитывается</span>
      <span className="sub">Наведите на клетку, чтобы увидеть адрес</span>
    </div>
  );
}

export default function ScanResults({ result, running, job, current, onApplied }) {
  const { status, setZapret, setRestartNeeded, setSplit } = useStore();
  const confirm = useConfirm();
  const toast = useToast();
  const [open, setOpen] = useState(null);
  const [tip, setTip] = useState(null);
  const groups = groupsOf(result.targets);
  const meta = result.meta || {};
  const n = result.counted ?? result.targets.length;
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

  // открытый без запрета сайт, который стратегия ломает, проще всего пустить мимо запрета
  const direct = async (t) => {
    const host = new URL(t.url).hostname;
    setSplit(await post("/api/split/rules", { value: host, route: "direct", note: "ломает стратегия" }));
    toast(`${host} теперь идёт напрямую — перезапустите запрет`);
  };

  const hover = (rowResults) => (h) => setTip(h && { ...h, row: rowResults, base: result.baseline?.[h.t.id], meta: meta[h.t.id] });

  return (
    <div className="card scan-results">
      <div className="list-head">
        <div className="card-title">
          Результаты
          {result.finished_at && !running && <span className="sub">от {new Date(result.finished_at * 1000).toLocaleString("ru")}</span>}
        </div>
        {running && job && <div className="progress"><i style={{ width: Math.round((job.progress || 0) * 100) + "%" }} /></div>}
      </div>
      <Legend />
      {result.meta && !running && (
        <p className="hint">
          Заблокировано без запрета: <b className="num">{result.blocked}</b> из {result.targets.length}.
          {result.targets.length - n > 0 && <> Не отвечают нигде и не учитываются: <b className="num">{result.targets.length - n}</b>.</>}
        </p>
      )}

      <div className="srow ghead">
        <div />
        <div className="cells">
          {groups.map((g) => (
            <span className="cgroup glabel" key={g.name} style={{ width: g.items.length * 14 - 2 }} title={g.name}>
              {g.name.replace(/^Игра:\s*/, "")}
            </span>
          ))}
        </div>
        <div /><div />
      </div>

      <div className="srow baseline">
        <div className="sname">Без запрета<span className="sub">проходит {baselineOk} из {result.targets.length}</span></div>
        <Cells groups={groups} results={result.baseline} meta={meta} onHover={hover(result.baseline)} />
        <div className="sscore" />
        <div className="sact" />
      </div>

      {rows.map((r) => (
        <div key={r.strategy}>
          <div className={"srow " + (r.grade || r.state) + (r.strategy === result.best && !running ? " best" : "")}>
            <button className="sname link-row" onClick={() => setOpen(open === r.strategy ? null : r.strategy)}>
              {r.strategy}
              <span className="sub">
                {r.state === "running" ? "проверяю…" : r.state === "pending" ? "в очереди" : r.state === "skipped" ? "пропущена" : GRADE[r.grade] || ""}
                {r.fixed > 0 && ` · чинит ${r.fixed} из ${result.blocked}`}
                {r.broke > 0 && ` · ломает ${r.broke}`}
                {r.strategy === current ? " · сейчас в службе" : ""}
              </span>
            </button>
            <Cells groups={groups} results={r.results} meta={meta} onHover={hover(r.results)} />
            <div className="sscore">
              {r.state === "done" && <><span><span className="num">{r.score}</span> / {r.of ?? n}</span><span className="sub">{r.avg_ms} мс</span></>}
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
                const st = meta[t.id]?.status;
                return (
                  <div key={t.id} className="drow">
                    <i className={"cell " + cellState(x, meta[t.id])} />
                    <span className="dname" title={t.about}>{t.name}</span>
                    <span className="ddetail" title={x ? humanDetail(x.detail) : undefined}>{x ? humanDetail(x.detail) : "—"}</span>
                    {st === "blocked" && cellState(x, meta[t.id]) === "ok" && <span className="fixed">починила</span>}
                    {st === "dead" && <span className="sub">не отвечает нигде</span>}
                    {st === "open" && x && t.kind === "url" && cellState(x, meta[t.id]) !== "ok" && (
                      <span className="row" style={{ gap: 8 }}>
                        <span className="t-bad">сломала</span>
                        <Button small plain kind="link" disabled={!status.admin} onClick={() => direct(t)}>Пустить напрямую</Button>
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
      {tip && <CellTip tip={tip} />}
    </div>
  );
}
