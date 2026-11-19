// 下から出るシート（パソコンでは中央のモーダル）。visual.md 9・11・12章。
// 開いている間は後ろの画面を固定し、フォーカスをシートの中に閉じこめる。Esc で閉じる。
// 閉じたら、開いたボタンにフォーカスを戻す。

import { X } from "@phosphor-icons/react";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

type SheetProps = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** full：ほぼ全画面（利用規約など）／auto：中身の高さ（確認・メニュー・短い入力） */
  variant?: "full" | "auto";
  /** false なら見出しと「×」を出さない（メニューなど。見出しは読み上げ用にだけ残す） */
  showHeader?: boolean;
};

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select, [tabindex]:not([tabindex="-1"])';

export function Sheet({ title, onClose, children, variant = "full", showHeader = true }: SheetProps) {
  const titleId = useId();
  const sheetRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    // 自動でカーソルを入れたい欄（data-autofocus）があればそこへ、なければ最初の押せる部品へ
    const target =
      sheetRef.current?.querySelector<HTMLElement>("[data-autofocus]") ??
      sheetRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    target?.focus({ preventScroll: true });

    return () => {
      document.body.style.overflow = overflow;
      opener?.focus({ preventScroll: true });
    };
  }, []);

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCloseRef.current();
      return;
    }
    if (event.key !== "Tab" || !sheetRef.current) return;
    const items = Array.from(sheetRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
  }

  return createPortal(
    <div
      className="sheet-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <div
        ref={sheetRef}
        className={`sheet sheet-${variant}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={handleKeyDown}
      >
        {showHeader ? (
          <div className="sheet-header">
            <h2 className="sheet-title" id={titleId}>
              {title}
            </h2>
            <button type="button" className="icon-button" aria-label="閉じる" onClick={() => onCloseRef.current()}>
              <X size={24} aria-hidden="true" />
            </button>
          </div>
        ) : (
          <h2 className="visually-hidden" id={titleId}>
            {title}
          </h2>
        )}
        <div className="sheet-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
