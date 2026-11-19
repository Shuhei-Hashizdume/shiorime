// 気づきの詳細（screens.md 6.、api.md 7-5）。
// AI提案のボタン・本日の残り回数・作成中の表示は、機能4（AI提案）で足す。

import { ArrowLeft, CaretRight, DotsThreeVertical } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import { insightsApi, type InsightDetail as Insight } from "../api/insights";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { ErrorBanner } from "../components/Feedback";
import { QuoteIcon } from "../components/QuoteIcon";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { formatDay } from "../lib/date";

type LoadState = { kind: "loading" } | { kind: "ready"; insight: Insight } | { kind: "not_found" } | { kind: "error" };

export default function InsightDetail() {
  const { insightId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  const showToast = useToast();
  // 作成した直後か（戻るボタンを本ごとの気づき一覧へ向けるため）
  const [justCreated] = useState(() => (location.state as { justCreated?: boolean } | null)?.justCreated === true);

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [sheet, setSheet] = useState<"menu" | "delete" | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", insight: await insightsApi.get(insightId) });
    } catch (error) {
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) setState({ kind: "not_found" });
      else setState({ kind: "error" });
    }
  }, [insightId, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  function goBack() {
    const groupUrl = state.kind === "ready" ? `/insight-groups/${state.insight.book.id}` : "/insights";
    // 作成した直後は、作成画面を開いた元ではなく本ごとの気づき一覧へ（screens.md 6.）
    if (justCreated || location.key === "default") navigate(groupUrl, { replace: justCreated });
    else navigate(-1);
  }

  return (
    <main className="page page-with-tabs">
      <div className="topbar topbar-between">
        <button type="button" className="icon-button" aria-label="戻る" onClick={goBack}>
          <ArrowLeft size={24} aria-hidden="true" />
        </button>
        {state.kind === "ready" && (
          <button type="button" className="icon-button" aria-label="メニュー" onClick={() => setSheet("menu")}>
            <DotsThreeVertical size={24} weight="bold" aria-hidden="true" />
          </button>
        )}
      </div>

      {state.kind === "loading" && (
        <div aria-busy="true" aria-label="読み込み中">
          <div className="skeleton skeleton-line" style={{ width: "60%" }} />
          <div className="skeleton skeleton-card tall" />
        </div>
      )}

      {state.kind === "not_found" && (
        <div className="state-box">
          <h1 className="state-title">この気づきは見つかりませんでした</h1>
          <Link to="/insights" className="button button-secondary">
            気づき一覧へ戻る
          </Link>
        </div>
      )}

      {state.kind === "error" && (
        <div className="state-box">
          <p>気づきを読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={() => void load()}>
            もう一度読み込む
          </button>
        </div>
      )}

      {state.kind === "ready" && (
        <>
          <div className="insight-book">
            <BookCover url={state.insight.book.cover_url} className="insight-book-cover" />
            <div>
              <p className="insight-book-title">{state.insight.book.title}</p>
              <p className="group-meta">
                {state.insight.page ? `P.${state.insight.page}　` : ""}
                {formatDay(state.insight.created_at) === "今日" ? "今日" : `${formatDay(state.insight.created_at)}に`}
                書いた気づき
              </p>
            </div>
          </div>

          <article className="card insight-full">
            <div className="ribbon" aria-hidden="true" />
            {state.insight.quote && (
              <p className="quote">
                <QuoteIcon />
                {state.insight.quote}
              </p>
            )}
            <p className="insight-full-body">{state.insight.body}</p>
          </article>

          {state.insight.latest_proposal && (
            <section className="next-steps" aria-label="次の一歩">
              <h2 className="next-steps-title">{formatDay(state.insight.latest_proposal.completed_at)}のAI提案</h2>
              <ol className="next-steps-list">
                {state.insight.latest_proposal.plans.map((plan, i) => (
                  <li key={i}>{plan.text}</li>
                ))}
              </ol>
              <Link to={`/ai-proposals/${state.insight.latest_proposal.id}`} className="row-link">
                深掘りと回答も見る
                <CaretRight size={18} aria-hidden="true" />
              </Link>
            </section>
          )}
        </>
      )}

      {state.kind === "ready" && sheet === "menu" && (
        <Sheet title="気づきのメニュー" onClose={() => setSheet(null)} variant="auto" showHeader={false}>
          <div className="menu-list">
            <button
              type="button"
              className="menu-item"
              onClick={() => navigate(`/insights/${state.insight.id}/edit`, { state: { fromDetail: true } })}
            >
              気づきを編集
            </button>
            <button type="button" className="menu-item danger" onClick={() => setSheet("delete")}>
              気づきを削除
            </button>
            <button type="button" className="menu-item" onClick={() => setSheet(null)}>
              キャンセル
            </button>
          </div>
        </Sheet>
      )}

      {state.kind === "ready" && sheet === "delete" && (
        <DeleteSheet
          insight={state.insight}
          onClose={() => setSheet(null)}
          onDeleted={(showDone) => {
            if (showDone) showToast("気づきを削除しました");
            navigate(`/insight-groups/${state.insight.book.id}`, { replace: true });
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
    </main>
  );
}

function DeleteSheet({
  insight,
  onClose,
  onDeleted,
  onUnauthorized,
}: {
  insight: Insight;
  onClose: () => void;
  onDeleted: (showDone: boolean) => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setSubmitting(true);
    setError(null);
    try {
      await insightsApi.remove(insight.id);
      onDeleted(true);
    } catch (err) {
      setSubmitting(false);
      if (onUnauthorized(err)) return;
      // すでに削除されていた（404）なら、エラーを見せずに本ごとの気づき一覧へ
      if (err instanceof ApiError && err.status === 404) return onDeleted(false);
      setError("削除できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="この気づきを削除しますか？" onClose={onClose} variant="auto" showHeader={false}>
      <div className="confirm">
        <p className="confirm-title">この気づきを削除しますか？</p>
        <p className="confirm-text">
          {insight.latest_proposal
            ? "この気づきの次の一歩（AI提案）も一緒に削除されます。削除すると、元に戻せません。"
            : "削除すると、元に戻せません。"}
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="sheet-actions">
          <button type="button" className="button button-danger" onClick={() => void handleDelete()} disabled={submitting}>
            削除する
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </div>
    </Sheet>
  );
}
