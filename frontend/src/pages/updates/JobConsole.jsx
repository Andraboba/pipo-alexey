import { JOB_TITLE } from "../../store.jsx";

export default function JobConsole({ job }) {
  const running = job.state === "running";
  const suffix = running ? "…" : job.state === "done" ? " — готово" : " — ошибка";
  const width = !running ? "100%" : job.progress != null ? Math.round(job.progress * 100) + "%" : undefined;
  return (
    <div className="card console">
      <div className="list-head">
        <div className="card-title">{JOB_TITLE[job.kind]}{suffix}</div>
        <div className={"progress" + (running && job.progress == null ? " indet" : "")}><i style={width ? { width } : undefined} /></div>
      </div>
      <pre className="mono">
        {job.log.map((l, i) => (
          <div key={i} className={"l-" + l.level}>{new Date(l.t * 1000).toLocaleTimeString("ru")}  {l.text}</div>
        ))}
      </pre>
    </div>
  );
}
