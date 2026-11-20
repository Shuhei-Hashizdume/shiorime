// 本ごとの気づき一覧（screens.md 5.、api.md 7-4）。

import { ArrowLeft, Plus } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import { insightsApi, type InsightCard, type InsightGroupDetail } from "../api/insights";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { InfoBanner } from "../components/Feedback";
import { InsightCardView } from "../components/InsightCardView";
import { MoreStatus } from "../components/MoreStatus";
import { useInfiniteList } from "../lib/useInfiniteList";

type GroupState = { kind: "loading" } | { kind: "ready"; group: InsightGroupDetail } | { kind: "not_found" } | { kind: "error" };

export default function BookInsights() {
  const { groupId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  const [group, setGroup] = useState<GroupState>({ kind: "loading" });

  // 404 のときは本の情報の方で「見つかりませんでした」を出すので、カードの失敗としては扱わない
  const onCardsError = useCallback(
    (error: unknown) => onUnauthorized(error) || (error instanceof ApiError && error.status === 404),
    [onUnauthorized],
  );
  const fetchCards = useCallback((cursor: string | null) => insightsApi.cards(groupId, cursor), [groupId]);
  const cards = useInfiniteList<InsightCard>(fetchCards, onCardsError);

  const loadGroup = useCallback(async () => {
    setGroup({ kind: "loading" });
    try {
      setGroup({ kind: "ready", group: await insightsApi.group(groupId) });
    } catch (error) {
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) setGroup({ kind: "not_found" });
      else setGroup({ kind: "error" });
    }
  }, [groupId, onUnauthorized]);

  useEffect(() => {
    void loadGroup();
  }, [loadGroup]);

  function goBack() {
    if (location.key !== "default") navigate(-1);
    else navigate("/insights");
  }

  function retry() {
    void loadGroup();
    void cards.reload();
  }

  const loading = group.kind === "loading" || (group.kind === "ready" && cards.state === "loading");
  const failed = group.kind === "error" || (group.kind === "ready" && cards.state === "error");
  const writeUrl = `/insights/new?book=${groupId}`;

  return (
    <main className="page page-with-tabs">
      <div className="topbar">
        <button type="button" className="icon-button" aria-label="戻る" onClick={goBack}>
          <ArrowLeft size={24} aria-hidden="true" />
        </button>
      </div>

      {group.kind === "not_found" && (
        <div className="state-box">
          <h1 className="state-title">この本は見つかりませんでした</h1>
          <Link to="/insights" className="button button-secondary">
            気づき一覧へ戻る
          </Link>
        </div>
      )}

      {failed && (
        <div className="state-box">
          <p>気づきを読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={retry}>
            もう一度読み込む
          </button>
        </div>
      )}

      {loading && (
        <div aria-busy="true" aria-label="読み込み中">
          <div className="group-head">
            <div className="skeleton group-head-cover" />
            <div className="group-text">
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line short" />
            </div>
          </div>
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="skeleton skeleton-card" />
          ))}
        </div>
      )}

      {group.kind === "ready" && !failed && !loading && (
        <>
          <div className="group-head">
            <BookCover url={group.group.cover_url} className={`group-head-cover${group.group.deleted ? " faded" : ""}`} />
            <div className="group-text">
              <h1 className="group-head-title">{group.group.title}</h1>
              {group.group.author && <p className="group-meta">{group.group.author}</p>}
              <p className="group-meta">気づき {group.group.insight_count}件</p>
              {group.group.deleted && <span className="deleted-badge">本棚から削除済み</span>}
            </div>
          </div>

          {group.group.deleted && <InfoBanner>この本は本棚から削除されているため、新しい気づきは書けません。</InfoBanner>}

          {cards.items.length === 0 && !group.group.deleted && (
            <div className="empty">
              <h2>まだ気づきがありません</h2>
              <p>心に残った一文や、読んで考えたことを書き留めてみましょう。</p>
              <Link to={writeUrl} className="button button-primary">
                <Plus size={20} weight="bold" aria-hidden="true" />
                気づきを書く
              </Link>
            </div>
          )}

          {cards.items.length > 0 && (
            <>
              <ul className="insight-list">
                {cards.items.map((insight) => (
                  <li key={insight.id}>
                    <InsightCardView insight={insight} />
                  </li>
                ))}
              </ul>
              <div ref={cards.sentinel} />
              <MoreStatus state={cards.moreState} onRetry={cards.retryMore} />
              {!group.group.deleted && (
                <Link to={writeUrl} className="fab">
                  <Plus size={20} weight="bold" aria-hidden="true" />
                  気づきを書く
                </Link>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
