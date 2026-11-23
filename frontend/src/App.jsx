import { StoreProvider, useHashTab, useStore } from "./store.jsx";
import TopBar from "./layout/TopBar.jsx";
import Nav from "./layout/Nav.jsx";
import Banners from "./layout/Banners.jsx";
import PanelPage from "./pages/panel/PanelPage.jsx";
import SplitPage from "./pages/split/SplitPage.jsx";
import GamesPage from "./pages/games/GamesPage.jsx";
import ScanPage from "./pages/scan/ScanPage.jsx";
import ServicesPage from "./pages/services/ServicesPage.jsx";
import TelegramPage from "./pages/telegram/TelegramPage.jsx";
import UpdatesPage from "./pages/updates/UpdatesPage.jsx";
import SettingsPage from "./pages/settings/SettingsPage.jsx";

export const TABS = [
  { id: "panel", label: "Пульт", Page: PanelPage },
  { id: "split", label: "Сплит", Page: SplitPage },
  { id: "games", label: "Игры", Page: GamesPage },
  { id: "scan", label: "Подбор", Page: ScanPage },
  { id: "services", label: "Сервисы", Page: ServicesPage },
  { id: "telegram", label: "Telegram", Page: TelegramPage },
  { id: "updates", label: "Обновления", Page: UpdatesPage },
  { id: "settings", label: "Настройки", Page: SettingsPage },
];

function Shell() {
  const tab = useHashTab(TABS.map((t) => t.id), "panel");
  const { status, offline } = useStore();
  const { Page } = TABS.find((t) => t.id === tab);
  return (
    <>
      <TopBar />
      <Banners />
      <div className="shell">
        <Nav tabs={TABS} active={tab} />
        <main>
          {offline && <div className="banner warn inline">Нет связи с сервером приложения — перезапустите Пипо Алексея</div>}
          {status ? <Page key={tab} /> : !offline && <div className="empty">Загрузка…</div>}
        </main>
      </div>
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
