import { useEffect, useState } from "react";
import { get, put } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button, Seg } from "../../ui/controls.jsx";
import { SCALE_OPTIONS, useUiScale } from "../../lib/uiScale.js";
import { THEME_OPTIONS, useTheme } from "../../lib/theme.js";
import { startTour } from "../../ui/Tour.jsx";
import { useToast } from "../../ui/Toasts.jsx";

export default function SettingsPage() {
  const { refreshStatus, status } = useStore();
  const toast = useToast();
  const [zdir, setZdir] = useState("");
  const [tgExe, setTgExe] = useState("");
  const [z2dir, setZ2dir] = useState("");
  const [scalePref, , setScale] = useUiScale();
  const [themePref, theme, setTheme] = useTheme();

  useEffect(() => {
    get("/api/settings").then((s) => { setZdir(s.zapret_dir || ""); setZ2dir(s.zapret2_dir || ""); setTgExe(s.tg_exe || ""); }).catch((e) => toast(e.message, true));
  }, [toast]);

  return (
    <section className="tab">
      <h2>Настройки</h2>
      <form className="card stack" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor="s-zdir">Папка запрета (Flowseal)</label>
          <input id="s-zdir" className="mono" spellCheck={false} value={zdir} onChange={(e) => setZdir(e.target.value)} />
          <p className="hint">Здесь должны лежать <code>service.bat</code>, <code>bin\winws.exe</code> и <code>lists\</code></p>
        </div>
        <div className="field">
          <label htmlFor="s-z2dir">Папка zapret2</label>
          <input id="s-z2dir" className="mono" spellCheck={false} value={z2dir} onChange={(e) => setZ2dir(e.target.value)} />
          <p className="hint">Второй движок: сборка kinlay0 с <code>bin\winws2.exe</code>, <code>lua\</code> и <code>lists\</code>. Если её ещё нет — установите во вкладке «Обновления», папка создастся сама</p>
        </div>
        <div className="field">
          <label htmlFor="s-tg">Путь к TgWsProxy.exe</label>
          <input id="s-tg" className="mono" spellCheck={false} value={tgExe} onChange={(e) => setTgExe(e.target.value)} placeholder="Пусто — искать рядом с запретом" />
        </div>
        <Button kind="solid" type="submit" onClick={async () => {
          await put("/api/settings", { zapret_dir: zdir.trim(), zapret2_dir: z2dir.trim(), tg_exe: tgExe.trim() || null });
          toast("Сохранено");
          refreshStatus();
        }}>Сохранить</Button>
      </form>
      <div className="card stack" data-tour="tour">
        <div className="field">
          <div className="field-label">Тема</div>
          <Seg value={themePref} onChange={setTheme} options={THEME_OPTIONS} />
          <p className="hint" style={{ marginBottom: 0 }}>
            {themePref === "system" ? `Как в Windows — сейчас ${theme === "light" ? "светлая" : "тёмная"}` : "Не зависит от темы Windows"}
          </p>
        </div>
        <div className="field">
          <div className="field-label">Масштаб интерфейса</div>
          <Seg value={scalePref} onChange={setScale} options={SCALE_OPTIONS} />
          <p className="hint" style={{ marginBottom: 0 }}>
            Если текст кажется мелким или крупным на вашем мониторе. Системный масштаб Windows уже учтён
          </p>
        </div>
        <div className="field">
          <div className="field-label">Гайд</div>
          <div className="row">
            <Button onClick={startTour}>Пройти гайд ещё раз</Button>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-title">О программе</div>
        <dl className="kv">
          <dt>Версия</dt><dd className="mono">Пипо Алексей {status?.version || "?"}</dd>
        </dl>
      </div>
    </section>
  );
}
