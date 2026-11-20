// 次の一歩の数に添える芽のアイコン（ロゴの芽と同じ形）。

export function SproutIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="20 16 60 48" aria-hidden="true">
      <path d="M50 62 V 36" stroke="currentColor" strokeWidth="5" strokeLinecap="round" fill="none" />
      <path d="M50 42 C 48 30, 38 24, 26 26 C 28 38, 38 44, 50 42 Z" fill="currentColor" />
      <path d="M50 38 C 52 26, 62 19, 74 21 C 72 33, 62 39, 50 38 Z" fill="currentColor" />
    </svg>
  );
}
