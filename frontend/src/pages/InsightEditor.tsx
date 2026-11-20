// 気づきの作成・編集（screens.md 7.、api.md 7-5）。長い文を書くため、共通メニューは出さない。

import { X } from "@phosphor-icons/react";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import { BODY_MAX, insightsApi, PAGE_MAX, PAGE_MIN, QUOTE_MAX } from "../api/insights";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { ErrorBanner, FieldErrorText, InfoBanner } from "../components/Feedback";
import { QuoteIcon } from "../components/QuoteIcon";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { countChars, normalize } from "../lib/text";

type Book = { id: string; title: string; author: string | null; cover_url: string | null };
type Values = { quote: string; page: string; body: string };
type Errors = { quote?: string; page?: string; body?: string };

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; book: Book; initial: Values; hasNextSteps: boolean }
  | { kind: "not_found" }
  | { kind: "book_deleted" }
  | { kind: "error" };

const EMPTY: Values = { quote: "", page: "", body: "" };
const formatNumber = (n: number) => n.toLocaleString("ja-JP");

function validate(values: Values): Errors {
  const errors: Errors = {};
  const body = normalize(values.body);
  const quote = normalize(values.quote);
  const page = values.page.trim();
  if (body === "") errors.body = "気づきを入力してください";
  else if (countChars(body) > BODY_MAX)
    errors.body = `気づきは${formatNumber(BODY_MAX)}文字以内で入力してください（あと${countChars(body) - BODY_MAX}文字減らしてください）`;
  if (countChars(quote) > QUOTE_MAX)
    errors.quote = `引用は${QUOTE_MAX}文字以内で入力してください（あと${countChars(quote) - QUOTE_MAX}文字減らしてください）`;
  if (page !== "" && !(/^\d+$/.test(page) && Number(page) >= PAGE_MIN && Number(page) <= PAGE_MAX))
    errors.page = `${PAGE_MIN}〜${PAGE_MAX}の数字で入力してください`;
  return errors;
}

function errorsFromServer(error: ApiError): Errors | null {
  if (error.code !== "VALIDATION_ERROR") return null;
  const errors: Errors = {};
  for (const f of error.fields) {
    if (f.field === "body") errors.body = f.reason === "required" ? "気づきを入力してください" : `気づきは${formatNumber(BODY_MAX)}文字以内で入力してください`;
    if (f.field === "quote") errors.quote = `引用は${QUOTE_MAX}文字以内で入力してください`;
    if (f.field === "page") errors.page = `${PAGE_MIN}〜${PAGE_MAX}の数字で入力してください`;
  }
  return errors;
}

export default function InsightEditor() {
  const { insightId } = useParams();
  const [searchParams] = useSearchParams();
  const bookId = searchParams.get("book");
  const isEdit = Boolean(insightId);
  const navigate = useNavigate();
  const location = useLocation();
  const fromDetail = (location.state as { fromDetail?: boolean } | null)?.fromDetail === true;
  const onUnauthorized = useUnauthorized();
  const showToast = useToast();

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [values, setValues] = useState<Values>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [bookGone, setBookGone] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const saved = useRef(false);
  const quoteId = useId();
  const pageId = useId();
  const bodyId = useId();

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      if (isEdit && insightId) {
        const insight = await insightsApi.get(insightId);
        const initial = { quote: insight.quote ?? "", page: insight.page ? String(insight.page) : "", body: insight.body };
        setValues(initial);
        setState({ kind: "ready", book: insight.book, initial, hasNextSteps: insight.latest_proposal !== null });
      } else {
        if (!bookId) return setState({ kind: "not_found" });
        // 「見つからない」と「削除済み」を見分けるため、本ではなく気づきのまとまりを取る（screens.md 7.）
        const group = await insightsApi.group(bookId);
        if (group.deleted) return setState({ kind: "book_deleted" });
        setValues(EMPTY);
        setState({ kind: "ready", book: group, initial: EMPTY, hasNextSteps: false });
      }
    } catch (error) {
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) setState({ kind: "not_found" });
      else setState({ kind: "error" });
    }
  }, [bookId, insightId, isEdit, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  // 新しく書くときは、気づきの欄に自動でカーソルを入れる
  useEffect(() => {
    if (state.kind === "ready" && !isEdit) bodyRef.current?.focus({ preventScroll: true });
  }, [state.kind, isEdit]);

  const dirty =
    state.kind === "ready" &&
    (values.quote !== state.initial.quote || values.page !== state.initial.page || values.body !== state.initial.body);

  // タブを閉じる・再読み込みのときは、ブラウザ標準の確認を出す
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      if (saved.current) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  function leave() {
    // 開いた元の画面へ戻る。URL を直接開いたときは、本ごとの気づき一覧か気づきの詳細へ
    if (location.key !== "default") navigate(-1);
    else if (isEdit && insightId) navigate(`/insights/${insightId}`, { replace: true });
    else if (state.kind === "ready") navigate(`/insight-groups/${state.book.id}`, { replace: true });
    else navigate("/insights", { replace: true });
  }

  function handleClose() {
    if (dirty && !bookGone) setConfirmClose(true);
    else if (bookGone && state.kind === "ready") navigate(`/insight-groups/${state.book.id}`, { replace: true });
    else leave();
  }

  async function handleSave(event?: FormEvent) {
    event?.preventDefault();
    if (saving || bookGone || state.kind !== "ready") return;
    const found = validate(values);
    setErrors(found);
    setBanner(null);
    if (Object.keys(found).length > 0) {
      if (found.body) bodyRef.current?.focus();
      return;
    }

    const input = {
      quote: normalize(values.quote) || null,
      page: values.page.trim() ? Number(values.page.trim()) : null,
      body: normalize(values.body),
    };
    setSaving(true);
    try {
      if (isEdit && insightId) {
        await insightsApi.update(insightId, input);
        saved.current = true;
        showToast("気づきを変更しました");
        // 詳細から開いたときは戻る（同じ気づきの詳細が履歴に2回続かないように）
        if (fromDetail) navigate(-1);
        else navigate(`/insights/${insightId}`, { replace: true });
      } else {
        const { id } = await insightsApi.create({ ...input, book_id: state.book.id });
        saved.current = true;
        showToast("気づきを保存しました");
        // 作成画面を気づきの詳細で置き換える
        navigate(`/insights/${id}`, { replace: true, state: { justCreated: true } });
      }
    } catch (error) {
      setSaving(false);
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && error.code === "BOOK_NOT_FOUND") {
        setBookGone(true);
        return;
      }
      if (error instanceof ApiError && error.code === "INSIGHT_NOT_FOUND") {
        setState({ kind: "not_found" });
        return;
      }
      const fieldErrors = error instanceof ApiError ? errorsFromServer(error) : null;
      if (fieldErrors) setErrors(fieldErrors);
      else setBanner("保存できませんでした。時間をおいてもう一度お試しください。");
    }
  }

  const quoteCount = countChars(normalize(values.quote));
  const bodyCount = countChars(normalize(values.body));
  const title = isEdit ? "気づきを編集" : "気づきを書く";

  return (
    <main className="page editor">
      <form onSubmit={handleSave} noValidate>
        <div className="editor-bar">
          <button type="button" className="icon-button" aria-label="閉じる" onClick={handleClose}>
            <X size={24} aria-hidden="true" />
          </button>
          <h1 className="topbar-title">{title}</h1>
          {state.kind === "ready" && (
            <button type="submit" className="button button-primary editor-save" disabled={saving || bookGone}>
              保存
            </button>
          )}
        </div>

        {state.kind === "loading" && (
          <div aria-busy="true" aria-label="読み込み中">
            <div className="skeleton skeleton-card" />
            <div className="skeleton skeleton-card tall" />
          </div>
        )}

        {state.kind === "not_found" && (
          <div className="state-box">
            <p className="state-title">{isEdit ? "この気づきは見つかりませんでした" : "この本は見つかりませんでした"}</p>
            <Link to="/insights" className="button button-secondary">
              気づき一覧へ戻る
            </Link>
          </div>
        )}

        {state.kind === "book_deleted" && (
          <div className="state-box">
            <p>この本は本棚から削除されているため、新しい気づきは書けません。</p>
            <button type="button" className="button button-secondary" onClick={leave}>
              戻る
            </button>
          </div>
        )}

        {state.kind === "error" && (
          <div className="state-box">
            <p>読み込めませんでした。時間をおいてもう一度お試しください。</p>
            <button type="button" className="button button-secondary" onClick={() => void load()}>
              もう一度読み込む
            </button>
          </div>
        )}

        {state.kind === "ready" && (
          <>
            {bookGone && (
              <ErrorBanner>
                この本は本棚から削除されたため、気づきを保存できませんでした。書いた内容は残っています。必要な部分はコピーしてください。
              </ErrorBanner>
            )}
            {banner && <ErrorBanner>{banner}</ErrorBanner>}

            <div className="insight-book">
              <BookCover url={state.book.cover_url} className="insight-book-cover" />
              <div>
                <p className="insight-book-title">{state.book.title}</p>
                {state.book.author && <p className="group-meta">{state.book.author}</p>}
              </div>
            </div>

            {isEdit && state.hasNextSteps && <InfoBanner>編集しても、次の一歩（AI提案）はそのまま残ります。</InfoBanner>}

            <div className="field-group">
              <div className="label-row">
                <label className="label" htmlFor={quoteId}>
                  引用 <span className="optional">任意</span>
                </label>
                <span className={`counter${quoteCount > QUOTE_MAX ? " over" : ""}`}>
                  {formatNumber(quoteCount)} / {QUOTE_MAX}
                </span>
              </div>
              <div className={`quote-input${errors.quote ? " invalid" : ""}`}>
                <QuoteIcon />
                <textarea
                  id={quoteId}
                  rows={2}
                  placeholder="心に残った一文"
                  value={values.quote}
                  onChange={(e) => setValues({ ...values, quote: e.target.value })}
                  aria-invalid={errors.quote ? true : undefined}
                  aria-describedby={errors.quote ? `${quoteId}-error` : undefined}
                />
              </div>
              {errors.quote && <FieldErrorText id={`${quoteId}-error`}>{errors.quote}</FieldErrorText>}
            </div>

            <div className="field-group">
              <label className="label" htmlFor={pageId}>
                ページ <span className="optional">任意</span>
              </label>
              <div className={`input-wrap page-input${errors.page ? " invalid" : ""}`}>
                <span className="page-prefix" aria-hidden="true">
                  P.
                </span>
                <input
                  id={pageId}
                  className="input"
                  inputMode="numeric"
                  value={values.page}
                  onChange={(e) => setValues({ ...values, page: e.target.value })}
                  aria-invalid={errors.page ? true : undefined}
                  aria-describedby={errors.page ? `${pageId}-error` : undefined}
                />
              </div>
              {errors.page && <FieldErrorText id={`${pageId}-error`}>{errors.page}</FieldErrorText>}
            </div>

            <div className="field-group">
              <div className="label-row">
                <label className="label" htmlFor={bodyId}>
                  気づき <span className="required-mark">必須</span>
                </label>
                <span className={`counter${bodyCount > BODY_MAX ? " over" : ""}`}>
                  {formatNumber(bodyCount)} / {formatNumber(BODY_MAX)}
                </span>
              </div>
              <div className={`input-wrap body-input${errors.body ? " invalid" : ""}`}>
                <textarea
                  ref={bodyRef}
                  id={bodyId}
                  className="input"
                  rows={10}
                  placeholder="読んで考えたこと、自分の経験と結びついたことを書きましょう。"
                  value={values.body}
                  onChange={(e) => setValues({ ...values, body: e.target.value })}
                  aria-invalid={errors.body ? true : undefined}
                  aria-describedby={errors.body ? `${bodyId}-error` : `${bodyId}-note`}
                />
              </div>
              {errors.body && <FieldErrorText id={`${bodyId}-error`}>{errors.body}</FieldErrorText>}
              <p className="hint" id={`${bodyId}-note`}>
                入力内容は、AI提案を受けるときにAI（OpenAI）に送信されます。個人情報は書かないでください。
              </p>
            </div>
          </>
        )}
      </form>

      {confirmClose && (
        <Sheet title="書きかけの気づきを破棄しますか？" onClose={() => setConfirmClose(false)} variant="auto" showHeader={false}>
          <div className="confirm">
            <p className="confirm-title">書きかけの気づきを破棄しますか？</p>
            <p className="confirm-text">保存していない内容は失われます。</p>
            <div className="sheet-actions">
              <button type="button" className="button button-primary" onClick={() => setConfirmClose(false)}>
                書き続ける
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => {
                  saved.current = true;
                  setConfirmClose(false);
                  leave();
                }}
              >
                破棄して閉じる
              </button>
            </div>
          </div>
        </Sheet>
      )}
    </main>
  );
}
