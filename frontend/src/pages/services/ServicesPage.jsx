import { useEffect, useState } from "react";
import { del, get, post, put } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button, Seg } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import SectionList from "./SectionList.jsx";
import QuickCheck from "./QuickCheck.jsx";
import "../../styles/services.css";

export default function ServicesPage() {
  const { status } = useStore();
  const toast = useToast();
  const confirm = useConfirm();
  const [data, setData] = useState(null);
  const [source, setSource] = useState("geohide");
  const [picked, setPicked] = useState(new Set());

  const sync = (d) => {
    setData(d);
    setSource(d.status.source || "geohide");
    setPicked(new Set(d.status.sections || []));
  };
  useEffect(() => { get("/api/hosts").then(sync).catch((e) => toast(e.message, true)); }, [toast]);

  if (!data) return <section className="tab"><div className="empty">Загрузка…</div></section>;
  const src = data.sources[source];
  const st = data.status;
  const empty = !src.sections.length;
  const dirty = source !== st.source || [...picked].sort().join("|") !== [...(st.sections || [])].sort().join("|");

  const refresh = async () => {
    const d = await post("/api/hosts/refresh");
    setData(d);
    d.errors?.length ? toast(d.errors.join("; "), true) : toast("Списки обновлены");
  };

  const apply = async (names = picked) => {
    const ok = await confirm({
      title: names.size ? `Записать ${names.size} сервис(ов) в hosts?` : "Убрать все правила из hosts?",
      ok: names.size ? "Записать" : "Убрать",
      body: names.size ? (
        <ul>
          <li>Запросы к этим сервисам пойдут через обратные прокси {src.name}: владелец прокси видит, к какому сервису и с какого IP вы ходите (содержимое HTTPS — нет).</li>
          <li>Это обход ограничений самих сервисов, а не РКН: их правила такое запрещают, аккаунт могут заблокировать.</li>
          <li>Ваши строки в hosts не трогаю; исходный файл сохранён в <code>data\backups\hosts.original</code>.</li>
        </ul>
      ) : "Блок Пипо Алексея будет удалён, остальное содержимое hosts останется.",
    });
    if (!ok) return;
    sync(names.size ? await put("/api/hosts", { source, sections: [...names] }) : await del("/api/hosts"));
    toast(names.size ? "Записано в hosts. Перезапустите браузер" : "Правила убраны из hosts");
  };

  return (
    <section className="tab">
      <div className="intro">
        <h2>Сервисы</h2>
        <p>
          ChatGPT, Gemini, Grok и другие сервисы сами закрыли доступ из России — запрет тут не поможет. Через hosts их
          домены направляются на обратные прокси из открытых списков. Claude и Anthropic не поддерживаются
        </p>
      </div>

      {st.reverted && (
        <div className="banner warn inline">
          Правил Пипо Алексея больше нет в hosts — скорее всего, их откатил Защитник Windows (он считает такие правки
          «захватом hosts»). Добавьте файл <code>{st.hosts_path}</code> в исключения Защитника и запишите правила заново
        </div>
      )}

      <div className="card svc-head">
        <div className="grow">
          <div className="card-title">Источник</div>
          <Seg options={Object.entries(data.sources).map(([v, s]) => ({ v, label: s.name }))} value={source}
            onChange={(v) => { setSource(v); setPicked(new Set()); }} />
          <p className="hint" style={{ marginBottom: 0 }}>
            {src.updated ? `Список от ${new Date(src.updated * 1000).toLocaleString("ru")}` : "Список ещё не загружен"} · {src.page.replace("https://", "")}
          </p>
        </div>
        <div className="svc-state">
          <span className="eyebrow">Сейчас в hosts</span>
          <b className="num">{st.in_hosts}</b>
          <span className="sub">{st.in_hosts ? `${st.sections.length} серв. · ${data.sources[st.source]?.name}` : "ничего"}</span>
        </div>
        <Button onClick={refresh}>{empty ? "Загрузить списки" : "Обновить списки"}</Button>
      </div>

      {!empty && <SectionList sections={src.sections} picked={picked} setPicked={setPicked} />}

      <div className="card scan-bar">
        <div className="grow">
          Выбрано <b className="num">{picked.size}</b> · {dirty ? "изменения не записаны" : "совпадает с hosts"}
        </div>
        {st.in_hosts > 0 && (
          <Button kind="ghost" disabled={!status.admin} onClick={() => apply(new Set())}>Убрать всё</Button>
        )}
        <Button kind="solid" disabled={!dirty || !status.admin || (empty && picked.size > 0)} onClick={() => apply()}>Записать в hosts</Button>
      </div>

      <QuickCheck />
    </section>
  );
}
