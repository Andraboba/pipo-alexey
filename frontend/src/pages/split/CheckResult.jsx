const STEP = { dns: "DNS", tcp: "TCP 443", tls: "TLS", http: "HTTP" };

export default function CheckResult({ result: r }) {
  const verdict = r.zapret_running
    ? "Запрет сейчас работает, проверка шла через него, если домен в его списках"
    : r.ok
      ? "Запрет выключен, а сайт открывается — он не заблокирован, его можно пустить напрямую"
      : "Запрет выключен и сайт не открывается — вероятно, заблокирован. Отправьте его через запрет";
  return (
    <div className="card check">
      <div className="card-title">
        {r.host} — {r.ok ? <span className="t-direct">открывается</span> : <span className="t-bad">не открывается</span>}
        <span className="sub mono">{r.ms} мс</span>
      </div>
      <div className="steps">
        {r.steps.map((s) => (
          <span key={s.step} className={"step " + (s.ok ? "ok" : "bad")} title={s.detail}>{STEP[s.step]}: {s.detail}</span>
        ))}
      </div>
      <p className="hint" style={{ margin: 0 }}>{verdict}</p>
    </div>
  );
}
