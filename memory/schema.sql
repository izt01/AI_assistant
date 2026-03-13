-- ══════════════════════════════════════════════════════════════
--  記憶テーブル群スキーマ  v2
--  proposal_history → lu_proposals に統合済み
-- ══════════════════════════════════════════════════════════════

-- ユーザープロファイル（会話から学習したライフスタイル・基本情報）
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id     TEXT PRIMARY KEY,
    name        TEXT,
    area        TEXT,
    occupation  TEXT,
    family      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 好み・嗜好（AIごとに蓄積）
CREATE TABLE IF NOT EXISTS user_preferences (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  FLOAT DEFAULT 1.0,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, ai_type, key)
);

-- 提案履歴（後方互換：lu_proposalsと並行運用。新規はlu_proposalsを使用）
CREATE TABLE IF NOT EXISTS proposal_history (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    proposal    TEXT NOT NULL,
    outcome     TEXT DEFAULT 'unknown',
    reason      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 会話セッション（記憶学習のソース）
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,
    messages    JSONB DEFAULT '[]',
    summary     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_preferences_user  ON user_preferences(user_id, ai_type);
CREATE INDEX IF NOT EXISTS idx_proposals_user    ON proposal_history(user_id, ai_type);
CREATE INDEX IF NOT EXISTS idx_sessions_user     ON chat_sessions(user_id, ai_type);
