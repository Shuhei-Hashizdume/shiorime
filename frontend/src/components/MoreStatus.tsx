// 一覧の続きを読み込むときの表示（読み込み中・失敗）。

export function MoreStatus({ state, onRetry }: { state: "idle" | "loading" | "error"; onRetry: () => void }) {
  if (state === "loading") return <p className="more-status">読み込み中…</p>;
  if (state === "error") {
    return (
      <div className="state-box">
        <p>読み込めませんでした</p>
        <button type="button" className="button button-secondary" onClick={onRetry}>
          もう一度読み込む
        </button>
      </div>
    );
  }
  return null;
}
