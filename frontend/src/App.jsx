import { useEffect, useState } from "react";
import { StoreProvider, useHashTab, useStore } from "./store.jsx";
import TopBar from "./layout/TopBar.jsx";
import Nav from "./layout/Nav.jsx";
import Banners from "./layout/Banners.jsx";
import Tour, { startTour, tourSeen } from "./ui/Tour.jsx";
import PanelPage from "./pages/panel/PanelPage.jsx";
import SplitPage from "./pages/split/SplitPage.jsx";
import GamesPage from "./pages/games/GamesPage.jsx";
import ScanPage from "./pages/scan/ScanPage.jsx";
import EvolvePage from "./pages/evolve/EvolvePage.jsx";
import DiagPage from "./pages/diag/DiagPage.jsx";
import ServicesPage from "./pages/services/ServicesPage.jsx";
import TelegramPage from "./pages/telegram/TelegramPage.jsx";
import UpdatesPage from "./pages/updates/UpdatesPage.jsx";
import SettingsPage from "./pages/settings/SettingsPage.jsx";
import {
  IconPanel, IconSplit, IconGames, IconScan, IconEvolve, IconDiag,
  IconServices, IconTelegram, IconUpdates, IconSettings,
} from "./ui/icons.jsx";

export const TABS = [
  { id: "panel", label: "Пульт", Icon: IconPanel, Page: PanelPage },
  { id: "scan", label: "Подбор", Icon: IconScan, Page: ScanPage },
  { id: "telegram", label: "Прокси Telegram", Icon: IconTelegram, Page: TelegramPage },
  { id: "services", label: "Сервисы", Icon: IconServices, Page: ServicesPage },
  { id: "games", label: "Игры", Icon: IconGames, Page: GamesPage },
  { id: "split", label: "Сплит", Icon: IconSplit, Page: SplitPage },
  { id: "diag", label: "Диагностика", Icon: IconDiag, Page: DiagPage },
  { id: "evolve", label: "Эволюция", Icon: IconEvolve, Page: EvolvePage },
  { id: "updates", label: "Обновления", Icon: IconUpdates, Page: UpdatesPage },
  { id: "settings", label: "Настройки", Icon: IconSettings, Page: SettingsPage },
];

function Shell() {
  const tab = useHashTab(TABS.map((t) => t.id), "panel");
  const { status, offline } = useStore();
  const { Page } = TABS.find((t) => t.id === tab);
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem("navCollapsed") === "1");
  const toggleNav = () => setNavCollapsed((c) => {
    localStorage.setItem("navCollapsed", c ? "0" : "1");
    return !c;
  });
  // первый запуск — гайд по вкладкам, как только есть что показывать
  const ready = !!status;
  useEffect(() => { if (ready && !tourSeen()) startTour(); }, [ready]);
  return (
    <>
      <TopBar />
      <Banners />
      <div className={"shell" + (navCollapsed ? " nav-collapsed" : "")}>
        <Nav tabs={TABS} active={tab} collapsed={navCollapsed} onToggle={toggleNav} />
        <main>
          {offline && <div className="banner warn inline">Нет связи с сервером приложения — перезапустите Пипо Алексея</div>}
          {status ? <Page key={tab} /> : !offline && <div className="empty">Загрузка…</div>}
        </main>
      </div>
      {status && <Tour />}
    </>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  );
}
