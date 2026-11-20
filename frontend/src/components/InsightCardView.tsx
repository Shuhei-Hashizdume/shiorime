// 本ごとの気づき一覧の、気づき1件のカード（screens.md 5.）。

import { Link } from "react-router";

import type { InsightCard } from "../api/insights";
import { formatDay } from "../lib/date";
import { QuoteIcon } from "./QuoteIcon";
import { SproutIcon } from "./SproutIcon";

export function InsightCardView({ insight }: { insight: InsightCard }) {
  return (
    <Link to={`/insights/${insight.id}`} className="insight-card">
      <span className="insight-card-meta">
        <span>{insight.page ? `P.${insight.page}` : "ページなし"}</span>
        <span>{formatDay(insight.created_at)}</span>
      </span>
      {insight.quote && (
        <span className="quote quote-clamp">
          <QuoteIcon />
          {insight.quote}
        </span>
      )}
      <span className="insight-card-body">{insight.body}</span>
      {insight.next_step_count > 0 && (
        <span className="next-step-count">
          <SproutIcon />
          次の一歩 {insight.next_step_count}件
        </span>
      )}
    </Link>
  );
}
