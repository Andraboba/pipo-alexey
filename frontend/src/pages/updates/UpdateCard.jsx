import { Button } from "../../ui/controls.jsx";

function message(d, tg) {
  if (!d) return "Проверяю…";
  if (d.error) return d.error;
  if (tg && !d.installed) return "Не установлен — кнопка ниже скачает его в папку запрета";
  if (d.newer) {
    const date = d.published ? " · " + new Date(d.published).toLocaleDateString("ru") : "";
    return `Вышла новая версия${date}. Установится только после вашего подтверждения`;
  }
  return "У вас последняя версия";
}

export default function UpdateCard({ title, repo, d, tg, action, disabled, onRun }) {
  return (
    <div className={"card upd" + (d?.newer ? " newer" : "")}>
      <div className="card-title">{title} <span className="sub">{repo}</span></div>
      <div className="versions">
        <div><span>Установлен</span><b>{d?.local || (tg && d && !d.installed ? "нет" : "—")}</b></div>
        <div><span>На GitHub</span><b className="latest">{d?.latest || "—"}</b></div>
      </div>
      <p className="upd-msg">{message(d, tg)}</p>
      <Button kind={d?.newer ? "solid" : ""} disabled={disabled} onClick={onRun}>{action}</Button>
    </div>
  );
}
