// 気づきの詳細（screens.md 6.、api.md 7-5・2-3・2-4）。
// AI提案はここから始める。作成中のAI提案があれば2秒ごとに問い合わせ、完了したら次の一歩を入れ替える。

import { ArrowLeft, CaretRight, DotsThreeVertical } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { aiProposalsApi, type AiUsage } from "../api/aiProposals";
import { ApiError } from "../api/client";
import { insightsApi, type InsightDetail as Insight } from "../api/insights";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { ErrorBanner, Notice } from "../components/Feedback";
import { Making } from "../components/Growing";
import { QuoteIcon } from "../components/QuoteIcon";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { formatDay } from "../lib/date";
import { useProposalPolling, type PollUpdate } from "../lib/useProposalPolling";

type LoadState = { kind: "loading" } | { kind: "ready"; insight: Insight } | { kind: "not_found" } | { kind: "error" };

/** 押して断られたときのお知らせ（api.md 2-4 の表） */
type StartNotice = { tone: "calm" | "error"; title: string; text: string };

const LOGGING_IS_FREE = "（気づきの登録は何件でもできます）";

export default function InsightDetail() {
  const { insightId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  const showToast = useToast();
  // 作成した直後か（戻るボタンを本ごとの気づき一覧へ向けるため）
  const [justCreated] = useState(() => (location.state as { justCreated?: boolean } | null)?.justCreated === true);

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [sheet, setSheet] = useState<"menu" | "delete" | "again" | null>(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<StartNotice | null>(null);

  const loadUsage = useCallback(async () => {
    try {
      setUsage(await aiProposalsApi.usage());
    } catch (error) {
      onUnauthorized(error);
    }
  }, [onUnauthorized]);

  /** quiet：スケルトンを出さずに取り直す（完了の反映・断られたあとなど） */
  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setState({ kind: "loading" });
      // 残り回数は気づきではなく自分の情報なので、別の API から同時に取る（api.md 7-5）
      void loadUsage();
      try {
        setState({ kind: "ready", insight: await insightsApi.get(insightId) });
      } catch (error) {
        if (onUnauthorized(error)) return;
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) setState({ kind: "not_found" });
        else if (!quiet) setState({ kind: "error" });
      }
    },
    [insightId, onUnauthorized, loadUsage],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // 作成中のAI提案があれば、2秒ごとに問い合わせる（api.md 2-3）
  const pending = state.kind === "ready" ? state.insight.pending_proposal : null;
  const handlePoll = useCallback(
    (update: PollUpdate) => {
      if (update.kind === "proposal" && (update.proposal.status === "generating_question" || update.proposal.status === "generating_plans")) return;
      if (update.kind === "proposal" && update.proposal.status === "completed") showToast("次の一歩ができました");
      // 完了・失敗・削除のどれでも、気づきを取り直して今の状態を出す
      void load(true);
    },
    [load, showToast],
  );
  useProposalPolling(pending?.status === "processing" ? pending.id : null, handlePoll, onUnauthorized);

  async function startProposal() {
    if (state.kind !== "ready" || starting) return;
    setSheet(null);
    setNotice(null);
    setStarting(true);
    // 受付番号。返事が届かなかったら、同じ番号で1回だけ送り直す（回数を二重に使わない。api.md 2-4）
    const key = crypto.randomUUID();
    try {
      let started: { id: string };
      try {
        started = await aiProposalsApi.start(state.insight.id, key);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 0)) throw error;
        started = await aiProposalsApi.start(state.insight.id, key);
      }
      navigate(`/ai-proposals/${started.id}`, { state: { fresh: true } });
    } catch (error) {
      setStarting(false);
      if (onUnauthorized(error)) return;
      const code = error instanceof ApiError ? error.code : "";
      if (code === "INSIGHT_NOT_FOUND") {
        setState({ kind: "not_found" });
        return;
      }
      if (code === "AI_DAILY_LIMIT")
        setNotice({ tone: "calm", title: "AI提案を始められませんでした", text: "本日の回数を使い切っています（ほかの端末で使った分も含みます）。" });
      else if (code === "AI_APP_LIMIT")
        setNotice({ tone: "calm", title: "AI提案を始められませんでした", text: "本日はAI提案の受付を終了しました。" });
      else if (code === "AI_PROPOSAL_IN_PROGRESS")
        setNotice({ tone: "calm", title: "この気づきのAI提案を処理中です", text: "しばらくお待ちください。" });
      else
        setNotice({ tone: "error", title: "AI提案を始められませんでした", text: "通信に失敗しました。時間をおいて、もう一度お試しください。" });
      // ボタンと残り回数を最新にする（処理中なら、作成中の表示と問い合わせに切り替わる）
      void load(true);
    }
  }

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
              {pending?.status === "processing" && (
                <Making title="新しい次の一歩を作成中です…">完了すると、ここに表示されます</Making>
              )}
            </section>
          )}
          {!state.insight.latest_proposal && pending?.status === "processing" && (
            <section className="next-steps" aria-label="次の一歩">
              <Making title="次の一歩を作成中です…" />
            </section>
          )}

          <AiStart
            insight={state.insight}
            usage={usage}
            starting={starting}
            notice={notice}
            onStart={() => (state.insight.latest_proposal ? setSheet("again") : void startProposal())}
          />
        </>
      )}

      {state.kind === "ready" && sheet === "again" && (
        <Sheet title="もう一度AI提案を受けますか？" onClose={() => setSheet(null)} variant="auto" showHeader={false}>
          <div className="confirm">
            <p className="confirm-title">もう一度AI提案を受けますか？</p>
            <p className="confirm-text">
              新しいAI提案が完了すると、今の次の一歩は新しいものに置き換わり、元には戻せません。途中でやめた場合は、今の次の一歩が残ります。
            </p>
            <div className="sheet-actions">
              <button type="button" className="button button-primary" onClick={() => void startProposal()}>
                AI提案を受ける
              </button>
              <button type="button" className="button button-ghost" onClick={() => setSheet(null)}>
                キャンセル
              </button>
            </div>
            {usage && <p className="rest">本日あと{usage.remaining_today}回（受けると1回使います）</p>}
          </div>
        </Sheet>
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

/** AI提案のボタンと残り回数（screens.md 6.「AI提案のボタンと確認」） */
function AiStart({
  insight,
  usage,
  starting,
  notice,
  onStart,
}: {
  insight: Insight;
  usage: AiUsage | null;
  starting: boolean;
  notice: StartNotice | null;
  onStart: () => void;
}) {
  const hasPlans = insight.latest_proposal !== null;
  const pending = insight.pending_proposal;
  // 押せない理由。処理中 → 本人の回数 → アプリ全体の上限の順に見る
  const blocked =
    pending?.status === "processing"
      ? "processing"
      : usage && usage.remaining_today <= 0
        ? "daily"
        : usage?.app_limit_reached
          ? "app"
          : null;

  let rest: string;
  if (blocked === "processing") rest = "AI提案を処理中です";
  else if (blocked === "daily") rest = "本日のAI提案は使い切りました。明日0時に回復します。";
  else if (blocked === "app") rest = "本日はAI提案の受付を終了しました。明日0時に再開します。";
  else rest = usage ? `本日あと${usage.remaining_today}回` : "";

  return (
    <section className="ai-start" aria-label="AI提案">
      {!hasPlans && <p className="ai-explain">AIが気づきを深掘りする質問をし、あなたの回答から次の一歩を一緒に考えます。</p>}
      {pending?.status === "failed" && !notice && (
        <Notice tone="error" title="次の一歩を作成できませんでした">
          使った回数は戻りません。もう一度AI提案を受けられます。
        </Notice>
      )}
      {notice && (
        <Notice tone={notice.tone} title={notice.title}>
          {notice.text}
        </Notice>
      )}
      <button
        type="button"
        className={`button ${hasPlans ? "button-secondary" : "button-primary"} ai-start-button${blocked ? " is-off" : ""}`}
        aria-disabled={blocked || starting ? true : undefined}
        onClick={() => {
          if (!blocked && !starting) onStart();
        }}
      >
        {starting ? "準備しています…" : hasPlans ? "もう一度AI提案を受ける" : "AI提案を受ける"}
      </button>
      <p className="rest">
        {rest}
        {blocked !== "processing" && (
          <>
            {rest && <br />}
            {LOGGING_IS_FREE}
          </>
        )}
      </p>
    </section>
  );
}
