import { useEffect } from "react";
import { post } from "../../lib/api.js";
import { fmt, nets } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import UpdateCard from "./UpdateCard.jsx";
import JobConsole from "./JobConsole.jsx";
import { confirmText } from "./confirmText.jsx";
import "../../styles/updates.css";

export default function UpdatesPage() {
  const { status, split, updates, checkUpdates, job, watchJob, busy } = useStore();
  const confirm = useConfirm();
  useEffect(() => { if (!updates) checkUpdates(false).catch(() => {}); }, [updates, checkUpdates]);

  const run = async (target) => {
    let u = updates;
    if (!u) { await checkUpdates(true); return; }
    const d = u[target === "ipset" ? "zapret" : target] || {};
    if (!(await confirm(confirmText(target, d, status)))) return;
    location.hash = "updates";
    watchJob(await post(`/api/updates/${target}`, { confirm: true, version: target === "ipset" ? null : d.latest }));
  };

  return (
    <section className="tab">
      <div className="list-head">
        <h2>Обновления</h2>
        <Button onClick={() => checkUpdates(true)}>Проверить сейчас</Button>
      </div>
      {updates?.checked_at && (
        <p className="hint" style={{ marginTop: -8 }}>
          Проверено в {new Date(updates.checked_at * 1000).toLocaleTimeString("ru")}. Проверка только сравнивает номера версий — ничего не скачивается
        </p>
      )}
      <div className="grid2">
        <UpdateCard title="Запрет" repo="Flowseal/zapret-discord-youtube" d={updates?.zapret} action="Обновить запрет" disabled={busy} onRun={() => run("zapret")} />
        <UpdateCard title="zapret2" repo={updates?.zapret2?.repo || "zapret2"} d={updates?.zapret2} engine
          action={updates?.zapret2 && !updates.zapret2.installed ? "Установить zapret2" : "Обновить zapret2"} disabled={busy} onRun={() => run("zapret2")} />
        <UpdateCard title="TG WS Proxy" repo="Flowseal/tg-ws-proxy" d={updates?.tg} tg action="Обновить TG WS Proxy" disabled={busy} onRun={() => run("tg")} />
      </div>
      <div className="card">
        <div className="card-title">
          Списки
          {split?.base_size > 0 && <span className="sub"><span className="num">{fmt(split.base_size)}</span> {nets(split.base_size)} в базе Flowseal</span>}
        </div>
        <p className="hint">Базовый IPSet Flowseal, диапазоны стран из GeoIP-правил и подсети игр по ASN. Ваши правила накладываются поверх</p>
        <Button disabled={busy} onClick={() => run("ipset")}>Обновить списки</Button>
      </div>
      {job && <JobConsole job={job} />}
    </section>
  );
}
