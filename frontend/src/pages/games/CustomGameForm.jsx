import { useState } from "react";
import { post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const EMPTY = { name: "", domains: "", asns: "", networks: "" };

export default function CustomGameForm() {
  const { setSplit } = useStore();
  const toast = useToast();
  const [f, setF] = useState(EMPTY);
  const [open, setOpen] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <details className="card" open={open} onToggle={(e) => setOpen(e.target.open)}>
      <summary>Своя игра</summary>
      <form className="stack" onSubmit={(e) => e.preventDefault()}>
        <div className="field"><label htmlFor="pf-name">Название</label>
          <input id="pf-name" value={f.name} onChange={set("name")} placeholder="Например, Le Mans Ultimate" />
        </div>
        <div className="grid2 tight">
          <div className="field"><label htmlFor="pf-domains">Домены, по одному в строке</label>
            <textarea id="pf-domains" className="mono" rows={4} spellCheck={false} value={f.domains} onChange={set("domains")} placeholder="example-game.com" />
          </div>
          <div className="field"><label htmlFor="pf-asns">ASN через пробел</label>
            <input id="pf-asns" className="mono" spellCheck={false} value={f.asns} onChange={set("asns")} placeholder="AS49544 AS199524" />
          </div>
        </div>
        <div className="field"><label htmlFor="pf-networks">Подсети, по одной в строке</label>
          <textarea id="pf-networks" className="mono" rows={5} spellCheck={false} value={f.networks} onChange={set("networks")} placeholder={"185.38.120.0/24\n2a05:d014::/32"} />
        </div>
        <Button kind="solid" type="submit" disabled={!f.name.trim()} onClick={async () => {
          setSplit(await post("/api/split/profiles", { ...f, route: "zapret" }));
          setF(EMPTY);
          setOpen(false);
          toast("Профиль создан");
        }}>Создать</Button>
      </form>
    </details>
  );
}
