import { put } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Seg, useAction } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const MODES = [
  { v: "loaded", label: "По списку" },
  { v: "none", label: "Никакие" },
  { v: "any", label: "Все" },
];

export default function IpsetCard() {
  const { status, applyResp, loadSplit } = useStore();
  const act = useAction();
  const toast = useToast();
  const change = (mode) => act(async () => {
    applyResp(await put("/api/zapret/ipset-mode", { mode }));
    loadSplit();
    toast("Режим IPSet изменён");
  });
  return (
    <div className="card">
      <div className="card-title">Режим IPSet</div>
      <p className="hint">Какие IP-адреса запрет обрабатывает по списку <code>ipset-all.txt</code></p>
      <Seg options={MODES} value={status.zapret.ipset_mode} onChange={change} />
      <dl className="kv">
        <dt>По списку</dt><dd>база Flowseal и ваши «через запрет»</dd>
        <dt>Никакие</dt><dd>IP-обход выключен, работают только домены</dd>
        <dt>Все</dt><dd>любой IP кроме исключений — для отладки</dd>
      </dl>
    </div>
  );
}
