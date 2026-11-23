import EngineCard from "./EngineCard.jsx";
import RoutesCard from "./RoutesCard.jsx";
import GamesSummary from "./GamesSummary.jsx";
import IpsetCard from "./IpsetCard.jsx";
import TgMini from "./TgMini.jsx";
import "../../styles/panel.css";

export default function PanelPage() {
  return (
    <section className="tab">
      <EngineCard />
      <RoutesCard />
      <div className="grid2">
        <GamesSummary />
        <IpsetCard />
      </div>
      <TgMini />
    </section>
  );
}
