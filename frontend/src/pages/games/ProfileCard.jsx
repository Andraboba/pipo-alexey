import { useState } from "react";
import { del, patch } from "../../lib/api.js";
import { domains, fmt, nets, ROUTE_LABEL } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Button, Seg, useAction } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const ROUTES = [
  { v: "off", label: "Не трогать" },
  { v: "direct", label: "Напрямую" },
  { v: "zapret", label: "Через запрет" },
];
const EXPLAIN = {
  off: "Запрет поступает с этими адресами так, как решат общие списки",
  direct: "Запрет гарантированно не трогает трафик к этим серверам",
  zapret: "Подсети в IPSet, домены в списке запрета. Для игровых портов нужен игровой фильтр",
};

export default function ProfileCard({ p }) {
  const { status, setSplit } = useStore();
  const act = useAction();
  const toast = useToast();
  const confirm = useConfirm();
  const [form, setForm] = useState(null); // null — свёрнуто

  const update = (body, msg) => act(async () => { setSplit(await patch(`/api/split/profiles/${p.id}`, body)); if (msg) toast(msg); });
  const gfOn = status.zapret.game_filter.mode !== "disabled";

  const openForm = () => setForm({
    domains: p.domains.join("\n"),
    asns: p.asns.map((a) => "AS" + a).join(" "),
    networks: p.networks.join("\n"),
  });

  const remove = async () => {
    const ok = await confirm({
      title: `Удалить профиль «${p.name}»?`,
      body: p.created_by_app ? "Файл со своими подсетями тоже будет удалён." : <>Профиль исчезнет из UI, файл <code>lists/{p.file}</code> останется.</>,
      ok: "Удалить", danger: true,
    });
    if (ok) act(async () => setSplit(await del(`/api/split/profiles/${p.id}`)));
  };

  return (
    <div className={"card profile " + p.route}>
      <div>
        <h3>{p.name}</h3>
        <div className="stat">
          <span className="num">{fmt(p.total)}</span> {nets(p.total)}
          {p.domains.length > 0 && <> · {p.domains.length} {domains(p.domains.length)}</>}
          {p.asns.length > 0 && <> · {p.asns.length} ASN</>}
        </div>
        {(p.domains.length > 0 || p.asns.length > 0) && (
          <div className="tags">
            {p.domains.map((d) => <span className="tag" key={d}>{d}</span>)}
            {p.asns.map((a) => (
              <span className="tag" key={a} title={`${p.asn_counts[a] ?? 0} префиксов`}>AS{a}{p.asn_counts[a] ? "" : " · не загружен"}</span>
            ))}
          </div>
        )}
      </div>
      <Seg options={ROUTES} value={p.route} onChange={(route) => update({ route }, `${p.name}: ${ROUTE_LABEL[route]}`)} />
      <p className="explain">
        {EXPLAIN[p.route]}
        {p.route === "off" && p.covered_by_base > 0 && (
          <> · <b className="t-zapret">{p.covered_by_base} из {p.total}</b> подсетей уже в общем IPSet{gfOn ? " и обрабатываются" : ""}</>
        )}
      </p>
      {form === null ? (
        <button className="link" style={{ alignSelf: "flex-start" }} onClick={openForm}>Изменить</button>
      ) : (
        <div className="stack tight">
          <div className="field"><label>Домены</label>
            <textarea className="mono" rows={3} spellCheck={false} value={form.domains} onChange={(e) => setForm({ ...form, domains: e.target.value })} />
          </div>
          <div className="field"><label>ASN</label>
            <input className="mono" spellCheck={false} value={form.asns} onChange={(e) => setForm({ ...form, asns: e.target.value })} />
          </div>
          <div className="field"><label>Свои подсети · <code>lists/{p.file}</code></label>
            <textarea className="mono" rows={6} spellCheck={false} value={form.networks} onChange={(e) => setForm({ ...form, networks: e.target.value })} />
          </div>
          <div className="row">
            <Button small kind="solid" onClick={async () => {
              setSplit(await patch(`/api/split/profiles/${p.id}`, form));
              setForm(null);
              toast("Профиль сохранён");
            }}>Сохранить</Button>
            <button className="btn small ghost" onClick={() => setForm(null)}>Отмена</button>
            <button className="btn small ghost danger-text" onClick={remove}>Удалить профиль</button>
          </div>
        </div>
      )}
    </div>
  );
}
