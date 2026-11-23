import { post } from "../lib/api.js";
import { useStore } from "../store.jsx";
import { Button } from "../ui/controls.jsx";
import { useToast } from "../ui/Toasts.jsx";

export default function Banners() {
  const { status, restartNeeded, setRestartNeeded, setZapret } = useStore();
  const toast = useToast();
  if (!status) return null;
  return (
    <>
      {!status.admin && (
        <div className="banner warn">
          <span>UI запущен без прав администратора — можно смотреть, но не управлять запретом. Запустите Пипо Алексея заново и разрешите запрос прав администратора</span>
        </div>
      )}
      {restartNeeded && (
        <div className="banner amber">
          <span>Списки обновлены, а запрет работает со старыми — перезапустите его, чтобы применить</span>
          <Button kind="solid" small onClick={async () => {
            setZapret(await post("/api/zapret/restart"));
            setRestartNeeded(false);
            toast("Запрет перезапущен");
          }}>Перезапустить запрет</Button>
          <button className="btn small ghost" onClick={() => setRestartNeeded(false)}>Позже</button>
        </div>
      )}
    </>
  );
}
