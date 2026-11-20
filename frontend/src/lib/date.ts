// 日付の書き方（screens.md「全画面で共通の決まり」）。日本時間で判断する。
// 今日は「今日」、今年は「10月20日」、去年以前は「2025年10月20日」。

const parts = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

function ymd(date: Date): { year: number; month: number; day: number } {
  const values = Object.fromEntries(parts.formatToParts(date).map((p) => [p.type, p.value]));
  return { year: Number(values.year), month: Number(values.month), day: Number(values.day) };
}

export function formatDay(iso: string, now: Date = new Date()): string {
  const d = ymd(new Date(iso));
  const today = ymd(now);
  if (d.year === today.year && d.month === today.month && d.day === today.day) return "今日";
  if (d.year === today.year) return `${d.month}月${d.day}日`;
  return `${d.year}年${d.month}月${d.day}日`;
}
