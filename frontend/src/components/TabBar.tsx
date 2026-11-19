// 画面下の共通メニュー（visual.md 5章）。アイコンの形は mockups/tabicons.html を正とする。
// 選択中は塗りつぶし＋灯りの色＋中太、選択していないときは線＋控えめな色。

import { Link, useLocation } from "react-router";

type Tab = "shelf" | "insights" | "profile";

function ShelfIcon({ on }: { on: boolean }) {
  return on ? (
    <g fill="currentColor">
      <rect x="3" y="5.5" width="5" height="14.5" rx="1.4" />
      <rect x="8.8" y="3.5" width="5" height="16.5" rx="1.4" />
      <rect x="14.8" y="4.6" width="5" height="15.4" rx="1.4" transform="rotate(-14 17.3 20)" />
      <rect x="2" y="20" width="20" height="2" rx="1" />
    </g>
  ) : (
    <g className="icon-line">
      <rect x="3.5" y="6" width="4" height="13.5" rx="1.2" />
      <rect x="8.5" y="4" width="4" height="15.5" rx="1.2" />
      <rect x="14.6" y="5.2" width="4" height="14.6" rx="1.2" transform="rotate(-14 16.6 19.5)" />
      <path d="M2.5 20.5 H 21.5" />
    </g>
  );
}

function NoteIcon({ on }: { on: boolean }) {
  return on ? (
    <g>
      <path
        fill="currentColor"
        d="M6.2 2.8 H 15.6 C 16 2.8 16.3 2.9 16.6 3.2 L 19.4 6 C 19.7 6.3 19.8 6.6 19.8 7 V 20.2 C 19.8 20.8 19.4 21.2 18.8 21.2 H 6.2 C 5.6 21.2 5.2 20.8 5.2 20.2 V 3.8 C 5.2 3.2 5.6 2.8 6.2 2.8 Z"
      />
      <path d="M9 2.8 V 11 L 11 9.5 L 13 11 V 2.8 Z" fill="var(--tabbar)" />
      <path d="M9 15 H 16 M9 17.8 H 13.5" fill="none" stroke="var(--tabbar)" strokeWidth="1.9" strokeLinecap="round" />
    </g>
  ) : (
    <g className="icon-line">
      <path d="M6 3.5 H 15.5 L 19 7 V 20.5 H 6 Z" />
      <path d="M9 3.5 V 11 L 11 9.5 L 13 11 V 3.5" />
      <path d="M9 15 H 16 M9 17.8 H 13.5" />
    </g>
  );
}

function MeIcon({ on }: { on: boolean }) {
  return on ? (
    <g fill="currentColor">
      <circle cx="12" cy="8.3" r="4.6" />
      <path d="M3.8 20 C 4.8 15.6 8 13.8 12 13.8 S 19.2 15.6 20.2 20 C 20.4 20.7 19.9 21.3 19.2 21.3 H 4.8 C 4.1 21.3 3.6 20.7 3.8 20 Z" />
    </g>
  ) : (
    <g className="icon-line">
      <circle cx="12" cy="8.5" r="4" />
      <path d="M4.5 20.5 C 5.5 16.6 8.4 14.8 12 14.8 S 18.5 16.6 19.5 20.5" />
    </g>
  );
}

function currentTab(pathname: string): Tab {
  if (pathname.startsWith("/insights") || pathname.startsWith("/insight-groups") || pathname.startsWith("/ai-proposals"))
    return "insights";
  if (pathname.startsWith("/profile")) return "profile";
  return "shelf";
}

export function TabBar() {
  const { pathname } = useLocation();
  const tab = currentTab(pathname);
  const items: { key: Tab; to: string; label: string; Icon: typeof ShelfIcon }[] = [
    // 共通メニューの「本棚」は、いつも「読書中」から始める（screens.md 1.）
    { key: "shelf", to: "/", label: "本棚", Icon: ShelfIcon },
    { key: "insights", to: "/insights", label: "気づき", Icon: NoteIcon },
    { key: "profile", to: "/profile", label: "プロフィール", Icon: MeIcon },
  ];
  return (
    <nav className="tabbar" aria-label="メニュー">
      {items.map(({ key, to, label, Icon }) => {
        const on = key === tab;
        return (
          <Link key={key} to={to} className={`tab${on ? " on" : ""}`} aria-current={on ? "page" : undefined}>
            <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
              <Icon on={on} />
            </svg>
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
