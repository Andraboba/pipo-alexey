import { useEffect, useState } from "react";
import { get, post } from "../../lib/api.js";
import { plural } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import "../../styles/diag.css";

const VERDICT = {
  ok: ["верно", ""],
  other: ["другой адрес", "muted"],
  stub: ["заглушка", "bad"],
  nxdomain: ["«нет такого»", "bad"],
  empty: ["пустой ответ", "bad"],
  junk: ["ложный адрес", "bad"],
  fakeip: ["FakeIP вашего VPN", "muted"],
  timeout: ["нет ответа", "muted"],
  refused: ["отказ", "muted"],
  unknown: ["не с чем сравнить", "muted"],
};

const SUMMARY = {
  system: {
    cls: "warn",
    title: "Провайдер подменяет ваш DNS",
    text: "Windows получает неправильные адреса заблокированных сайтов. Запрет тут не поможет: браузер идёт не туда ещё до него. Включите DNS-over-HTTPS — список рабочих серверов ниже.",
  },
  udp: {
    cls: "amber",
    title: "Ваш DNS честный, но обычные DNS-запросы портят по дороге",
    text: "Сейчас всё в порядке, но если вы впишете в настройки сети 8.8.8.8 или 1.1.1.1 без шифрования, ответы могут подменяться. Надёжнее DNS-over-HTTPS.",
  },
  offline: {
    cls: "warn",
    title: "Не ответил ни один DNS-сервер",
    text: "Похоже, сейчас нет интернета — проверить подмену не с чем. Проверьте подключение и запустите ещё раз.",
  },
  fakeip: {
    cls: "amber",
    title: "Включён VPN-клиент с FakeIP",
    text: "Windows получает адреса 198.18.x.x от вашего VPN (sing-box, Clash и т. п.), а не от провайдера, — подмену провайдером так не проверить. Выключите VPN и проверьте ещё раз.",
  },
  clean: {
    cls: "",
    title: "DNS не подменяется",
    text: "Адреса заблокированных сайтов приходят настоящие. Если сайт не открывается — дело в DPI: тогда поможет запрет и «Подбор».",
  },
};

function Verdict({ v }) {
  const [label, cls] = VERDICT[v.verdict] || [v.verdict, "muted"];
  return (
    <span className={"dv " + cls} title={(v.ips || []).join(", ") || v.error || ""}>
      {label}
    </span>
  );
}

export default function DiagPage() {
  const { busy } = useStore();
  const toast = useToast();
  const [report, setReport] = useState(null);
  const [domains, setDomains] = useState("");
  const [running, setRunning] = useState(false);

  useEffect(() => { get("/api/diag/dns").then(setReport).catch(() => {}); }, []);

  const runCheck = async () => {
    setRunning(true);
    try {
      setReport(await post("/api/diag/dns", { domains }));
    } catch (e) {
      toast(e.message, true);
    } finally {
      setRunning(false);
    }
  };

  const r = report;
  const s = r && SUMMARY[r.verdict];
  const cols = r ? [...r.blocked, ...r.control] : [];

  return (
    <section className="tab">
      <div className="intro">
        <h2>Диагностика</h2>
        <p>
          Подменяет ли провайдер DNS. Адреса заблокированных сайтов сравниваются с ответами по шифрованным каналам
          (DoH и DoT): их провайдер прочитать и подменить не может. Ничего в системе не меняется
        </p>
      </div>

      <div className="card stack">
        <div className="field">
          <label htmlFor="d-domains">Свои домены <span className="sub">необязательно</span></label>
          <input id="d-domains" className="mono" spellCheck={false} value={domains} onChange={(e) => setDomains(e.target.value)}
            placeholder="например: x.com, instagram.com" />
          <p className="hint">Проверю и их вместе со стандартными: rutor.info, flibusta.is, rezka.ag и другими</p>
        </div>
        <div className="row">
          <Button kind="solid" disabled={running || busy} onClick={runCheck}>{running ? "Проверяю… ~5 с" : "Проверить DNS"}</Button>
          {r && <span className="hint">Проверено {new Date(r.checked_at * 1000).toLocaleString("ru")} за {(r.ms / 1000).toFixed(1)} с</span>}
        </div>
      </div>

      {r && (
        <>
          <div className={"banner inline " + s.cls}>
            <b>{s.title}</b>
            <p className="hint" style={{ margin: "4px 0 0" }}>{s.text}</p>
            {r.stubs.length > 0 && <p className="hint" style={{ margin: "4px 0 0" }}>Адрес заглушки: <code>{r.stubs.join(", ")}</code></p>}
            {r.hijack.map((h) => (
              <p key={h.net} className="hint" style={{ margin: "4px 0 0" }}>
                <b>Перехват UDP/53:</b> {h.names.join(", ")} на самом деле отвечают из одной сети <code>{h.net}</code> —
                запросы к ним заворачивает к себе провайдер
              </p>
            ))}
          </div>

          <div className="card">
            <div className="card-title">Ответы по доменам</div>
            <div className="dtable" style={{ gridTemplateColumns: `minmax(160px, 1.4fr) repeat(${cols.length}, minmax(84px, 1fr))` }}>
              <div className="dh">Сервер</div>
              {cols.map((d) => <div key={d} className="dh mono" title={(r.truth[d] || []).join(", ")}>{d}</div>)}
              {[r.system, ...r.udp].map((row) => (
                <Row key={row.kind + row.addr} row={row} cols={cols} />
              ))}
            </div>
            <p className="hint">
              «Другой адрес» — не обязательно подмена: у сайтов за CDN разные серверы отдают разные адреса. Подмена —
              это заглушка, «нет такого», пустой или ложный ответ. Российские резолверы (MSK-IX, НСДИ, Яндекс) обязаны
              выполнять блокировки — их «неправда» ожидаема и в вывод не идёт
            </p>
          </div>

          <div className="card">
            <div className="card-title">Шифрованный DNS, который у вас работает <span className="count">{r.working_encrypted.length}</span></div>
            {r.working_encrypted.length === 0
              ? <p className="hint">Ни один DoH/DoT-сервер не ответил — похоже, провайдер блокирует и их</p>
              : (
                <div className="dlist">
                  {r.working_encrypted.map((w) => (
                    <div key={w.kind + w.addr} className="ditem">
                      <span className="tag">{w.kind === "doh" ? "DoH" : "DoT"}</span>
                      <b>{w.name}</b>
                      <span className="mono sub">{w.addr}</span>
                      <span className="sub">{w.ms != null ? `${w.ms} мс` : ""}{w.rewrites ? " · сам подставляет свои прокси для заблокированного" : ""}</span>
                    </div>
                  ))}
                </div>
              )}
            <p className="hint">
              Windows 11: Параметры → Сеть и Интернет → ваше подключение → Назначение DNS-сервера → Изменить → Вручную,
              впишите IP (например, 1.1.1.1) и выберите «Только зашифрованные (DNS по HTTPS)». В браузере: Настройки →
              Конфиденциальность → «Безопасный DNS»
            </p>
            {r.no_truth.length > 0 && (
              <p className="hint">Не с чем сравнить ({plural(r.no_truth.length, "домен", "домена", "доменов")} {r.no_truth.join(", ")}): шифрованный DNS не вернул по ним адресов</p>
            )}
          </div>
          <p className="hint">Методика и списки серверов — <a href="https://github.com/Runnin4ik/dpi-detector" target="_blank" rel="noreferrer">dpi-detector</a> (Runnin4ik, MIT)</p>
        </>
      )}
    </section>
  );
}

function Row({ row, cols }) {
  const sub = row.kind === "system" ? "как видит Windows"
    : !row.alive ? "не отвечает"
    : row.hijacked ? `перехвачен · отвечает ${row.egress}`
    : row.ru ? "российский резолвер" : row.addr;
  return (
    <>
      <div className={"dsrv" + (row.kind === "system" ? " sys" : "")}>
        <span>{row.name}</span>
        <span className={"sub" + (row.hijacked ? " t-bad" : "")}>{sub}</span>
      </div>
      {cols.map((d) => <div key={d}><Verdict v={row.domains[d]} /></div>)}
    </>
  );
}
