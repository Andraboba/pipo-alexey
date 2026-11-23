import { useState } from "react";
import { post } from "../../lib/api.js";
import { COUNTRIES } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Button, Seg } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import { ROUTES } from "./RuleForm.jsx";

export default function GeoForm() {
  const { setSplit } = useStore();
  const toast = useToast();
  const [cc, setCc] = useState("");
  const [route, setRoute] = useState("direct");

  const add = async () => {
    const code = cc.trim().toUpperCase();
    setSplit(await post("/api/split/rules", { value: code, route, kind: "geo" }));
    toast(`${COUNTRIES[code] || code}: ${route === "direct" ? "напрямую" : "через запрет"}`);
    setCc("");
  };

  return (
    <form className="card addrule" autoComplete="off" onSubmit={(e) => e.preventDefault()}>
      <div className="geo-label"><b>GeoIP</b><span className="sub">страна целиком</span></div>
      <input id="geo-cc" className="mono" list="countries" placeholder="RU" maxLength={2} value={cc}
        onChange={(e) => setCc(e.target.value.toUpperCase())} />
      <datalist id="countries">
        {Object.entries(COUNTRIES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
      </datalist>
      <Seg options={ROUTES} value={route} onChange={setRoute} />
      <span className="hint grow" style={{ margin: 0 }}>
        Заблокированное из списков Flowseal и ваши игры «через запрет» из страны вычитаются автоматически
      </span>
      <Button kind="solid" type="submit" disabled={cc.trim().length !== 2} onClick={add}>Добавить страну</Button>
    </form>
  );
}
