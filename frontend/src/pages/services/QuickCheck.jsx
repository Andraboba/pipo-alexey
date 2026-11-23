import { useState } from "react";
import { get } from "../../lib/api.js";
import { Button } from "../../ui/controls.jsx";

const DOMAINS = ["chatgpt.com", "gemini.google.com", "grok.com"];

export default function QuickCheck() {
  const [res, setRes] = useState({});
  const check = async (d) => {
    const r = await get("/api/hosts/check?domain=" + encodeURIComponent(d));
    setRes((x) => ({ ...x, [d]: r }));
  };
  return (
    <div className="card">
      <div className="card-title">Проверка</div>
      <p className="hint">Куда сейчас резолвится домен и отвечает ли он. После записи в hosts браузер нужно перезапустить</p>
      <div className="svc-checks">
        {DOMAINS.map((d) => (
          <div key={d} className="svc-check">
            <span className="mono">{d}</span>
            <span className={"sub" + (res[d] ? (res[d].ok ? " t-direct" : " t-bad") : "")}>
              {res[d] ? `${res[d].ip || "—"} · ${res[d].detail}` : ""}
            </span>
            <Button small onClick={() => check(d)}>Проверить</Button>
          </div>
        ))}
      </div>
    </div>
  );
}
