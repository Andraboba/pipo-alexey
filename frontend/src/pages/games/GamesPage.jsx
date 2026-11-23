import { post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import GameFilterCard from "./GameFilterCard.jsx";
import GamesWarning from "./GamesWarning.jsx";
import ProfileCard from "./ProfileCard.jsx";
import PresetCatalog from "./PresetCatalog.jsx";
import CustomGameForm from "./CustomGameForm.jsx";
import "../../styles/games.css";

export default function GamesPage() {
  const { split, watchJob, busy } = useStore();
  return (
    <section className="tab">
      <div className="intro">
        <h2>Игры</h2>
        <p>
          Заблокированную игру — <b className="t-zapret">через запрет</b> вместе с игровым фильтром. Незаблокированную —{" "}
          <b className="t-direct">напрямую</b>, чтобы запрет не трогал её трафик и пинг.
        </p>
      </div>
      <GameFilterCard />
      <GamesWarning />
      <div className="profiles">
        {split?.profiles.length
          ? split.profiles.map((p) => <ProfileCard key={p.id} p={p} />)
          : <div className="card empty">Профилей нет — добавьте игру из каталога ниже</div>}
      </div>

      <div className="list-head section-gap">
        <h2>Каталог игр</h2>
        <Button disabled={busy} onClick={async () => watchJob(await post("/api/split/profiles/refresh"))}>Обновить подсети по ASN</Button>
      </div>
      <p className="hint" style={{ marginTop: -8 }}>
        Подсети берутся из RIPEstat по номерам сетей (ASN) издателей и игровых хостингов. Облака AWS, Google, Azure и
        Cloudflare целиком не добавляются — у таких игр работают домены
      </p>
      <PresetCatalog />
      <CustomGameForm />
    </section>
  );
}
