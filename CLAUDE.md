# SHIORIME（book-app）

読書の気づきを記録し、AI と一緒に「次の一歩」を考える Web アプリ。バックエンドエンジニア志望のポートフォリオ。

## まず読むもの

作業を始める前に、必ず [docs/design/progress.md](docs/design/progress.md) を読み、今どこまで進んでいて次に何をするかを確かめる。

設計の文書（どれも日本語）。食い違ったときは、上にあるものほど優先する。

| 文書 | 中身 |
| --- | --- |
| [docs/requirements.md](docs/requirements.md) | 要件定義書。アプリの決まりの元 |
| [docs/design/api.md](docs/design/api.md) | API の形（URL・入出力・エラー・ステータスコード） |
| [docs/design/database.md](docs/design/database.md) | テーブル・列・制約・インデックス |
| [docs/design/screens.md](docs/design/screens.md) | 画面と、画面に出す文 |
| [docs/design/visual.md](docs/design/visual.md) | 見た目（色・文字・部品） |
| [docs/design/notes.md](docs/design/notes.md) | 技術的な決定（競合対策・認証・インフラ・ログ・.env など） |

- 設計の文書にないことを決めたら、実装と一緒にその文書も直す。文書と実装を食い違わせない。
- 設計を変える必要があると気づいたら、勝手に変えず、理由と案を出して確かめる。

## 技術と版

- バックエンド：Python 3.14、FastAPI、SQLAlchemy、Alembic、Pydantic、pydantic-settings
- データベース：PostgreSQL 18（主キーは `uuidv7()`）
- 画面：React 19、Vite、Node.js 24（24.22.1 以上。開発とビルドのときだけ使う）
- AI：OpenAI（Structured Outputs）。本の検索：Google Books API
- 構成：Docker Compose で Caddy・FastAPI・worker（後片付け）・PostgreSQL の4コンテナ。本番は AWS EC2

## 作る順番と進め方

- 機能ごとに「バックエンド（API＋テスト）→ 画面」の順で作り、1つの機能を本当に動くところまで作り切ってから次へ進む。
- 機能の順番：
  0. 土台（Docker Compose・FastAPI・PostgreSQL・Alembic・React の空の画面）
  1. 新規登録・ログイン・ログアウト・`GET /me`
  2. 本棚（本の検索・追加・一覧・詳細・変更・削除）
  3. 気づき（気づき一覧・作成・詳細・変更・削除）
  4. AI提案
  5. プロフィール（属性・パスワードの変更・退会）・後片付けの worker
- 画面は api.md の API の形どおりに作り、本物の API につないで確かめる（偽のデータで先に作らない）。
- 画面の実装は AI が行い、人がレビューする。バックエンドは人が設計を考え、AI と一緒に実装する。

## ブランチ・コミット・プルリクエスト

- main に直接コミットしない。機能ごとにブランチを切り（例：`feature/auth`）、プルリクエストで main に入れる。
- コミットのメッセージは日本語で、何をしたかを1行目に書く（例：`feat: 新規登録の API を追加`）。
- プルリクエストには、何を作ったか・どう確かめたか・設計の文書のどこに対応するかを書く。

## コードの決まり

- 認可：データを返す・変える処理は、必ず「自分のものか」を確かめる。他人のものは 404 を返す（403 は使わない）。
- エラーは api.md 1-3 の形（`{"error": {"code", "message", "fields", "details"}}`）にそろえる。画面に出す文は画面側が `code` を見て決める。
- 文字数は見た目の1文字（書記素クラスタ）で数え、NFC に正規化する（api.md 5-1）。数える関数は1つにまとめる。
- 同時に押された・連打された場合に、回数や状態が二重に変わらないよう、確認と変更はデータベースへの1回の命令（条件付きの UPDATE・UPSERT・一意制約）で行う（notes.md 2章）。
- 日時は UTC で扱い、「今日」の判定（AI の回数など）だけ日本時間にする。

## テスト

- バックエンドの API は、機能ごとに pytest でテストを書く。正常な場合だけでなく、他人のデータ・入力の誤り・状態が合わない・同時に押された場合も書く（各文書の「テスト」の項目）。
- OpenAI と Google Books は、テストでは偽物に置き換える。

## 秘密の値とログ

- 秘密の値（DB のパスワード・JWT の鍵・API キー）は `.env` に書き、Git に入れない。必要な名前は `.env.example` に書く。
- ログに、パスワード・Cookie・JWT・API キー・気づきの本文や引用・AI への回答と AI の返事・メールアドレス・接続元の IP を出さない（notes.md 5章）。

## 依存する部品

- 部品の版はロックファイルで固定する（npm は `package-lock.json` と `npm ci`、npm の `ignore-scripts=true`）。
- 部品はむやみに増やさない。足すときは理由を説明してから足す。
