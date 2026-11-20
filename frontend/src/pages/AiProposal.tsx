// AI提案（screens.md 8.、api.md 7-6、要件定義書 5.5）。
// 深掘り → 回答 → 次の一歩を1つの画面で順に進める。完了したAI提案の見返しにも使う。共通メニューは出さない。
//
// 気づきの詳細の「AI提案を受ける」から来たときだけ、続きから進められる（state の fresh）。
// 再読み込み・戻る/進む・URL の直接入力で開いたとき（fresh なし）は、新しく進めず、状態に応じた表示にする。
// 回答を送る前のものは、開いた時点でサーバーに終了を伝える（/abandon）。

import { ArrowLeft, CheckCircle, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { ANSWER_MAX, aiProposalsApi, type Proposal } from "../api/aiProposals";
import { ApiError } from "../api/client";
import { useUnauthorized } from "../auth/useUnauthorized";
import { ErrorBanner, FieldErrorText, Notice } from "../components/Feedback";
import { Waiting } from "../components/Growing";
import { QuoteIcon } from "../components/QuoteIcon";
import { Sheet } from "../components/Sheet";
import { formatDay } from "../lib/date";
import { countChars, normalize } from "../lib/text";
import { useProposalPolling, type PollUpdate } from "../lib/useProposalPolling";

type View =
  | { kind: "loading" }
  | { kind: "error" }
  /** この画面で進めているAI提案 */
  | { kind: "live"; proposal: Proposal }
  /** 完了したAI提案の見返し */
  | { kind: "review"; proposal: Proposal }
  /** 開き直したら、行動プランの作成中だった */
  | { kind: "making"; insightId: string }
  /** 終了・削除されたAI提案。insightId がわからなければ気づき一覧へ戻す */
  | { kind: "ended"; insightId: string | null };

/** 回答を送る前の状態（離れると終了になる） */
const BEFORE_ANSWER = new Set(["generating_question", "awaiting_answer", "plan_failed"]);
const GENERATING = new Set(["generating_question", "generating_plans"]);

function validateAnswer(value: string): string | null {
  const count = countChars(normalize(value));
  if (count === 0) return "回答を入力してください";
  if (count > ANSWER_MAX) return `回答は${ANSWER_MAX}文字以内で入力してください（あと${count - ANSWER_MAX}文字減らしてください）`;
  return null;
}

export default function AiProposal() {
  const { proposalId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  // 気づきの詳細から始めて来たか。再読み込みで残らないよう、読んだらすぐ履歴から消す
  const fresh = useRef((location.state as { fresh?: boolean } | null)?.fresh === true);

  const [view, setView] = useState<View>({ kind: "loading" });
  const [draft, setDraft] = useState("");
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  // 一度わかった元の気づき（終了させたあとに読み直して 404 になっても「気づきに戻る」を出すため）
  const knownInsightId = useRef<string | null>(null);
  const answerId = useId();
  const answerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (fresh.current && (location.state as { fresh?: boolean } | null)?.fresh) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  const showProposal = useCallback((proposal: Proposal) => {
    setView((prev) => {
      // 送り直し待ちになったら、送った回答を入力欄に戻す（書き直してから送り直せる）
      const prevStatus = prev.kind === "live" ? prev.proposal.status : null;
      if (proposal.status === "plan_failed" && prevStatus !== "plan_failed") setDraft(proposal.answer ?? "");
      return { kind: "live", proposal };
    });
  }, []);

  const load = useCallback(async () => {
    setView({ kind: "loading" });
    let proposal: Proposal;
    try {
      proposal = await aiProposalsApi.get(proposalId);
    } catch (error) {
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && (error.status === 404 || error.status === 422))
        setView({ kind: "ended", insightId: knownInsightId.current });
      else setView({ kind: "error" });
      return;
    }
    knownInsightId.current = proposal.insight_id;

    if (fresh.current) {
      showProposal(proposal);
      return;
    }
    // 開き直した場合（要件定義書 5.5「AI提案画面を開き直した場合」）
    if (proposal.status === "completed") setView({ kind: "review", proposal });
    else if (proposal.status === "generating_plans") setView({ kind: "making", insightId: proposal.insight_id });
    else if (BEFORE_ANSWER.has(proposal.status)) {
      setView({ kind: "ended", insightId: proposal.insight_id });
      // 回答前に離れたものとして終了させる。もう消えていても（404）、表示は同じ
      aiProposalsApi.abandon(proposal.id).catch((error) => onUnauthorized(error));
    } else setView({ kind: "live", proposal });
  }, [proposalId, onUnauthorized, showProposal]);

  useEffect(() => {
    void load();
  }, [load]);

  const live = view.kind === "live" ? view.proposal : null;

  // 作成中は2秒ごとに問い合わせる
  const handlePoll = useCallback(
    (update: PollUpdate) => {
      if (update.kind === "gone") setView((prev) => ({ kind: "ended", insightId: prev.kind === "live" ? prev.proposal.insight_id : null }));
      else showProposal(update.proposal);
    },
    [showProposal],
  );
  useProposalPolling(live && GENERATING.has(live.status) ? live.id : null, handlePoll, onUnauthorized);

  // 回答を送る前は、タブを閉じる・再読み込みでブラウザ標準の確認を出す
  const beforeAnswer = live !== null && BEFORE_ANSWER.has(live.status);
  useEffect(() => {
    if (!beforeAnswer) return;
    const handler = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [beforeAnswer]);

  const insightIdOf = (v: View): string | null =>
    v.kind === "live" || v.kind === "review" ? v.proposal.insight_id : v.kind === "making" || v.kind === "ended" ? v.insightId : null;

  /** 気づきの詳細へ。アプリの中から来ていれば戻る（この画面に戻るボタンで戻らないように） */
  function goToInsight() {
    const insightId = insightIdOf(view);
    if (location.key !== "default") navigate(-1);
    else navigate(insightId ? `/insights/${insightId}` : "/insights", { replace: true });
  }

  function handleClose() {
    if (beforeAnswer) setConfirmLeave(true);
    else goToInsight();
  }

  async function leaveBeforeAnswer() {
    if (live) {
      // 回答前に離れたら終了。失敗しても移動はする（開き直したときにも終了させるため）
      await aiProposalsApi.abandon(live.id).catch((error) => onUnauthorized(error));
    }
    goToInsight();
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    if (!live || sending) return;
    const found = validateAnswer(draft);
    setAnswerError(found);
    setSendError(null);
    if (found) {
      answerRef.current?.focus();
      return;
    }
    const answer = normalize(draft);
    const isRetry = live.status === "plan_failed";
    setSending(true);
    try {
      if (isRetry) await aiProposalsApi.retry(live.id, answer);
      else await aiProposalsApi.answer(live.id, answer);
      showProposal({
        ...live,
        status: "generating_plans",
        answer,
        retries_left: isRetry ? live.retries_left - 1 : live.retries_left,
      });
    } catch (error) {
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && error.code === "AI_PROPOSAL_STATE_CONFLICT") {
        // 別の操作が先に状態を進めていた。エラーとして見せず、今の状態の表示に切り替える
        try {
          showProposal(await aiProposalsApi.get(live.id));
        } catch {
          setView({ kind: "ended", insightId: live.insight_id });
        }
      } else if (error instanceof ApiError && error.status === 404) {
        setView({ kind: "ended", insightId: live.insight_id });
      } else if (error instanceof ApiError && error.fields.some((f) => f.field === "answer")) {
        const field = error.fields.find((f) => f.field === "answer")!;
        setAnswerError(field.reason === "required" ? "回答を入力してください" : `回答は${ANSWER_MAX}文字以内で入力してください`);
      } else {
        setSendError("送信できませんでした。時間をおいて、もう一度お試しください。");
      }
    } finally {
      setSending(false);
    }
  }

  const isReview = view.kind === "review";
  const title = isReview && view.proposal.completed_at ? `${formatDay(view.proposal.completed_at)}のAI提案` : "AI提案";

  return (
    <main className="page ai-page">
      <div className="topbar">
        {isReview ? (
          <button type="button" className="icon-button" aria-label="戻る" onClick={goToInsight}>
            <ArrowLeft size={24} aria-hidden="true" />
          </button>
        ) : (
          <button type="button" className="icon-button" aria-label="閉じる" onClick={handleClose}>
            <X size={24} aria-hidden="true" />
          </button>
        )}
        <h1 className="topbar-title">{title}</h1>
      </div>

      {view.kind === "loading" && (
        <div aria-busy="true" aria-label="読み込み中">
          <div className="skeleton skeleton-card" />
          <div className="skeleton skeleton-card" />
        </div>
      )}

      {view.kind === "error" && (
        <div className="state-box">
          <p>AI提案を読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={() => void load()}>
            もう一度読み込む
          </button>
        </div>
      )}

      {view.kind === "ended" && (
        <CenterState title="このAI提案は終了しました" text="このAI提案は表示できません。気づきの詳細から新しく始めてください。">
          {view.insightId ? (
            <button type="button" className="button button-primary" onClick={goToInsight}>
              気づきに戻る
            </button>
          ) : (
            <Link to="/insights" replace className="button button-primary">
              気づき一覧へ戻る
            </Link>
          )}
        </CenterState>
      )}

      {view.kind === "making" && (
        <CenterState title="次の一歩を作成中です" text="完了すると、気づきの詳細に表示されます。">
          <BackToInsight onClick={goToInsight} />
        </CenterState>
      )}

      {view.kind === "review" && (
        <>
          <MyInsight proposal={view.proposal} full />
          <Question text={view.proposal.question} />
          <MyAnswer text={view.proposal.answer} />
          <Plans plans={view.proposal.plans} />
        </>
      )}

      {live?.status === "question_failed" && (
        <CenterState title="AIの質問を作成できませんでした" text="時間をおいて、気づきの詳細からもう一度お試しください。">
          <BackToInsight onClick={goToInsight} />
        </CenterState>
      )}

      {live?.status === "retry_limit_reached" && (
        <CenterState
          title="次の一歩を作成できませんでした"
          text="AIが応答しない状態が続いているため、このAI提案は終了しました。本日の回数は1回戻しています。時間をおいて、気づきの詳細から新しく始めてください。"
        >
          <BackToInsight onClick={goToInsight} />
        </CenterState>
      )}

      {live?.status === "generating_question" && (
        <>
          <MyInsight proposal={live} />
          <Waiting title="AIが質問を考えています…">最大1分ほどかかります</Waiting>
        </>
      )}

      {live && (live.status === "awaiting_answer" || live.status === "plan_failed") && (
        <>
          {live.status === "awaiting_answer" && <MyInsight proposal={live} />}
          <Question text={live.question} />
          {live.status === "plan_failed" && (
            <Notice tone="error" title="次の一歩を作成できませんでした">
              時間をおいて、もう一度お試しください。
            </Notice>
          )}
          <form onSubmit={handleSend} noValidate>
            <div className="field-group answer-field">
              <div className="label-row">
                <label className="label" htmlFor={answerId}>
                  回答
                </label>
                <span className={`counter${countChars(normalize(draft)) > ANSWER_MAX ? " over" : ""}`}>
                  {countChars(normalize(draft))} / {ANSWER_MAX}
                </span>
              </div>
              <div className={`input-wrap${answerError ? " invalid" : ""}`}>
                <textarea
                  ref={answerRef}
                  id={answerId}
                  className="input"
                  rows={5}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  aria-invalid={answerError ? true : undefined}
                  aria-describedby={`${answerError ? `${answerId}-error ` : ""}${answerId}-note`}
                />
              </div>
              {answerError && <FieldErrorText id={`${answerId}-error`}>{answerError}</FieldErrorText>}
              <p className="hint" id={`${answerId}-note`}>
                入力内容はAI（OpenAI）に送信されます。個人情報は書かないでください。
              </p>
            </div>
            {sendError && <ErrorBanner>{sendError}</ErrorBanner>}
            <button type="submit" className="button button-primary ai-submit" disabled={sending}>
              {live.status === "plan_failed" ? "もう一度送る（回数は使いません）" : "回答して次の一歩を受け取る"}
            </button>
            {live.status === "plan_failed" && <p className="rest">送り直せるのは、あと{live.retries_left}回です</p>}
          </form>
        </>
      )}

      {live?.status === "generating_plans" && (
        <>
          <Question text={live.question} />
          <MyAnswer text={live.answer} />
          <Waiting title="AIが次の一歩を考えています…">
            最大1分ほどかかります。この画面を離れても作成は続き、完了すると気づきの詳細に表示されます。
          </Waiting>
        </>
      )}

      {live?.status === "completed" && (
        <>
          <Question text={live.question} />
          <MyAnswer text={live.answer} />
          <Plans plans={live.plans} />
          <button type="button" className="button button-primary ai-submit" onClick={goToInsight}>
            気づきに戻る
          </button>
          <p className="saved">
            <CheckCircle size={16} weight="fill" aria-hidden="true" />
            この次の一歩は保存されています
          </p>
        </>
      )}

      {confirmLeave && (
        <Sheet title="このAI提案は削除されます" onClose={() => setConfirmLeave(false)} variant="auto" showHeader={false}>
          <div className="confirm">
            <p className="confirm-title">このAI提案は削除されます</p>
            <p className="confirm-text">深掘りと、入力した回答も削除されます。使った回数は戻りません。移動しますか？</p>
            <div className="sheet-actions">
              <button type="button" className="button button-primary" onClick={() => setConfirmLeave(false)}>
                回答を続ける
              </button>
              <button type="button" className="button button-secondary" onClick={() => void leaveBeforeAnswer()}>
                移動する
              </button>
            </div>
          </div>
        </Sheet>
      )}
    </main>
  );
}

function MyInsight({ proposal, full = false }: { proposal: Proposal; full?: boolean }) {
  const { insight } = proposal;
  return (
    <section aria-label="あなたの気づき">
      <p className="who">あなたの気づき</p>
      <div className="card mine">
        <p className="mine-book">
          {insight.book_title}
          {insight.page ? `　P.${insight.page}` : ""}
        </p>
        {insight.quote && (
          <p className="quote">
            <QuoteIcon />
            {insight.quote}
          </p>
        )}
        <p className={`mine-body${full ? "" : " clamp-2"}`}>{insight.body}</p>
      </div>
    </section>
  );
}

function Question({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <section aria-label="AIからの深掘り">
      <p className="who">AIからの深掘り</p>
      <div className="deep">
        <p>{text}</p>
      </div>
    </section>
  );
}

function MyAnswer({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <section aria-label="あなたの回答">
      <p className="who">あなたの回答</p>
      <div className="card answer-box">{text}</div>
    </section>
  );
}

function Plans({ plans }: { plans: { text: string }[] | null }) {
  if (!plans) return null;
  return (
    <section aria-label="次の一歩">
      <p className="who">次の一歩</p>
      <ol className="plans">
        {plans.map((plan, i) => (
          <li key={i}>{plan.text}</li>
        ))}
      </ol>
    </section>
  );
}

function CenterState({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <div className="state-box ai-center">
      <h2 className="state-title">{title}</h2>
      <p>{text}</p>
      {children}
    </div>
  );
}

function BackToInsight({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="button button-primary" onClick={onClick}>
      気づきに戻る
    </button>
  );
}
