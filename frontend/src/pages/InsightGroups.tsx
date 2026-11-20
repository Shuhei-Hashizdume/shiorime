// 気づき一覧（screens.md 4.、api.md 7-4）。

import { ArrowsDownUp, Check } from "@phosphor-icons/react";
import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { insightsApi, SORT_OPTIONS, type GroupSort, type InsightGroup } from "../api/insights";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { Mark } from "../components/Logo";
import { MoreStatus } from "../components/MoreStatus";
import { Sheet } from "../components/Sheet";
import { formatDay } from "../lib/date";
import { useInfiniteList } from "../lib/useInfiniteList";

function parseSort(value: string | null): GroupSort {
  // 知らない値が書かれていたら、最近書いた順として表示する
  return value === "many" || value === "few" ? value : "recent";
}

export default function InsightGroups() {
  const [searchParams, setSearchParams] = useSearchParams();
  // 選んだ並び順は URL に入れる。本ごとの気づき一覧から戻ったとき、同じ並び順のまま戻るため
  const sort = parseSort(searchParams.get("sort"));
  const onUnauthorized = useUnauthorized();
  const [sortOpen, setSortOpen] = useState(false);

  const fetchPage = useCallback((cursor: string | null) => insightsApi.groups(sort, cursor), [sort]);
  const { items, state, moreState, reload, retryMore, sentinel } = useInfiniteList<InsightGroup>(fetchPage, onUnauthorized);

  function selectSort(next: GroupSort) {
    setSortOpen(false);
    setSearchParams(next === "recent" ? {} : { sort: next }, { replace: true });
  }

  const label = SORT_OPTIONS.find((o) => o.key === sort)?.label;

  return (
    <main className="page page-with-tabs">
      <h1 className="title page-title">気づき一覧</h1>

      {!(state === "ready" && items.length === 0) && (
        <div className="sort-row">
          <span className="sort-label">並び順：{label}</span>
          <button type="button" className="icon-button" aria-label="並び替え" onClick={() => setSortOpen(true)}>
            <ArrowsDownUp size={22} aria-hidden="true" />
          </button>
        </div>
      )}

      {state === "loading" && (
        <ul className="group-list" aria-busy="true" aria-label="読み込み中">
          {Array.from({ length: 4 }, (_, i) => (
            <li key={i} className="group-card">
              <div className="skeleton group-cover" />
              <div className="group-text">
                <div className="skeleton skeleton-line" />
                <div className="skeleton skeleton-line short" />
              </div>
            </li>
          ))}
        </ul>
      )}

      {state === "error" && (
        <div className="state-box">
          <p>気づき一覧を読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={() => void reload()}>
            もう一度読み込む
          </button>
        </div>
      )}

      {state === "ready" && items.length === 0 && (
        <div className="empty">
          <Mark size={96} />
          <h2>まだ本がありません</h2>
          <p>本棚に本を追加すると、ここから気づきを書けるようになります。</p>
          <Link to="/books/add" className="button button-primary">
            本を追加する
          </Link>
        </div>
      )}

      {state === "ready" && items.length > 0 && (
        <>
          <ul className="group-list">
            {items.map((group) => (
              <li key={group.id}>
                <Link to={`/insight-groups/${group.id}`} className={`group-card${group.deleted ? " deleted" : ""}`}>
                  <BookCover url={group.cover_url} className="group-cover" />
                  <span className="group-text">
                    <span className="group-title">{group.title}</span>
                    <span className="group-meta">気づき {group.insight_count}件</span>
                    {group.last_written_at && (
                      <span className="group-meta">最後に書いた日：{formatDay(group.last_written_at)}</span>
                    )}
                    {group.deleted && <span className="deleted-badge">本棚から削除済み</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div ref={sentinel} />
          <MoreStatus state={moreState} onRetry={retryMore} />
        </>
      )}

      {sortOpen && (
        <Sheet title="並び替え" onClose={() => setSortOpen(false)} variant="auto">
          <div className="menu-list" role="radiogroup" aria-label="並び順">
            {SORT_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={sort === option.key}
                className="sort-option"
                onClick={() => selectSort(option.key)}
              >
                <span>
                  <span className="sort-option-label">{option.label}</span>
                  <span className="sort-option-description">{option.description}</span>
                </span>
                {sort === option.key && <Check size={20} weight="bold" aria-hidden="true" />}
              </button>
            ))}
            <button type="button" className="menu-item" onClick={() => setSortOpen(false)}>
              キャンセル
            </button>
          </div>
        </Sheet>
      )}
    </main>
  );
}
