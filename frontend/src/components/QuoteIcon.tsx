// 引用符のアイコン（独自に描いたもの。visual.md 6章、mockups/quote.html）

export function QuoteIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        transform="translate(0 2)"
        d="M3 13 C 3 8.5 5.2 5.2 9 4 L 9.8 5.6 C 7.7 6.6 6.6 8.2 6.5 10 H 9 V 16 H 3 Z M12.5 13 C 12.5 8.5 14.7 5.2 18.5 4 L 19.3 5.6 C 17.2 6.6 16.1 8.2 16 10 H 18.5 V 16 H 12.5 Z"
      />
    </svg>
  );
}
