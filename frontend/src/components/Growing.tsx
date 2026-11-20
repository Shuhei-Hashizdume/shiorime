// AI を待つ間の、芽がゆっくり育つ動き（screens.md 8.、visual.md 9章）。
// 「視差効果を減らす」設定の人には動かさない（CSS で止める）。

import { SproutIcon } from "./SproutIcon";

/** AI提案の画面の、大きな待ちの表示 */
export function Waiting({ title, children }: { title: string; children: string }) {
  return (
    <div className="waiting" role="status">
      <span className="growing">
        <SproutIcon size={44} />
      </span>
      <b>{title}</b>
      <span className="waiting-note">{children}</span>
    </div>
  );
}

/** 気づきの詳細の、次の一歩の中の小さな作成中の表示 */
export function Making({ title, children }: { title: string; children?: string }) {
  return (
    <div className="making" role="status">
      <span className="growing">
        <SproutIcon size={30} />
      </span>
      <div>
        <b>{title}</b>
        {children && <span className="making-note">{children}</span>}
      </div>
    </div>
  );
}
