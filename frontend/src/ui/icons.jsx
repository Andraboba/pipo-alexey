// Линейные иконки 16px, штрих 1.6, цвет текста.
const Svg = ({ children }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

export const IconCheck = () => <Svg><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></Svg>;
export const IconPause = () => <Svg><circle cx="8" cy="8" r="5.5" /><path d="M6.5 6v4M9.5 6v4" /></Svg>;
export const IconPlay = () => <Svg><circle cx="8" cy="8" r="5.5" /><path d="m7 5.8 3 2.2-3 2.2z" /></Svg>;
export const IconTrash = () => <Svg><path d="M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.5 8.5h5l.5-8.5" /></Svg>;

// Знак: монограмма «П» — Пипо Алексей (янтарь — тот же цвет, что «через запрет»)
export const Logo = () => (
  <svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true">
    <rect width="32" height="32" rx="8" className="brand-bg" />
    <path d="M10 24V9h12v15" fill="none" stroke="var(--amber)" strokeWidth="3.2" strokeLinejoin="round" strokeLinecap="round" />
  </svg>
);
