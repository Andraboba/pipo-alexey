import { useEffect, useState } from "react";
import { get, put } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

export default function SettingsPage() {
  const { refreshStatus } = useStore();
  const toast = useToast();
  const [zdir, setZdir] = useState("");
  const [tgExe, setTgExe] = useState("");

  useEffect(() => {
    get("/api/settings").then((s) => { setZdir(s.zapret_dir || ""); setTgExe(s.tg_exe || ""); }).catch((e) => toast(e.message, true));
  }, [toast]);

  return (
    <section className="tab">
      <h2>Настройки</h2>
      <form className="card stack" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor="s-zdir">Папка запрета</label>
          <input id="s-zdir" className="mono" spellCheck={false} value={zdir} onChange={(e) => setZdir(e.target.value)} />
          <p className="hint">Здесь должны лежать <code>service.bat</code>, <code>bin\winws.exe</code> и <code>lists\</code></p>
        </div>
        <div className="field">
          <label htmlFor="s-tg">Путь к TgWsProxy.exe</label>
          <input id="s-tg" className="mono" spellCheck={false} value={tgExe} onChange={(e) => setTgExe(e.target.value)} placeholder="Пусто — искать рядом с запретом" />
        </div>
        <Button kind="solid" type="submit" onClick={async () => {
          await put("/api/settings", { zapret_dir: zdir.trim(), tg_exe: tgExe.trim() || null });
          toast("Сохранено");
          refreshStatus();
        }}>Сохранить</Button>
      </form>
    </section>
  );
}
