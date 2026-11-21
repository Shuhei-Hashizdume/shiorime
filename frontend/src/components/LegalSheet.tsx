// 利用規約・プライバシーポリシー（screens.md 12.）。ウェルカム・新規登録・プロフィールから開く。
// 本文は src/legal/content.ts。見出し・本文・箇条書きで読みやすくする（visual.md）。

import { PRIVACY, TERMS, type LegalDocument } from "../legal/content";
import { Sheet } from "./Sheet";

export type LegalKind = "terms" | "privacy";

const DOCUMENTS: Record<LegalKind, { title: string; doc: LegalDocument }> = {
  terms: { title: "利用規約", doc: TERMS },
  privacy: { title: "プライバシーポリシー", doc: PRIVACY },
};

export function LegalSheet({ kind, onClose }: { kind: LegalKind; onClose: () => void }) {
  const { title, doc } = DOCUMENTS[kind];
  return (
    <Sheet title={title} onClose={onClose}>
      <div className="legal">
        <p>{doc.intro}</p>
        {doc.sections.map((section) => (
          <section key={section.heading}>
            <h3 className="legal-heading">{section.heading}</h3>
            {section.paragraphs?.map((text, i) => <p key={i}>{text}</p>)}
            {section.items && (
              <ul className="legal-list">
                {section.items.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            )}
            {section.note && <p className="legal-note">{section.note}</p>}
          </section>
        ))}
        <p className="legal-date">{doc.enactedOn} 制定</p>
      </div>
    </Sheet>
  );
}
