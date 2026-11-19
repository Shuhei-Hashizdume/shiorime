// 利用規約・プライバシーポリシー（screens.md 12.）。本文は公開前に別途作る。

import { Sheet } from "./Sheet";

export type LegalKind = "terms" | "privacy";

const TITLES: Record<LegalKind, string> = {
  terms: "利用規約",
  privacy: "プライバシーポリシー",
};

export function LegalSheet({ kind, onClose }: { kind: LegalKind; onClose: () => void }) {
  return (
    <Sheet title={TITLES[kind]} onClose={onClose}>
      <p>本文は公開前に掲載します。</p>
    </Sheet>
  );
}
