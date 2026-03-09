-- ユーザープロファイル（ライフスタイル・基本情報）
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id     TEXT PRIMARY KEY,
    name        TEXT,
    area        TEXT,          -- 居住エリア
    occupation  TEXT,          -- 職業
    family      TEXT,          -- 家族構成
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 好み・嗜好（AIごとに蓄積）
CREATE TABLE IF NOT EXISTS user_preferences (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,  -- recipe / travel / shopping / diy / appliance / health
    key         TEXT NOT NULL,  -- spice_level / budget_feel / style など
    value       TEXT NOT NULL,
    confidence  FLOAT DEFAULT 1.0,  -- 確信度（言及回数で上がる）
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, ai_type, key)
);

-- 提案履歴
CREATE TABLE IF NOT EXISTS proposal_history (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    proposal    TEXT NOT NULL,   -- 提案した内容（JSON）
    outcome     TEXT DEFAULT 'unknown',  -- accepted / rejected / unknown
    reason      TEXT,            -- 却下理由など
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 会話セッション（記憶学習のソース）
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ai_type     TEXT NOT NULL,
    messages    JSONB DEFAULT '[]',
    summary     TEXT,            -- AIが要約した会話の要点
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_preferences_user  ON user_preferences(user_id, ai_type);
CREATE INDEX IF NOT EXISTS idx_proposals_user     ON proposal_history(user_id, ai_type);
CREATE INDEX IF NOT EXISTS idx_sessions_user      ON chat_sessions(user_id, ai_type);
