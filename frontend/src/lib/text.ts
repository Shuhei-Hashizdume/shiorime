// 文字の数え方（api.md 5-1）。サーバーの app/core/text.py と同じ考え方で数える。
// 画面の判定は目安で、正しいかどうかはサーバーが決める。

const segmenter = new Intl.Segmenter("ja", { granularity: "grapheme" });

/** 見た目の文字数（書記素クラスタの数）。"😀" は 1、"👨‍👩‍👧" は 1。 */
export function countChars(value: string): number {
  let count = 0;
  for (const _ of segmenter.segment(value)) count++;
  return count;
}

/** 前後の空白を除き、NFC にそろえる。 */
export function normalize(value: string): string {
  return value.trim().normalize("NFC");
}
