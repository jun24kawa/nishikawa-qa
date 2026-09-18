-- 質問応答システム D1 スキーマ
-- 適用: wrangler d1 execute nishikawa-qa-db --file=schema/schema.sql

-- edusalon生の許可リスト（西川さんから渡されるエクセルを取り込む）
CREATE TABLE IF NOT EXISTS allowlist (
  email      TEXT PRIMARY KEY,   -- 小文字・前後空白除去済みで保存
  name       TEXT,
  created_at TEXT NOT NULL
);

-- メール確認〜質問応答の1回の利用セッション
CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,   -- ブラウザ側が持つセッションID（UUID）
  email         TEXT NOT NULL,      -- 入力されたメールアドレス（許可リストに無くても記録する）
  token         TEXT NOT NULL,      -- 確認メールのリンクに埋め込む秘密トークン（UUID）
  is_member     INTEGER NOT NULL,   -- 1=許可リストに一致 / 0=不一致（実際にはメールを送らない）
  status        TEXT NOT NULL,      -- pending / confirmed / denied / expired / ended
  created_at    TEXT NOT NULL,
  confirm_expires_at TEXT NOT NULL, -- 「はい/いいえ」の確認待ち期限（30分程度）
  confirmed_at  TEXT,
  session_expires_at TEXT,          -- 確認後の利用期限（24時間程度）
  last_used_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);

-- 1件の質問とその処理状況（Renderの無料プランは起き上がるまで最大1分ほどかかることがあるため、
-- Cloudflare側は結果を待たずに一旦返し、フロントがポーリングで結果を取りに来る）
CREATE TABLE IF NOT EXISTS asks (
  id          TEXT PRIMARY KEY,   -- UUID
  session_id  TEXT NOT NULL,
  question    TEXT NOT NULL,
  status      TEXT NOT NULL,      -- processing / done / error
  answer      TEXT,
  error       TEXT,
  created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asks_session ON asks(session_id);

-- 本の公開サイト（jun24kawa.github.io、別ドメインの静的サイト）の「ご意見箱」投稿。
-- 名前・メールアドレスは受け取らない設計。2026-09-19、Cloudflareダッシュボードのコンソールで作成済み。
CREATE TABLE IF NOT EXISTS opinions (
  id         TEXT PRIMARY KEY,
  message    TEXT NOT NULL,
  ip         TEXT,             -- 簡易レート制限用
  created_at TEXT NOT NULL
);
