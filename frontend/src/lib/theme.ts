// 夜と朝の表示の切り替え（visual.md「夜と朝の切り替え」）。
// 選んだ表示は端末のブラウザにだけ保存する。読み込みの最初の決め方は index.html にある（ちらつかないように）。

export type ThemeChoice = "auto" | "dark" | "light";

const KEY = "shiorime-theme";

export function readTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === "dark" || value === "light" ? value : "auto";
  } catch {
    return "auto";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  try {
    if (choice === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // 保存できない（プライベートブラウズなど）ときも、今の画面の表示は切り替える
  }
}
