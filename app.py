"""
Lumina AI  ─  統合バックエンドサーバー（Railway対応版）
OpenAI GPT-4o × 記憶成長型AIエージェント

起動: python app.py
Railway: Procfile の `web: python app.py` で自動起動
"""
import json, os, sys, uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import bcrypt, jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()  # ローカル開発時は .env を読む（Railwayでは環境変数が直接注入される）

# ── エージェント群
from agents import route, AGENT_MAP
from memory import init_db, save_feedback

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# ══════════════════════════════════════════════════════════════
#  設定
# ══════════════════════════════════════════════════════════════
SECRET_KEY      = os.getenv("SECRET_KEY", "lumina-dev-secret")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
PORT            = int(os.getenv("PORT", 5001))  # Railway は PORT を自動注入


# ══════════════════════════════════════════════════════════════
#  DB 接続（Railway の DATABASE_URL に対応）
# ══════════════════════════════════════════════════════════════
def _make_conn():
    """
    Railway環境: DATABASE_URL が自動注入される
    ローカル環境: DB_HOST / DB_PORT 等の個別変数を使う
    """
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        # Railway / Heroku 形式: postgres://user:pass@host:port/dbname
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor,
                                sslmode="require")
    # ローカル用
    return psycopg2.connect(
        host     = os.getenv("DB_HOST", "localhost"),
        port     = int(os.getenv("DB_PORT", 5432)),
        dbname   = os.getenv("DB_NAME", "ai_suite"),
        user     = os.getenv("DB_USER", "ai_suite_user"),
        password = os.getenv("DB_PASSWORD", "ai_suite_pass"),
        cursor_factory=RealDictCursor,
    )

def get_db():
    if "db" not in g:
        g.db = _make_conn()
        g.db.autocommit = False
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        try: db.close()
        except Exception: pass

def db_exec(sql, params=None, fetch="none"):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        if fetch == "one": return cur.fetchone()
        if fetch == "all": return cur.fetchall()
        conn.commit()
        return None

def db_init_lumina_tables():
    """Lumina AI 専用テーブルを初期化（起動時に自動実行）"""
    sql = """
    CREATE TABLE IF NOT EXISTS lu_users (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        nickname        VARCHAR(50)  NOT NULL,
        email           VARCHAR(255) NOT NULL UNIQUE,
        password_hash   TEXT         NOT NULL,
        plan            VARCHAR(20)  NOT NULL DEFAULT 'free',
        usage_count     INT          NOT NULL DEFAULT 0,
        is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
        is_admin        BOOLEAN      NOT NULL DEFAULT FALSE,
        terms_agreed_at TIMESTAMP,
        device_info     JSONB,
        created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_profiles (
        user_id            UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        area               VARCHAR(100),
        transport_modes    TEXT[]    DEFAULT '{}',
        household_size     INT,
        has_children       BOOLEAN,
        has_pets           BOOLEAN,
        monthly_budget     INT,
        outing_budget      INT,
        weekday_style      TEXT,
        weekend_style      TEXT,
        favorite_services  TEXT[]    DEFAULT '{}',
        interests          TEXT[]    DEFAULT '{}',
        updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
    );
    -- interests カラムが既存DBに存在しない場合に備えてマイグレーション
    ALTER TABLE lu_profiles ADD COLUMN IF NOT EXISTS interests TEXT[] DEFAULT '{}';
    CREATE TABLE IF NOT EXISTS lu_pref_food (
        user_id              UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        liked_cuisines       TEXT[]  DEFAULT '{}',
        disliked_cuisines    TEXT[]  DEFAULT '{}',
        liked_ingredients    TEXT[]  DEFAULT '{}',
        disliked_ingredients TEXT[]  DEFAULT '{}',
        allergies            TEXT[]  DEFAULT '{}',
        volume_pref          VARCHAR(20) DEFAULT 'normal',
        health_conscious     INT     DEFAULT 3,
        cooking_freq         VARCHAR(20) DEFAULT 'sometimes',
        spice_level          INT     DEFAULT 2,
        updated_at           TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_pref_shopping (
        user_id               UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        liked_brands          TEXT[]  DEFAULT '{}',
        disliked_brands       TEXT[]  DEFAULT '{}',
        priority_price        INT     DEFAULT 3,
        priority_practicality INT     DEFAULT 3,
        priority_novelty      INT     DEFAULT 3,
        priority_reliability  INT     DEFAULT 3,
        updated_at            TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_pref_travel (
        user_id            UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        travel_styles      TEXT[]  DEFAULT '{}',
        budget_range       VARCHAR(20),
        max_travel_hours   INT,
        priority_hotel     INT DEFAULT 3,
        priority_onsen     INT DEFAULT 3,
        priority_scenery   INT DEFAULT 3,
        priority_station   INT DEFAULT 3,
        priority_breakfast INT DEFAULT 3,
        updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_pref_restaurant (
        user_id           UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        liked_genres      TEXT[]  DEFAULT '{}',
        price_range       VARCHAR(20),
        smoking_ok        BOOLEAN DEFAULT FALSE,
        private_room_pref BOOLEAN DEFAULT FALSE,
        noise_pref        VARCHAR(20) DEFAULT 'any',
        solo_or_group     VARCHAR(20) DEFAULT 'any',
        updated_at        TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_pref_health (
        user_id             UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        health_goals        TEXT[]  DEFAULT '{}',   -- 目標（減量・筋力アップ・睡眠改善 等）
        disliked_exercises  TEXT[]  DEFAULT '{}',   -- 嫌いな運動（絶対に提案しない）
        liked_exercises     TEXT[]  DEFAULT '{}',   -- 好きな運動
        exercise_freq       VARCHAR(30) DEFAULT 'unknown', -- 運動頻度（daily/weekly/rarely/none）
        available_time_min  INT,                    -- 1回の運動に使える時間（分）
        health_constraints  TEXT[]  DEFAULT '{}',   -- 身体的制約（膝が痛い・腰痛 等）
        diet_style          VARCHAR(50),            -- 食事スタイル（標準・低糖質・ベジタリアン 等）
        updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_pref_diy (
        user_id             UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        skill_level         VARCHAR(20) DEFAULT 'beginner', -- beginner/intermediate/advanced
        owned_tools         TEXT[]  DEFAULT '{}',   -- 持っている工具
        disliked_methods    TEXT[]  DEFAULT '{}',   -- 苦手な工法・工具（絶対に提案しない）
        preferred_materials TEXT[]  DEFAULT '{}',   -- 好きな素材（木材・アイアン 等）
        past_projects       TEXT[]  DEFAULT '{}',   -- 過去に作ったもの（参考用）
        budget_range        VARCHAR(20),            -- DIY予算帯
        updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_constraints (
        user_id                 UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        food_allergies          TEXT[]  DEFAULT '{}',
        dietary_restrictions    TEXT[]  DEFAULT '{}',
        require_non_smoking     BOOLEAN DEFAULT FALSE,
        require_stroller_ok     BOOLEAN DEFAULT FALSE,
        require_pet_ok          BOOLEAN DEFAULT FALSE,
        hotel_blacklist         TEXT[]  DEFAULT '{}',
        max_meal_budget         INT,
        max_hotel_budget        INT,
        max_shopping_budget     INT,
        max_travel_time_min     INT,
        -- 移動・身体制約（会話から自動学習）
        cannot_drive            BOOLEAN DEFAULT FALSE,
        prefers_car             BOOLEAN DEFAULT FALSE,
        mobility_notes          TEXT,
        travel_companions       TEXT[]  DEFAULT '{}',
        updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_match_scores (
        user_id           UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        overall_score     FLOAT NOT NULL DEFAULT 0.0,
        food_score        FLOAT NOT NULL DEFAULT 0.0,
        gourmet_score     FLOAT NOT NULL DEFAULT 0.0,
        travel_score      FLOAT NOT NULL DEFAULT 0.0,
        shopping_score    FLOAT NOT NULL DEFAULT 0.0,
        health_score      FLOAT NOT NULL DEFAULT 0.0,
        home_score        FLOAT NOT NULL DEFAULT 0.0,
        diy_score         FLOAT NOT NULL DEFAULT 0.0,
        total_sessions    INT   NOT NULL DEFAULT 0,
        helpful_count     INT   NOT NULL DEFAULT 0,
        not_helpful_count INT   NOT NULL DEFAULT 0,
        last_updated      TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_sessions (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id    UUID NOT NULL REFERENCES lu_users(id) ON DELETE CASCADE,
        ai_type    VARCHAR(30) NOT NULL,
        title      VARCHAR(200),
        msg_count  INT  NOT NULL DEFAULT 0,
        started_at TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_messages (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES lu_sessions(id) ON DELETE CASCADE,
        user_id    UUID NOT NULL REFERENCES lu_users(id)    ON DELETE CASCADE,
        role       VARCHAR(10) NOT NULL,
        content    TEXT        NOT NULL,
        ai_type    VARCHAR(30),
        extra      JSONB,
        created_at TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_sessions_user  ON lu_sessions(user_id, started_at DESC);
    -- 管理者: OpenAI予算・チャージ管理
    CREATE TABLE IF NOT EXISTS admin_openai_budget (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        amount_usd  NUMERIC(10,2) NOT NULL,
        note        TEXT,
        charged_by  UUID REFERENCES lu_users(id),
        card_last4  VARCHAR(4),
        charged_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );
    -- 管理者: 月次APIコストスナップショット
    CREATE TABLE IF NOT EXISTS admin_cost_logs (
        id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        month         VARCHAR(7) NOT NULL,
        model         VARCHAR(50) NOT NULL,
        input_tokens  BIGINT DEFAULT 0,
        output_tokens BIGINT DEFAULT 0,
        cost_usd      NUMERIC(10,4) DEFAULT 0,
        recorded_at   TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_admin_cost_logs_month ON admin_cost_logs(month, recorded_at DESC);
    -- 管理者: 登録カード情報（本番ではStripe連携）
    CREATE TABLE IF NOT EXISTS admin_cards (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        card_last4  VARCHAR(4) NOT NULL,
        card_brand  VARCHAR(20) DEFAULT 'Visa',
        exp_month   INT,
        exp_year    INT,
        is_default  BOOLEAN DEFAULT FALSE,
        added_at    TIMESTAMP NOT NULL DEFAULT NOW()
    );
    -- 管理者: システム設定KV
    CREATE TABLE IF NOT EXISTS admin_settings (
        key         VARCHAR(100) PRIMARY KEY,
        value       TEXT,
        updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );
    INSERT INTO admin_settings(key,value) VALUES
        ('monthly_budget_usd','100'),
        ('alert_threshold_pct','80'),
        ('maintenance_mode','false'),
        ('maintenance_mode_manual','false'),  -- 手動ONの場合は自動復旧をスキップ
        ('budget_warning_mode','none'),       -- none/warning(90%超)/critical(100%)
        ('alert_sent_pct','0')               -- 今月送信済みアラートの最高閾値（80/90/100）
    ON CONFLICT(key) DO NOTHING;
    CREATE INDEX IF NOT EXISTS idx_lu_messages_session ON lu_messages(session_id, created_at);

    -- ════════════════════════════════════════════════
    --  成長AI用テーブル群（DB_今後 実装）
    -- ════════════════════════════════════════════════

    -- lu_reactions: 感情・満足度の詳細フィードバック
    CREATE TABLE IF NOT EXISTS lu_reactions (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id  UUID        NOT NULL REFERENCES lu_messages(id) ON DELETE CASCADE,
        user_id     UUID        NOT NULL REFERENCES lu_users(id)    ON DELETE CASCADE,
        reaction    VARCHAR(20) NOT NULL
                    CHECK (reaction IN ('love','helpful','boring','wrong','too_long','too_short','off_topic')),
        detail      TEXT,
        created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_reactions_user    ON lu_reactions(user_id);
    CREATE INDEX IF NOT EXISTS idx_lu_reactions_message ON lu_reactions(message_id);

    -- lu_proposals: 提案の構造化保存（proposal_historyを統合・拡張）
    CREATE TABLE IF NOT EXISTS lu_proposals (
        id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id    UUID        REFERENCES lu_sessions(id) ON DELETE SET NULL,
        user_id       UUID        NOT NULL REFERENCES lu_users(id) ON DELETE CASCADE,
        ai_type       VARCHAR(30) NOT NULL,
        category      VARCHAR(50) NOT NULL DEFAULT 'general',
        item_name     TEXT        NOT NULL,
        item_data     JSONB,
        outcome       VARCHAR(20) DEFAULT 'unknown'
                      CHECK (outcome IN ('accepted','rejected','ignored','unknown')),
        reject_reason TEXT,
        created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_proposals_user    ON lu_proposals(user_id, ai_type);
    CREATE INDEX IF NOT EXISTS idx_lu_proposals_outcome ON lu_proposals(user_id, outcome);

    -- lu_learning_log: AI学習イベントの追跡ログ
    CREATE TABLE IF NOT EXISTS lu_learning_log (
        id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id      UUID        NOT NULL REFERENCES lu_users(id) ON DELETE CASCADE,
        ai_type      VARCHAR(30) NOT NULL,
        learned_key  TEXT        NOT NULL,
        learned_val  TEXT        NOT NULL,
        source       VARCHAR(30) NOT NULL DEFAULT 'conversation'
                     CHECK (source IN ('conversation','feedback','profile','reaction')),
        confidence   FLOAT       NOT NULL DEFAULT 1.0,
        created_at   TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_learning_user ON lu_learning_log(user_id, ai_type);

    -- lu_usage_stats: 使用パターンの日別集計
    CREATE TABLE IF NOT EXISTS lu_usage_stats (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID        NOT NULL REFERENCES lu_users(id) ON DELETE CASCADE,
        ai_type     VARCHAR(30) NOT NULL,
        date        DATE        NOT NULL,
        msg_count   INT         NOT NULL DEFAULT 0,
        avg_rating  FLOAT,
        topics      TEXT[]      DEFAULT '{}',
        created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, ai_type, date)
    );
    CREATE INDEX IF NOT EXISTS idx_lu_usage_stats_user ON lu_usage_stats(user_id, date DESC);

    -- lu_favorites: お気に入り保存
    CREATE TABLE IF NOT EXISTS lu_favorites (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID        NOT NULL REFERENCES lu_users(id) ON DELETE CASCADE,
        ai_type     VARCHAR(30) NOT NULL,
        category    VARCHAR(50) NOT NULL DEFAULT 'general',
        title       TEXT        NOT NULL,
        subtitle    TEXT,
        detail      JSONB,
        source_url  TEXT,
        note        TEXT,
        created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_favorites_user ON lu_favorites(user_id, ai_type, created_at DESC);

    -- lu_action_logs: ユーザーの実行動記録（提案を実際に実行したか）
    CREATE TABLE IF NOT EXISTS lu_action_logs (
        id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id      UUID        NOT NULL REFERENCES lu_users(id)    ON DELETE CASCADE,
        ai_type      VARCHAR(30) NOT NULL,
        proposal_id  UUID        REFERENCES lu_proposals(id) ON DELETE SET NULL,
        action_type  VARCHAR(30) NOT NULL
                     CHECK (action_type IN ('visited','cooked','purchased','booked','diy_done','exercised','other')),
        note         TEXT,
        actioned_at  TIMESTAMP   NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_lu_action_logs_user ON lu_action_logs(user_id, ai_type);
    """
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


# 起動時にテーブル初期化
with app.app_context():
    # 記憶テーブル（AI_assistant_02 側）
    try:
        init_db()
        print("[DB] 記憶スキーマ 初期化完了")
    except Exception as e:
        print(f"[DB] 記憶スキーマ スキップ: {e}")
    # Lumina テーブル
    try:
        db_init_lumina_tables()
        print("[DB] Lumina テーブル 初期化完了")
    except Exception as e:
        print(f"[DB] Lumina テーブル スキップ: {e}")
    # カラム追加マイグレーション（既存DBへの後付け対応）
    migrations = [
        # 既存マイグレーション
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE lu_match_scores ADD COLUMN IF NOT EXISTS gourmet_score FLOAT NOT NULL DEFAULT 0.0",
        # lu_users への成長追跡カラム追加（DB_今後）
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN DEFAULT FALSE",
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS first_chat_at TIMESTAMP",
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP",
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS total_sessions INT DEFAULT 0",
        "ALTER TABLE lu_users ADD COLUMN IF NOT EXISTS favorite_ai VARCHAR(30)",
        # 移動・身体制約カラム（lu_constraints 拡張）
        "ALTER TABLE lu_constraints ADD COLUMN IF NOT EXISTS cannot_drive BOOLEAN DEFAULT FALSE",
        "ALTER TABLE lu_constraints ADD COLUMN IF NOT EXISTS prefers_car BOOLEAN DEFAULT FALSE",
        "ALTER TABLE lu_constraints ADD COLUMN IF NOT EXISTS mobility_notes TEXT",
        "ALTER TABLE lu_constraints ADD COLUMN IF NOT EXISTS travel_companions TEXT[] DEFAULT '{}'",
        # lu_pref_health / lu_pref_diy 新テーブル（既存ユーザー向け初期行挿入）
        "INSERT INTO lu_pref_health (user_id) SELECT id FROM lu_users WHERE is_active=TRUE ON CONFLICT DO NOTHING",
        "INSERT INTO lu_pref_diy (user_id) SELECT id FROM lu_users WHERE is_active=TRUE ON CONFLICT DO NOTHING",
        # admin_cost_logs 拡張（自前トークン記録用）
        "CREATE INDEX IF NOT EXISTS idx_admin_cost_logs_month ON admin_cost_logs(month, recorded_at DESC)",
        # maintenance_mode_manual フラグの初期挿入（存在しない場合のみ）
        "INSERT INTO admin_settings (key, value) VALUES ('maintenance_mode_manual','false') ON CONFLICT (key) DO NOTHING",
        # budget_warning_mode の初期挿入
        "INSERT INTO admin_settings (key, value) VALUES ('budget_warning_mode','none') ON CONFLICT (key) DO NOTHING",
    ]
    for sql in migrations:
        try:
            db_exec(sql)
            print(f"[DB] Migration OK: {sql[:60]}...")
        except Exception as e:
            print(f"[DB] Migration スキップ: {e}")

    # 起動時フォールバックモードチェック（残高ゼロで自動ON）
    try:
        _check_and_update_fallback_mode()
    except Exception as e:
        print(f"[Fallback] 起動時チェックスキップ: {e}")


# ══════════════════════════════════════════════════════════════
#  JWT 認証
# ══════════════════════════════════════════════════════════════
def create_token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id,
         "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)},
        SECRET_KEY, algorithm="HS256"
    )

def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        if not token:
            return jsonify({"error": "認証が必要です"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # まず is_active を問わず存在確認し、停止か削除かを区別する
            user = db_exec("SELECT * FROM lu_users WHERE id=%s", (data["sub"],), fetch="one")
            if not user:
                return jsonify({"error": "アカウントが見つかりません"}), 401
            if not user.get("is_active"):
                return jsonify({"error": "このアカウントは管理者により停止されています。お心当たりがある場合はサポートにお問い合わせください。"}), 401
            # is_active=TRUE のユーザーのみ g.current_user にセット
            user = db_exec("SELECT * FROM lu_users WHERE id=%s AND is_active=TRUE",
                           (data["sub"],), fetch="one")
            if not user:
                return jsonify({"error": "ユーザーが見つかりません"}), 401
            g.current_user = dict(user)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "セッションが期限切れです"}), 401
        except Exception:
            return jsonify({"error": "無効なトークンです"}), 401
        return f(*args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════════════════════
#  ヘルパー
# ══════════════════════════════════════════════════════════════
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        if not token:
            return jsonify({"error": "認証が必要です"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user = db_exec("SELECT * FROM lu_users WHERE id=%s AND is_active=TRUE AND is_admin=TRUE",
                           (data["sub"],), fetch="one")
            if not user:
                return jsonify({"error": "管理者権限がありません"}), 403
            g.current_user = dict(user)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "セッションが期限切れです"}), 401
        except Exception:
            return jsonify({"error": "無効なトークンです"}), 401
        return f(*args, **kwargs)
    return wrapper

PLAN_LIMITS = {"free": 10, "pro": 50, "master": 200}

# ══════════════════════════════════════════════════════════════
#  フォールバックモード管理
# ══════════════════════════════════════════════════════════════

def _check_and_update_fallback_mode():
    """
    OpenAI残高と使用量を比較してフォールバックモードと警告レベルを自動切替。
    - 消化率 < 90%  → budget_warning_mode=none
    - 消化率 >= 90% → budget_warning_mode=warning（予告バナー）
    - 残高ゼロ      → budget_warning_mode=critical + maintenance_mode=true
    """
    try:
        # チャージ累計
        charged = db_exec("SELECT COALESCE(SUM(amount_usd),0) as total FROM admin_openai_budget", fetch="one")
        charged_usd = float(charged["total"] or 0) if charged else 0.0

        # 使用累計（全期間）
        used = db_exec("SELECT COALESCE(SUM(cost_usd),0) as total FROM admin_cost_logs", fetch="one")
        used_usd = float(used["total"] or 0) if used else 0.0

        balance  = charged_usd - used_usd
        used_pct = (used_usd / charged_usd * 100) if charged_usd > 0 else 0.0

        # 現在のモードと手動フラグ
        cur    = db_exec("SELECT value FROM admin_settings WHERE key='maintenance_mode'", fetch="one")
        manual = db_exec("SELECT value FROM admin_settings WHERE key='maintenance_mode_manual'", fetch="one")
        current_mode = (cur["value"] if cur else "false") == "true"
        is_manual    = (manual["value"] if manual else "false") == "true"

        # ── 予算警告レベルの自動更新 ──────────────────────────────
        if balance <= 0:
            new_warning = "critical"   # 残高ゼロ → フォールバック発動
        elif used_pct >= 90:
            new_warning = "warning"    # 90%超 → 予告バナー
        else:
            new_warning = "none"

        cur_warning = db_exec("SELECT value FROM admin_settings WHERE key='budget_warning_mode'", fetch="one")
        old_warning = cur_warning["value"] if cur_warning else "none"
        if old_warning != new_warning:
            db_exec("UPDATE admin_settings SET value=%s, updated_at=NOW() WHERE key='budget_warning_mode'",
                    (new_warning,))
            print(f"[Fallback] 予算警告レベル変更: {old_warning} → {new_warning} (消化率={used_pct:.1f}%)")

        # ── フォールバックモードの自動ON/OFF ─────────────────────
        if balance <= 0 and not current_mode:
            db_exec("UPDATE admin_settings SET value='true',  updated_at=NOW() WHERE key='maintenance_mode'")
            db_exec("UPDATE admin_settings SET value='false', updated_at=NOW() WHERE key='maintenance_mode_manual'")
            print(f"[Fallback] 残高ゼロ（${balance:.4f}）→ メンテナンスモード 自動ON")
        elif balance > 0 and current_mode and not is_manual:
            db_exec("UPDATE admin_settings SET value='false', updated_at=NOW() WHERE key='maintenance_mode'")
            print(f"[Fallback] 残高回復（${balance:.4f}）→ メンテナンスモード 自動OFF")
        elif balance > 0 and current_mode and is_manual:
            print(f"[Fallback] 残高あり（${balance:.4f}）だが手動ONのため維持")

        # ── 予算アラートメール（80% / 90% / 100% 到達時に1回だけ送信）────
        try:
            budget_row  = db_exec("SELECT value FROM admin_settings WHERE key='monthly_budget_usd'", fetch="one")
            budget_usd_alert = float(budget_row["value"]) if budget_row else 100.0
            cost_row = db_exec(
                "SELECT COALESCE(SUM(cost_usd),0) as total FROM admin_cost_logs "                "WHERE month=TO_CHAR(CURRENT_DATE,'YYYY-MM')", fetch="one")
            month_used = float(cost_row["total"] or 0) if cost_row else 0.0
            month_pct  = (month_used / budget_usd_alert * 100) if budget_usd_alert > 0 else 0.0
            sent_row  = db_exec("SELECT value FROM admin_settings WHERE key='alert_sent_pct'", fetch="one")
            sent_pct  = int(sent_row["value"] or 0) if sent_row else 0
            month_key = datetime.now().strftime("%Y-%m")
            sent_month_row = db_exec("SELECT value FROM admin_settings WHERE key='alert_sent_month'", fetch="one")
            sent_month = sent_month_row["value"] if sent_month_row else ""
            if sent_month != month_key:
                db_exec("INSERT INTO admin_settings(key,value,updated_at) VALUES('alert_sent_pct','0',NOW()) "                        "ON CONFLICT(key) DO UPDATE SET value='0',updated_at=NOW()")
                db_exec("INSERT INTO admin_settings(key,value,updated_at) VALUES('alert_sent_month',%s,NOW()) "                        "ON CONFLICT(key) DO UPDATE SET value=%s,updated_at=NOW()",
                        (month_key, month_key))
                sent_pct = 0
            hit_level = 0
            for threshold in [100, 90, 80]:
                if month_pct >= threshold and sent_pct < threshold:
                    hit_level = threshold
                    break
            if hit_level > 0:
                send_admin_budget_alert(month_used, budget_usd_alert, month_pct, hit_level)
                db_exec("UPDATE admin_settings SET value=%s,updated_at=NOW() WHERE key='alert_sent_pct'",
                        (str(hit_level),))
                print(f"[BudgetAlert] {hit_level}%アラート送信完了")
        except Exception as alert_err:
            print(f"[BudgetAlert] アラート処理エラー: {alert_err}")

    except Exception as e:
        print(f"[Fallback] モードチェックエラー: {e}")


def is_fallback_mode() -> bool:
    """現在フォールバックモードか確認する"""
    try:
        row = db_exec("SELECT value FROM admin_settings WHERE key='maintenance_mode'", fetch="one")
        return (row["value"] if row else "false") == "true"
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════
#  メール送信ユーティリティ
#  環境変数: MAIL_DRIVER=smtp|none  SMTP_HOST/PORT/USER/PASS/FROM
#            ADMIN_EMAIL  APP_URL
# ══════════════════════════════════════════════════════════════

def _send_email(to: str, subject: str, body_text: str, body_html: str = None) -> bool:
    driver = os.getenv("MAIL_DRIVER", "none").lower()
    if driver == "none":
        print(f"[Mail] (MAIL_DRIVER=none) To={to} Subject={subject}")
        return True
    try:
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        from_addr = os.getenv("SMTP_FROM", smtp_user)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.ehlo(); s.starttls(); s.login(smtp_user, smtp_pass)
            s.sendmail(from_addr, [to], msg.as_string())
        print(f"[Mail] 送信成功: To={to} Subject={subject}")
        return True
    except Exception as e:
        print(f"[Mail] 送信失敗: {e}")
        return False


def send_admin_budget_alert(used_usd: float, budget_usd: float, pct: float, level: int):
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if not admin_email:
        print(f"[Mail] ADMIN_EMAIL 未設定 → アラートスキップ (level={level}%)")
        return
    app_url   = os.getenv("APP_URL", "https://aiassistant-production-264e.up.railway.app")
    remaining = max(0.0, budget_usd - used_usd)
    if level == 100:
        emoji = "🚨"; heading = "予算100%到達・フォールバックモード移行"
        caution = "予算を超過しました。フォールバックモードに切り替わっています。"
        actions = "1. 予算の追加（OpenAI プリペイドへの入金）\n2. フォールバックモードの動作確認\n3. ユーザーへの告知検討"
    elif level == 90:
        emoji = "🔴"; heading = f"OpenAI予算{level}%到達アラート"
        caution = "このペースだと、月末には予算を超過する可能性があります。"
        actions = f"1. 予算の追加（推奨額: +${budget_usd:.0f}）\n2. 使用量の監視強化\n3. フォールバックモードの準備確認"
    else:
        emoji = "⚠️"; heading = f"OpenAI予算{level}%到達アラート"
        caution = "このペースだと、月末には予算を超過する可能性があります。"
        actions = f"1. 予算の追加（推奨額: +${budget_usd:.0f}）\n2. 使用量の監視強化\n3. フォールバックモードの準備確認"
    subject   = f"{emoji} {heading}"
    body_text = (
        f"今月のOpenAI使用額が{level}%に達しました。\n\n"
        f"現在の使用額: ${used_usd:.2f}\n予算上限: ${budget_usd:.2f}\n"
        f"使用率: {pct:.0f}%\n残り: ${remaining:.2f}\n\n"
        f"{caution}\n\n以下の対応を検討してください：\n{actions}\n\n"
        f"管理画面: {app_url}/admin-login.html"
    )
    body_html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
<h2 style="color:{'#c00' if level>=100 else '#e55' if level>=90 else '#e90'}">{emoji} {heading}</h2>
<p>今月のOpenAI使用額が<strong>{level}%</strong>に達しました。</p>
<table style="border-collapse:collapse;width:100%;margin:16px 0">
  <tr style="background:#f5f5f5"><td style="padding:8px 12px;font-weight:bold">現在の使用額</td><td style="padding:8px 12px">${used_usd:.2f}</td></tr>
  <tr><td style="padding:8px 12px;font-weight:bold">予算上限</td><td style="padding:8px 12px">${budget_usd:.2f}</td></tr>
  <tr style="background:#f5f5f5"><td style="padding:8px 12px;font-weight:bold">使用率</td><td style="padding:8px 12px"><strong>{pct:.0f}%</strong></td></tr>
  <tr><td style="padding:8px 12px;font-weight:bold">残り</td><td style="padding:8px 12px">${remaining:.2f}</td></tr>
</table>
<p>{caution}</p>
<pre style="background:#f9f9f9;padding:12px;border-radius:4px">{actions}</pre>
<p><a href="{app_url}/admin-login.html" style="display:inline-block;padding:10px 20px;background:#1a1a2e;color:#fff;text-decoration:none;border-radius:4px">管理画面を開く</a></p>
</body></html>"""
    _send_email(admin_email, subject, body_text, body_html)


def send_user_notification(to_email: str, nickname: str, subject: str, body_text: str, body_html: str = None):
    _send_email(to_email, subject, body_text, body_html)


def hash_pw(pw):   return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def check_pw(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())

def serialize_user(u):
    return {"id": str(u["id"]), "nickname": u["nickname"], "email": u["email"],
            "plan": u["plan"], "usage_count": u["usage_count"],
            "usage_limit": PLAN_LIMITS.get(u["plan"], 10)}

def safe_json(v):
    if isinstance(v, (dict, list)): return v
    try: return json.loads(v) if v else v
    except Exception: return v


# ══════════════════════════════════════════════════════════════
#  Lumina コンテキスト → エージェントへの注入
# ══════════════════════════════════════════════════════════════
def get_user_context(user_id):
    ctx = {}
    for tbl, key in [("lu_profiles","profile"),("lu_pref_food","food"),
                     ("lu_pref_shopping","shopping"),("lu_pref_travel","travel"),
                     ("lu_pref_restaurant","restaurant"),("lu_constraints","constraints"),
                     ("lu_match_scores","match_score"),
                     ("lu_pref_health","health_pref"),("lu_pref_diy","diy_pref")]:
        row  = db_exec(f"SELECT * FROM {tbl} WHERE user_id=%s", (user_id,), fetch="one")
        data = {k: safe_json(v) for k, v in dict(row).items()} if row else {}
        ctx[key] = data
    row = db_exec("SELECT nickname FROM lu_users WHERE id=%s", (user_id,), fetch="one")
    ctx["nickname"] = row["nickname"] if row else "ユーザー"

    # user_preferences（会話学習した好き嫌い）も取得して ctx に追加
    # lu_pref_* と補完関係にある：手動設定は lu_pref_*、会話学習は user_preferences
    try:
        from memory.db import get_conn as mem_get_conn
        import psycopg2.extras
        with mem_get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT ai_type, key, value, confidence FROM user_preferences "
                    "WHERE user_id = %s ORDER BY confidence DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
        prefs_by_ai = {}
        for r in (rows or []):
            ai = r["ai_type"]
            if ai not in prefs_by_ai:
                prefs_by_ai[ai] = []
            prefs_by_ai[ai].append({
                "key": r["key"],
                "value": r["value"],
                "confidence": r["confidence"],
            })
        ctx["learned_prefs"] = prefs_by_ai
    except Exception:
        ctx["learned_prefs"] = {}

    # lu_learning_log から直近の学習イベント（reaction/action）を取得
    try:
        rows = db_exec(
            "SELECT ai_type, learned_key, learned_val, source, confidence, created_at "
            "FROM lu_learning_log WHERE user_id=%s "
            "ORDER BY created_at DESC LIMIT 30",
            (user_id,), fetch="all"
        ) or []
        learning_events = []
        for r in rows:
            learning_events.append({
                "ai_type":   r["ai_type"],
                "key":       r["learned_key"],
                "val":       r["learned_val"],
                "source":    r["source"],
                "confidence": float(r["confidence"] or 0),
            })
        ctx["learning_events"] = learning_events
    except Exception:
        ctx["learning_events"] = []

    return ctx

def build_context_injection(user_id, ai_type):
    ctx = get_user_context(user_id)
    lines = ["━━━━ Lumina AIパーソナライズ情報（必ず考慮すること） ━━━━",
             f"ユーザー名: {ctx.get('nickname','ユーザー')}さん"]

    p = ctx.get("profile", {})
    if p.get("area"):            lines.append(f"居住エリア: {p['area']}")
    if p.get("household_size"):  lines.append(f"家族構成: {p['household_size']}人")
    if p.get("monthly_budget"):  lines.append(f"月次予算目安: ¥{p['monthly_budget']:,}")
    if p.get("transport_modes"): lines.append(f"移動手段: {', '.join(p['transport_modes'])}")
    # ── ユーザーが登録した興味・趣味（全AIに共通で注入）──
    interests = p.get("interests") or []
    if isinstance(interests, str):
        try:
            import json as _json
            interests = _json.loads(interests)
        except Exception:
            interests = [interests]
    if interests:
        lines.append(f"興味・趣味: {', '.join(interests)}（会話・提案のコンテキストとして積極的に活用すること）")

    if ai_type in ("recipe", "gourmet", "health", "general"):
        fd = ctx.get("food", {})
        if fd.get("liked_cuisines"):    lines.append(f"好きな料理ジャンル: {', '.join(fd['liked_cuisines'])}（レシピ提案時は優先的にこのジャンルから提案すること）")
        if fd.get("disliked_cuisines"): lines.append(f"苦手な料理: {', '.join(fd['disliked_cuisines'])}")
        if fd.get("allergies"):         lines.append(f"⚠️ アレルギー: {', '.join(fd['allergies'])} ←絶対に提案しないこと")
        if fd.get("spice_level"):
            spice_map = {1:"薄味・辛さなし", 2:"普通", 3:"辛め", 4:"かなり辛い", 5:"激辛"}
            spice_val = fd["spice_level"]
            spice_label = spice_map.get(int(spice_val), f"{spice_val}/5") if str(spice_val).isdigit() else str(spice_val)
            lines.append(f"辛さの好み: {spice_label}（レシピの辛さに必ず反映すること）")

    if ai_type in ("travel", "general"):
        t = ctx.get("travel", {})
        if t.get("travel_styles"):    lines.append(f"旅行スタイル: {', '.join(t['travel_styles'])}")
        if t.get("budget_range"):     lines.append(f"旅行予算帯: {t['budget_range']}")
        if t.get("max_travel_hours"): lines.append(f"移動許容時間: {t['max_travel_hours']}時間まで")

    if ai_type in ("shopping", "appliance", "diy", "general"):
        s = ctx.get("shopping", {})
        if s.get("liked_brands"):    lines.append(f"好きなブランド: {', '.join(s['liked_brands'])}")
        if s.get("disliked_brands"): lines.append(f"苦手なブランド: {', '.join(s['disliked_brands'])}")

        # 買い物の優先軸をAIに注入（比較表や提案の軸に使用）
        if ai_type == "shopping":
            priority_labels = {
                "priority_price":        ("価格の安さ", "price"),
                "priority_practicality": ("実用性・コスパ", "practicality"),
                "priority_novelty":      ("デザイン・おしゃれさ", "novelty"),
                "priority_reliability":  ("耐久性・品質信頼性", "reliability"),
            }
            top_priorities = []
            for col, (label, key) in priority_labels.items():
                val = s.get(col, 3)
                if isinstance(val, int) and val >= 4:
                    top_priorities.append(label)
            if top_priorities:
                lines.append(f"【買い物の優先軸（比較表・提案に必ず反映すること）】: {' > '.join(top_priorities)}")
                lines.append("→ 比較表を作るときは上記の優先軸を第1列・第1ソートキーにする")
            # user_preferences からも好み軸を補完
            learned = ctx.get("learned_prefs", {}).get("shopping", [])
            price_keywords  = ["安い", "コスパ", "予算", "節約", "格安"]
            quality_keywords = ["丈夫", "壊れにくい", "品質", "長持ち", "耐久"]
            design_keywords  = ["デザイン", "おしゃれ", "見た目", "かっこいい", "かわいい"]
            inferred = []
            for pref in learned:
                v = pref.get("value","")
                if pref["confidence"] > 0:
                    if any(k in v for k in price_keywords):   inferred.append("価格重視")
                    if any(k in v for k in quality_keywords): inferred.append("耐久性重視")
                    if any(k in v for k in design_keywords):  inferred.append("デザイン重視")
            inferred = list(dict.fromkeys(inferred))  # 重複除去
            if inferred:
                lines.append(f"会話から推測した優先軸: {' / '.join(inferred)}（比較表・提案に活用すること）")

    if ai_type in ("health", "general"):
        h = ctx.get("health_pref", {})
        if h.get("health_goals"):       lines.append(f"健康目標: {', '.join(h['health_goals'])}")
        if h.get("liked_exercises"):    lines.append(f"好きな運動: {', '.join(h['liked_exercises'])}")
        if h.get("disliked_exercises"): lines.append(f"⚠️ 嫌いな運動（絶対に提案しないこと）: {', '.join(h['disliked_exercises'])}")
        if h.get("exercise_freq") and h["exercise_freq"] != "unknown":
            lines.append(f"現在の運動頻度: {h['exercise_freq']}")
        if h.get("available_time_min"): lines.append(f"1回に使える時間: {h['available_time_min']}分")
        if h.get("health_constraints"): lines.append(f"⚠️ 身体的制約（負荷をかけないこと）: {', '.join(h['health_constraints'])}")
        if h.get("diet_style"):         lines.append(f"食事スタイル: {h['diet_style']}")

    if ai_type in ("diy", "general"):
        d = ctx.get("diy_pref", {})
        if d.get("skill_level") and d["skill_level"] != "beginner":
            lines.append(f"DIYスキルレベル: {d['skill_level']}")
        elif d.get("skill_level") == "beginner":
            lines.append("DIYスキル: 初心者（難しい工程は省略・代替案を示すこと）")
        if d.get("owned_tools"):         lines.append(f"持っている工具: {', '.join(d['owned_tools'])}")
        if d.get("disliked_methods"):    lines.append(f"⚠️ 苦手な工法・工具（絶対に提案しないこと）: {', '.join(d['disliked_methods'])}")
        if d.get("preferred_materials"): lines.append(f"好きな素材: {', '.join(d['preferred_materials'])}")
        if d.get("budget_range"):        lines.append(f"DIY予算帯: {d['budget_range']}")

    c = ctx.get("constraints", {})
    cl = []
    if c.get("food_allergies"):       cl.append(f"食物アレルギー: {', '.join(c['food_allergies'])}")
    if c.get("dietary_restrictions"): cl.append(f"食事制限: {', '.join(c['dietary_restrictions'])}")
    if c.get("require_non_smoking"):  cl.append("禁煙必須")
    if c.get("require_stroller_ok"):  cl.append("ベビーカー可必須")
    if c.get("require_pet_ok"):       cl.append("ペット可必須")
    if c.get("max_hotel_budget"):     cl.append(f"宿泊上限: ¥{c['max_hotel_budget']:,}/泊")
    if c.get("max_meal_budget"):      cl.append(f"食事上限: ¥{c['max_meal_budget']:,}/回")
    if c.get("max_shopping_budget"):  cl.append(f"買い物上限: ¥{c['max_shopping_budget']:,}")
    if c.get("max_travel_time_min"):  cl.append(f"移動時間上限: {c['max_travel_time_min']}分")
    # 移動・身体制約（会話から自動学習されたもの）
    if c.get("cannot_drive"):         cl.append("🚫 運転不可（レンタカー・自家用車プランは絶対に提案しないこと）")
    if c.get("prefers_car"):          cl.append("🚗 車移動希望（レンタカー等を積極的に使うプランを提案）")
    if c.get("mobility_notes"):       cl.append(f"身体制約: {c['mobility_notes']}（長距離歩行・急な階段等を避けること）")
    if c.get("travel_companions"):    cl.append(f"同行者: {', '.join(c['travel_companions'])}（同行者に合わせた提案をすること）")
    if cl:
        lines.append("⚠️ 以下は絶対に守ること（除外ルール）:")
        for x in cl: lines.append(f"   - {x}")

    # ── 会話学習した好み（user_preferences）をAIに注入 ──────────
    # lu_pref_* で拾えなかった細かい好き嫌いを補完する
    learned = ctx.get("learned_prefs", {})
    # このAI + general の両方のprefsを対象にする
    relevant_ai_keys = [ai_type, "general"]
    shown_likes, shown_dislikes = [], []
    for ak in relevant_ai_keys:
        for p in learned.get(ak, []):
            val = p["value"].replace("[嫌い]", "").strip()
            if p["confidence"] < 0:  # dislike
                shown_dislikes.append(f"{p['key']}: {val}")
            elif p["confidence"] >= 2:  # like（推測レベルは除外）
                shown_likes.append(f"{p['key']}: {val}")
    if shown_likes:
        lines.append("会話から学習した好み（積極的に活用すること）:")
        for x in shown_likes[:8]: lines.append(f"   ✓ {x}")
    if shown_dislikes:
        lines.append("会話から学習した除外条件（絶対に提案しないこと）:")
        for x in shown_dislikes[:8]: lines.append(f"   🚫 {x}")

    # ── lu_learning_log から直近のフィードバックパターンをAIに注入 ──
    # 「最近どんな反応をされているか」をAIが把握し、提案スタイルを自動調整する
    events = ctx.get("learning_events", [])
    if events:
        # このAIと関係するイベントだけ絞り込む
        ai_events = [e for e in events if e["ai_type"] == ai_type or e["ai_type"] == "general"]

        # reaction イベントを集計（直近10件）
        reaction_events = [e for e in ai_events if e["source"] == "reaction"][:10]
        neg_reactions  = [e for e in reaction_events if e["val"] in ("wrong","off_topic","boring")]
        pos_reactions  = [e for e in reaction_events if e["val"] in ("love","helpful")]
        # action イベント（実際に行動した実績）
        action_events  = [e for e in ai_events if e["source"] == "feedback"][:5]

        if neg_reactions:
            lines.append(f"【最近のフィードバック傾向 - 要改善】（直近{len(neg_reactions)}件の否定的反応）:")
            neg_types = {}
            for e in neg_reactions:
                neg_types[e["val"]] = neg_types.get(e["val"], 0) + 1
            for k, v in neg_types.items():
                advice = {
                    "wrong":     "内容の事実確認を強化し、正確な情報のみ提案すること",
                    "off_topic": "ユーザーの質問に直接答えること。話題がずれないよう注意",
                    "boring":    "提案に具体性・意外性を加えること。毎回同じパターンを避ける",
                    "too_long":  "回答をより簡潔にまとめること",
                    "too_short": "もう少し詳しい情報・理由を添えること",
                }.get(k, "提案の質を改善すること")
                lines.append(f"   ⚠️ {k} が{v}回 → {advice}")

        if pos_reactions:
            lines.append(f"【最近のフィードバック傾向 - 好評】（直近{len(pos_reactions)}件の肯定的反応）:")
            lines.append(f"   ✓ このパターンの提案を継続・強化すること")

        if action_events:
            lines.append("【実際に行動した実績（最優先で参考にすること）】:")
            for e in action_events[:3]:
                lines.append(f"   ✓ {e['key'].replace('action_','')}: {e['val']}")

    sc           = ctx.get("match_score", {})
    overall      = sc.get("overall_score", 0)
    ai_score_col = {
        "recipe": "food_score", "gourmet": "food_score",
        "travel": "travel_score", "shopping": "shopping_score",
        "health": "health_score", "appliance": "home_score", "diy": "diy_score",
    }.get(ai_type, "overall_score")
    ai_score     = sc.get(ai_score_col, overall)
    sessions     = sc.get("total_sessions", 0)
    nickname     = ctx.get("nickname", "ユーザー")

    if sessions > 0:
        lines.append(f"（会話実績: {sessions}回 / 総合マッチ度: {round(overall)}% / AI固有スコア: {round(ai_score)}%）")

    # ── スコアに応じた行動モードを注入 ──────────────────────────
    lines.append("")
    lines.append("【AIの行動モード】")

    if overall < 8:
        # ── フェーズ1: 初対面（情報収集優先）──
        lines.append("モード: 初対面（情報収集フェーズ）")
        lines.append(f"・{nickname}さんの好みがまだ不明なため、提案前に1〜2つだけ質問して好みを引き出すこと")
        lines.append("・質問は「ジャンル」「予算感」「シチュエーション」の中から最も重要な1つを選ぶ")
        lines.append("・提案する場合は「いくつかご質問してもいいですか？」と一言断ってから行う")
        lines.append("・まだ記憶がないので、一般的な人気店・定番を提案するにとどめる")

    elif overall < 25:
        # ── フェーズ2: 学習フェーズ（確認しながら提案）──
        lines.append("モード: 学習フェーズ（好み蓄積中）")
        lines.append(f"・{nickname}さんの好みが少し蓄積されてきた。蓄積された好みを必ず参照して提案すること")
        lines.append("・「確実」フラグの好みは確認なしで前提として使ってよい")
        lines.append("・「推測」フラグの好みは「〇〇がお好みでしたね？」と一言確認してから使う")
        lines.append("・却下された提案は絶対に繰り返さないこと")
        lines.append(f"・返答の冒頭で「{nickname}さんの好みを踏まえると〜」と一言添えるとよい")

    elif overall < 50:
        # ── フェーズ3: パーソナライズフェーズ（確認なしで即提案）──
        lines.append("モード: パーソナライズフェーズ（常連モード）")
        lines.append(f"・{nickname}さんの好みは十分に把握済み。確認は一切不要。即提案に移ること")
        lines.append("・蓄積された好み情報をすべて前提として使い、「なぜこれを勧めるか」を必ず一言添える")
        lines.append("・却下された提案・店・商品は絶対に出さないこと（リストを必ず確認すること）")
        lines.append(f"・「{nickname}さんのいつもの感じだと〜」「{nickname}さんには〇〇が合いそうです」のような表現を使う")
        lines.append("・好評だった過去の提案に近いものを優先的に出す")

    else:
        # ── フェーズ4: 専属AIフェーズ（先回り提案・パターン参照）──
        lines.append("モード: 専属AIフェーズ（深い個別最適化）")
        lines.append(f"・{nickname}さんの好み・行動パターンが深く蓄積されている。先回りした提案を積極的に行うこと")
        lines.append("・好みをすべて既知として扱い、「確認」は一切行わない")
        lines.append(f"・「{nickname}さんといえば〜」「いつものパターンだと〜」のように個人の傾向を自然に言語化する")
        lines.append("・却下履歴・好評履歴の両方を参照し、ユーザーが言わなくても自動的に除外・優先する")
        lines.append("・提案理由を「なぜこれがあなたに合うか」まで具体的に説明する")
        lines.append("・会話の最後に次回につながる一言（新情報・関連情報）を添えるとよい")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# ── スコア成長イベント重み定義 ────────────────────────────────
# 「何が起きたか」によって加算量を変える。125回会話しないとフェーズ4にならない問題を解消。
# overall: 全AIに共通の累積スコア（フェーズ判定に使用）
# ai固有: そのAIに特化したスコア（AI内での詳細度調整に使用）
SCORE_WEIGHTS = {
    # イベント名            overall  ai固有
    "chat_normal":        (  0.4,   0.8),   # 通常会話（変更なし）
    "chat_helpful":       (  2.0,   3.5),   # helpful評価（引き上げ: +0.5/+1.0）
    "chat_not_helpful":   ( -0.2,  -0.8),   # not helpful（ペナルティ軽減）
    "pref_dislike":       (  1.5,   2.5),   # 嫌いを明言（重要な学習イベント）
    "pref_like":          (  1.0,   2.0),   # 好きを明言
    "pref_allergy":       (  2.0,   3.0),   # アレルギー・絶対制約を明言
    "proposal_rejected":  (  0.8,   1.5),   # 提案を却下（学習した証拠）
    "proposal_accepted":  (  1.5,   2.5),   # 提案を採用
    "action_done":        (  2.0,   4.0),   # 実際に行動した（最高重み）
    "reaction_love":      (  2.5,   4.5),   # love反応
    "reaction_helpful":   (  1.5,   2.5),   # helpful反応
    "reaction_wrong":     ( -0.5,  -1.0),   # wrong反応
    "reaction_off_topic": ( -0.3,  -0.5),   # off_topic反応
}

AI_SCORE_COL = {
    "recipe":"food_score","gourmet":"food_score","travel":"travel_score",
    "shopping":"shopping_score","health":"health_score",
    "appliance":"home_score","diy":"diy_score",
}

def _apply_score_event(user_id: str, ai_type: str, event: str):
    """成長イベントをスコアに反映する共通関数"""
    w = SCORE_WEIGHTS.get(event, (0.4, 0.8))
    d_overall, d_ai = w
    col = AI_SCORE_COL.get(ai_type, "overall_score")
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO lu_match_scores (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            if d_overall >= 0:
                cur.execute(
                    f"UPDATE lu_match_scores SET "
                    f"overall_score=LEAST(100,overall_score+%s), "
                    f"{col}=LEAST(100,{col}+%s), "
                    f"last_updated=NOW() WHERE user_id=%s",
                    (d_overall, d_ai, user_id)
                )
            else:
                cur.execute(
                    f"UPDATE lu_match_scores SET "
                    f"overall_score=GREATEST(0,overall_score+%s), "
                    f"{col}=GREATEST(0,{col}+%s), "
                    f"last_updated=NOW() WHERE user_id=%s",
                    (d_overall, d_ai, user_id)
                )
        conn.commit()
    except Exception as e:
        print(f"[Score] {event} 更新エラー: {e}")

def update_match_score(user_id, ai_type, rating=0):
    """後方互換ラッパー。既存の rating=1/-1/0 呼び出しを成長イベントに変換"""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lu_match_scores (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        if rating == 1:
            cur.execute(
                f"UPDATE lu_match_scores SET helpful_count=helpful_count+1,"
                f"total_sessions=total_sessions+1,last_updated=NOW() WHERE user_id=%s", (user_id,)
            )
    conn.commit()
    event = {1: "chat_helpful", -1: "chat_not_helpful"}.get(rating, "chat_normal")
    _apply_score_event(user_id, ai_type, event)


# ══════════════════════════════════════════════════════════════
#  認証エンドポイント
# ══════════════════════════════════════════════════════════════
@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.json or {}
    nickname = (d.get("nickname") or "").strip()
    email    = (d.get("email") or "").strip().lower()
    password = d.get("password", "")
    plan     = d.get("plan", "free")

    if not nickname or not email or not password:
        return jsonify({"error": "必須項目を入力してください"}), 400
    if len(password) < 8:
        return jsonify({"error": "パスワードは8文字以上で入力してください"}), 400
    if plan not in ("free", "pro", "master"):
        plan = "free"

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM lu_users WHERE email=%s", (email,))
        if cur.fetchone():
            return jsonify({"error": "このメールアドレスは既に登録されています"}), 409
        uid = str(uuid.uuid4())
        cur.execute("INSERT INTO lu_users (id,nickname,email,password_hash,plan,terms_agreed_at)"
                    " VALUES (%s,%s,%s,%s,%s,NOW())",
                    (uid, nickname, email, hash_pw(password), plan))
        for tbl in ["lu_profiles","lu_pref_food","lu_pref_shopping","lu_pref_travel",
                    "lu_pref_restaurant","lu_constraints","lu_match_scores",
                    "lu_pref_health","lu_pref_diy"]:
            cur.execute(f"INSERT INTO {tbl} (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
    conn.commit()

    return jsonify({"token": create_token(uid),
                    "user": {"id": uid, "nickname": nickname, "email": email,
                             "plan": plan, "usage_count": 0, "usage_limit": PLAN_LIMITS[plan]}}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    d = request.json or {}
    email    = (d.get("email") or "").strip().lower()
    password = d.get("password", "")
    user = db_exec("SELECT * FROM lu_users WHERE email=%s AND is_active=TRUE", (email,), fetch="one")
    if not user or not check_pw(password, user["password_hash"]):
        return jsonify({"error": "メールアドレスまたはパスワードが正しくありません"}), 401
    return jsonify({"token": create_token(str(user["id"])), "user": serialize_user(dict(user))})

@app.route("/api/auth/me",     methods=["GET"])
@auth_required
def me():
    return jsonify({"user": serialize_user(g.current_user)})

@app.route("/api/auth/logout", methods=["POST"])
@auth_required
def logout():
    return jsonify({"message": "ログアウトしました"})


# ══════════════════════════════════════════════════════════════
#  プラン変更（ユーザー自身）
# ══════════════════════════════════════════════════════════════
PLAN_PRICES = {"free": 0, "pro": 980, "master": 2980}

@app.route("/api/user/plan", methods=["PUT"])
@auth_required
def change_user_plan():
    uid  = str(g.current_user["id"])
    data = request.json or {}
    plan = data.get("plan", "")
    if plan not in ("free", "pro", "master"):
        return jsonify({"error": "無効なプランです"}), 400

    current_plan = g.current_user["plan"]
    if plan == current_plan:
        return jsonify({"error": "現在と同じプランです"}), 400

    # ダウングレード時は usage_count をリセットしない（次回更新日まで現プランを維持）
    # アップグレード時は即時適用（usage_count は据え置き）
    new_limit = PLAN_LIMITS[plan]
    db_exec(
        "UPDATE lu_users SET plan=%s, updated_at=NOW() WHERE id=%s",
        (plan, uid)
    )

    # 課金ログ（本番ではStripe連携に置き換える）
    direction = "upgrade" if PLAN_PRICES.get(plan, 0) > PLAN_PRICES.get(current_plan, 0) else "downgrade"
    try:
        db_exec(
            "INSERT INTO admin_cost_logs (user_id, month, model, input_tokens, output_tokens, cost_usd, recorded_at) "
            "VALUES (%s, to_char(NOW(),'YYYY-MM'), 'plan_change', 0, 0, %s, NOW())",
            (uid, PLAN_PRICES.get(plan, 0) / 150)  # 円→USD概算
        )
    except Exception:
        pass  # ログ失敗は無視

    updated_user = db_exec("SELECT * FROM lu_users WHERE id=%s", (uid,), fetch="one")
    return jsonify({
        "ok": True,
        "direction": direction,
        "plan": plan,
        "limit": new_limit,
        "user": serialize_user(dict(updated_user))
    })

# ══════════════════════════════════════════════════════════════
#  プロフィール・好み
# ══════════════════════════════════════════════════════════════
@app.route("/api/profile", methods=["GET"])
@auth_required
def get_profile():
    uid = str(g.current_user["id"])
    row = db_exec("SELECT * FROM lu_profiles WHERE user_id=%s", (uid,), fetch="one")
    data = {k: safe_json(v) for k, v in dict(row).items()} if row else {}
    data.pop("user_id", None)
    return jsonify(data)

@app.route("/api/profile", methods=["PUT"])
@auth_required
def update_profile():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    allowed = ["area","transport_modes","household_size","has_children","has_pets",
               "monthly_budget","outing_budget","weekday_style","weekend_style","favorite_services",
               "interests"]
    sets, vals = [], []
    for k in allowed:
        if k in d:
            sets.append(f"{k}=%s")
            v = d[k]
            vals.append(json.dumps(v) if isinstance(v, list) else v)
    if not sets:
        return jsonify({"error": "更新フィールドがありません"}), 400
    vals.append(uid)
    db_exec(f"UPDATE lu_profiles SET {','.join(sets)},updated_at=NOW() WHERE user_id=%s", vals)
    return jsonify({"message": "プロフィールを更新しました"})

PREF_CONFIG = {
    "food":        ("lu_pref_food",       ["liked_cuisines","disliked_cuisines","liked_ingredients",
                                            "disliked_ingredients","allergies","volume_pref",
                                            "health_conscious","cooking_freq","spice_level"]),
    "shopping":    ("lu_pref_shopping",   ["liked_brands","disliked_brands","priority_price",
                                            "priority_practicality","priority_novelty","priority_reliability"]),
    "travel":      ("lu_pref_travel",     ["travel_styles","budget_range","max_travel_hours",
                                            "priority_hotel","priority_onsen","priority_scenery",
                                            "priority_station","priority_breakfast"]),
    "restaurant":  ("lu_pref_restaurant", ["liked_genres","price_range","smoking_ok",
                                            "private_room_pref","noise_pref","solo_or_group"]),
    "constraints": ("lu_constraints",     ["food_allergies","dietary_restrictions","require_non_smoking",
                                            "require_stroller_ok","require_pet_ok","hotel_blacklist",
                                            "max_meal_budget","max_hotel_budget","max_shopping_budget",
                                            "max_travel_time_min",
                                            "cannot_drive","prefers_car","mobility_notes","travel_companions"]),
    "health":      ("lu_pref_health",     ["health_goals","disliked_exercises","liked_exercises",
                                            "exercise_freq","available_time_min","health_constraints","diet_style"]),
    "diy":         ("lu_pref_diy",        ["skill_level","owned_tools","disliked_methods",
                                            "preferred_materials","past_projects","budget_range"]),
}

@app.route("/api/preferences", methods=["GET"])
@auth_required
def get_prefs():
    uid = str(g.current_user["id"])
    result = {}
    for cat, (tbl, _) in PREF_CONFIG.items():
        row  = db_exec(f"SELECT * FROM {tbl} WHERE user_id=%s", (uid,), fetch="one")
        data = {k: safe_json(v) for k, v in dict(row).items()} if row else {}
        data.pop("user_id", None); data.pop("updated_at", None)
        result[cat] = data
    return jsonify(result)

@app.route("/api/preferences/<category>", methods=["PUT"])
@auth_required
def update_prefs(category):
    if category not in PREF_CONFIG:
        return jsonify({"error": "カテゴリが不正です"}), 400
    uid = str(g.current_user["id"])
    tbl, allowed = PREF_CONFIG[category]
    d = request.json or {}
    sets, vals = [], []
    for k in allowed:
        if k in d:
            sets.append(f"{k}=%s")
            v = d[k]
            vals.append(json.dumps(v) if isinstance(v, list) else v)
    if not sets:
        return jsonify({"error": "更新フィールドがありません"}), 400
    vals.append(uid)
    db_exec(f"UPDATE {tbl} SET {','.join(sets)},updated_at=NOW() WHERE user_id=%s", vals)
    return jsonify({"message": f"{category}の好みを更新しました"})


# ══════════════════════════════════════════════════════════════
#  チャット（OpenAI × エージェント統合）
# ══════════════════════════════════════════════════════════════
@app.route("/api/chat", methods=["POST"])
@auth_required
def chat():
    user        = g.current_user
    uid         = str(user["id"])
    d           = request.json or {}
    ai_type     = d.get("ai_type", "all")
    messages_in = d.get("messages", [])
    session_id  = d.get("session_id")
    user_lat    = d.get("lat")
    user_lng    = d.get("lng")

    if not messages_in:
        return jsonify({"error": "メッセージがありません"}), 400

    limit = PLAN_LIMITS.get(user["plan"], 10)
    if user["plan"] != "master" and user["usage_count"] >= limit:
        return jsonify({"error": "usage_limit_reached", "limit": limit}), 429

    AI_NAME_MAP = {"all": None, "cooking": "recipe", "travel": "travel",
                   "shopping": "shopping", "diy": "diy", "home": "appliance", "health": "health",
                   "gourmet": "gourmet"}
    agent_name = AI_NAME_MAP.get(ai_type)

    # セッション管理
    conn = get_db()
    if not session_id:
        session_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute("INSERT INTO lu_sessions (id,user_id,ai_type) VALUES (%s,%s,%s)",
                        (session_id, uid, ai_type))
        conn.commit()

    # ユーザーメッセージ保存
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lu_messages (id,session_id,user_id,role,content,ai_type)"
                    " VALUES (%s,%s,%s,'user',%s,%s)",
                    (str(uuid.uuid4()), session_id, uid, messages_in[-1]["content"], ai_type))
    conn.commit()

    # エージェント決定
    if not agent_name:
        agent_name = route(messages_in)
    print(f"[Router] user={uid} ai_type={ai_type} → agent={agent_name}")

    # ── フォールバックモードチェック ─────────────────────────────
    # 残高ゼロ or メンテナンスモード時はシナリオベースの返答に切り替える
    if is_fallback_mode():
        from agents.fallback import run_fallback
        # セッションごとのフォールバック状態をextraフィールドに保存・復元
        fb_state = d.get("fallback_state") or {}
        fb_ai    = agent_name or ai_type
        print(f"[Fallback] run_fallback ai={fb_ai} state={fb_state}")
        fb_result = run_fallback(fb_ai, messages_in, fb_state)
        print(f"[Fallback] result reply={fb_result['reply'][:40]} next_state={fb_result['session_state']}")

        reply_text  = fb_result["reply"]
        extra       = fb_result["extra"]
        suggestions = fb_result.get("suggestions", [])

        # AIメッセージ保存
        msg_id = str(uuid.uuid4())
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lu_messages (id,session_id,user_id,role,content,ai_type,extra)"
                " VALUES (%s,%s,%s,'assistant',%s,%s,%s)",
                (msg_id, session_id, uid, reply_text, ai_type, extra_json)
            )
        conn.commit()

        # フォールバックモード中は usage_count を消費しない
        return jsonify({
            "reply":         reply_text,
            "suggestions":   suggestions,
            "extra":         extra,
            "session_id":    session_id,
            "message_id":    msg_id,
            "usage_count":   user["usage_count"],
            "fallback_mode": True,
            "fallback_state": fb_result["session_state"],
        })
    # ─────────────────────────────────────────────────────────────

    context_injection = build_context_injection(uid, agent_name)

    # グルメAI: 位置情報をコンテキストに注入
    if agent_name == "gourmet":
        geocoded_address = None

        # ① フロントから座標が来た場合はそのまま使う
        if user_lat and user_lng:
            context_injection += (
                f"\n\n【ユーザーの現在地】\n緯度: {user_lat}\n経度: {user_lng}\n"
                "※ search_restaurants を呼ぶ際はこの座標を使用してください"
            )

        # ② 座標がない場合は最新メッセージから住所テキストを抽出してGeocodingする
        else:
            last_msg = messages_in[-1]["content"] if messages_in else ""
            import re
            # 都道府県・市区町村・番地などを含む文字列を住所候補として抽出
            addr_pattern = re.search(
                r'(東京都|北海道|(?:京都|大阪)府|.{2,3}県)?'
                r'[^\s、。！？\n]*(?:市|区|町|村|丁目|番地|号)[^\s、。！？\n]*',
                last_msg
            )
            if addr_pattern:
                candidate = addr_pattern.group(0).strip()
                if len(candidate) >= 4:  # 短すぎる誤検出を除外
                    from tools.maps import geocode_address
                    geo = geocode_address(candidate)
                    if geo.get("ok"):
                        user_lat = geo["lat"]
                        user_lng = geo["lng"]
                        geocoded_address = geo.get("formatted", candidate)
                        context_injection += (
                            f"\n\n【ユーザーの現在地（住所から変換）】\n"
                            f"住所: {geocoded_address}\n"
                            f"緯度: {user_lat}\n経度: {user_lng}\n"
                            "※ search_restaurants を呼ぶ際はこの座標を使用してください"
                        )
                    else:
                        print(f"[Geocode] 変換失敗: {candidate} → {geo.get('reason')}")

    # 旅行AI: 位置情報を「出発地候補」としてコンテキストに注入
    if agent_name == "travel":
        if user_lat and user_lng:
            # 座標から都市名に逆ジオコーディングを試みる
            try:
                from tools.maps import reverse_geocode
                geo = reverse_geocode(user_lat, user_lng)
                city_name = geo.get("city") or geo.get("formatted", "")
                if city_name:
                    context_injection += (
                        f"\n\n【ユーザーの現在地（GPS取得済み）】\n"
                        f"現在地: {city_name}\n"
                        f"緯度: {user_lat} / 経度: {user_lng}\n"
                        "※ 出発地が明示されていない場合、この現在地を出発地として使用してください。\n"
                        "※ 出発地を確認する際は「現在地（{city_name}）からでよいですか？」と提案してください。"
                    )
                else:
                    context_injection += (
                        f"\n\n【ユーザーの現在地（GPS取得済み）】\n"
                        f"緯度: {user_lat} / 経度: {user_lng}\n"
                        "※ 出発地が明示されていない場合、この位置情報を出発地の参考にしてください。"
                    )
            except Exception:
                context_injection += (
                    f"\n\n【ユーザーの現在地（GPS取得済み）】\n"
                    f"緯度: {user_lat} / 経度: {user_lng}\n"
                    "※ 出発地が明示されていない場合、この位置情報を出発地の参考にしてください。"
                )

    agent = AGENT_MAP.get(agent_name)

    try:
        if agent:
            original_build = agent.build_system
            def patched_build(_):
                return original_build(uid) + "\n\n" + context_injection
            agent.build_system = patched_build
            try:
                result = agent.run(messages_in, user_id=uid)
            finally:
                # clarifier が早期 return した場合も確実に復元
                agent.build_system = original_build
        else:
            from openai import OpenAI
            client = OpenAI()
            res = client.chat.completions.create(
                model="gpt-4o", max_tokens=1200,
                messages=[{"role":"system","content":
                    f"あなたは親切な日本語AIアシスタントです。\n\n{context_injection}\n\n"
                    "## 専門AIの紹介\n""ユーザーの話題に合わせて以下の専門AIを紹介してください:\n""- 飲食店・外食 → gourmet（グルメAI）\n""- 料理レシピ → recipe（料理AI）\n""- 旅行・ホテル → travel（旅行AI）\n""- 商品購入 → shopping（買い物AI）\n""- 家電・インテリア → home（家電AI）\n""- 健康・運動 → health（健康AI）\n""- DIY・修理 → diy（DIY AI）\n\n"'必ず次のJSONのみで返答: {"ai":"general","message":"応答","suggestions":["選択肢1","選択肢2"],"redirect_to_ai":"専門AIキー名またはnull"}'}
                ] + messages_in)
            raw = res.choices[0].message.content.strip()
            try:    result = json.loads(raw.replace("```json","").replace("```","").strip())
            except: result = {"ai":"general","message":raw,"suggestions":[]}
    except Exception as e:
        print(f"[Chat Error] {e}")
        return jsonify({"error": f"AI応答エラー: {str(e)}"}), 500

    result["ai"]  = ai_type
    reply_text    = result.get("reply") or result.get("message", "")
    suggestions   = result.get("suggestions", [])
    needs_clarification = result.get("needs_clarification", False)
    redirect_to_ai = result.get("redirect_to_ai")  # 専門外AIへの誘導
    extra         = {k:v for k,v in result.items() if k not in ("ai","message","reply","suggestions","needs_clarification","redirect_to_ai","recipe")}
    msg_id_ai     = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute("INSERT INTO lu_messages (id,session_id,user_id,role,content,ai_type,extra)"
                    " VALUES (%s,%s,%s,'assistant',%s,%s,%s)",
                    (msg_id_ai, session_id, uid, reply_text, ai_type,
                     json.dumps(extra, ensure_ascii=False) if extra else None))
        cur.execute("UPDATE lu_sessions SET msg_count=msg_count+2 WHERE id=%s", (session_id,))
        # 深掘り質問中（clarifier返答）はusage_countを消費しない
        if not needs_clarification:
            cur.execute("UPDATE lu_users SET usage_count=usage_count+1 WHERE id=%s", (uid,))
    conn.commit()

    # lu_proposals に提案を自動保存（gourmet/travel/shopping等でitem情報がある場合）
    proposal_id = None
    try:
        ai_name = agent_name or "general"
        # extraにお店・商品・ホテルなどのアイテム情報があれば構造化保存
        item_name = None
        item_data = {}
        category  = ai_name

        if ai_name == "gourmet" and extra.get("restaurants"):
            top = extra["restaurants"][0] if extra["restaurants"] else None
            if top:
                item_name = top.get("name", reply_text[:60])
                item_data = {k:v for k,v in top.items() if k != "name"}
                category  = "restaurant"
        elif ai_name == "travel" and extra.get("hotels"):
            top = extra["hotels"][0] if extra["hotels"] else None
            if top:
                item_name = top.get("name", reply_text[:60])
                item_data = {k:v for k,v in top.items() if k != "name"}
                category  = "hotel"
        elif ai_name == "shopping" and extra.get("products"):
            top = extra["products"][0] if extra["products"] else None
            if top:
                item_name = top.get("name", reply_text[:60])
                item_data = {k:v for k,v in top.items() if k != "name"}
                category  = "product"
        elif ai_name == "recipe":
            # レシピ名はreply_textの先頭から推測
            item_name = reply_text[:80]
            category  = "recipe"
        elif ai_name in ("diy","appliance","health"):
            item_name = reply_text[:80]
            category  = ai_name

        if item_name:
            proposal_id = str(uuid.uuid4())
            db_exec(
                "INSERT INTO lu_proposals (id,session_id,user_id,ai_type,category,item_name,item_data,outcome) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'unknown')",
                (proposal_id, session_id, uid, ai_name, category, item_name,
                 json.dumps(item_data, ensure_ascii=False) if item_data else None)
            )
    except Exception as e:
        print(f"[Proposals] 保存スキップ: {e}")

    update_match_score(uid, agent_name or "general")
    _upsert_usage_stats(uid, agent_name or "general")

    # 初回チャット時刻を記録
    db_exec(
        "UPDATE lu_users SET first_chat_at=COALESCE(first_chat_at,NOW()), last_active_at=NOW() WHERE id=%s",
        (uid,)
    )

    return jsonify({"reply": reply_text, "suggestions": suggestions, "extra": extra,
                    "needs_clarification": needs_clarification,
                    "redirect_to_ai": redirect_to_ai,
                    "session_id": session_id, "message_id": msg_id_ai,
                    "proposal_id": proposal_id,
                    "usage_count": user["usage_count"] + 1, "agent": agent_name or "general"})


@app.route("/api/chat/feedback", methods=["POST"])
@auth_required
def feedback():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    rating = d.get("rating")
    if rating not in (1, -1):
        return jsonify({"error": "rating は 1 または -1 で指定してください"}), 400
    outcome = "accepted" if rating == 1 else "rejected"
    try:
        save_feedback(user_id=uid, ai_type=d.get("ai_type","general"),
                      session_id=d.get("session_id",""), proposal=d.get("proposal",""),
                      outcome=outcome, reason=d.get("reason",""))
    except Exception as e:
        print(f"[Feedback] {e}")
    update_match_score(uid, d.get("ai_type","general"), rating)
    # 採用/却下は別途 proposal イベントとしてスコア加算
    if outcome == "accepted":
        _apply_score_event(uid, d.get("ai_type","general"), "proposal_accepted")
    elif outcome == "rejected":
        _apply_score_event(uid, d.get("ai_type","general"), "proposal_rejected")
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════
#  lu_reactions: 感情フィードバック（5種別）
# ══════════════════════════════════════════════════════════════
REACTION_SCORE_MAP = {
    "love":      {"overall": 2.0, "ai": 3.5},   # 最高評価
    "helpful":   {"overall": 1.5, "ai": 2.5},   # 役立った
    "boring":    {"overall": 0.0, "ai": -0.3},  # 普通〜微妙
    "wrong":     {"overall": 0.0, "ai": -1.0},  # 内容が違う
    "too_long":  {"overall": 0.2, "ai":  0.3},  # 長すぎ（情報は有用）
    "too_short": {"overall": 0.2, "ai":  0.3},  # 短すぎ（改善余地）
    "off_topic": {"overall": 0.0, "ai": -0.5},  # 的外れ
}

@app.route("/api/chat/reaction", methods=["POST"])
@auth_required
def post_reaction():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    message_id = d.get("message_id")
    reaction   = d.get("reaction")
    detail     = d.get("detail", "")
    ai_type    = d.get("ai_type", "general")

    if not message_id:
        return jsonify({"error": "message_id は必須です"}), 400
    if reaction not in REACTION_SCORE_MAP:
        return jsonify({"error": f"reaction は {list(REACTION_SCORE_MAP.keys())} のいずれかです"}), 400

    # lu_reactions に保存
    rid = str(uuid.uuid4())
    db_exec(
        "INSERT INTO lu_reactions (id, message_id, user_id, reaction, detail) VALUES (%s,%s,%s,%s,%s)",
        (rid, message_id, uid, reaction, detail or None)
    )

    # 成長イベントとしてスコアを更新
    reaction_event_map = {
        "love": "reaction_love", "helpful": "reaction_helpful",
        "wrong": "reaction_wrong", "off_topic": "reaction_off_topic",
    }
    event_key = reaction_event_map.get(reaction, "chat_normal")
    _apply_score_event(uid, ai_type, event_key)

    # lu_learning_log に学習イベントとして記録（detail も保存）
    _log_learning(uid, ai_type, f"reaction_{reaction}", detail or reaction,
                  source="reaction", confidence=abs(SCORE_WEIGHTS.get(event_key, (0,0))[1]))

    # lu_usage_stats の avg_rating を更新
    _upsert_usage_stats(uid, ai_type)

    return jsonify({"ok": True, "reaction": reaction})


# ══════════════════════════════════════════════════════════════
#  lu_proposals: 提案の構造化保存
# ══════════════════════════════════════════════════════════════
@app.route("/api/proposals", methods=["POST"])
@auth_required
def save_proposal():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    required = ["ai_type", "item_name"]
    for k in required:
        if not d.get(k):
            return jsonify({"error": f"{k} は必須です"}), 400

    pid = str(uuid.uuid4())
    db_exec(
        "INSERT INTO lu_proposals (id, session_id, user_id, ai_type, category, item_name, item_data, outcome) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (pid,
         d.get("session_id"),
         uid,
         d["ai_type"],
         d.get("category", "general"),
         d["item_name"],
         json.dumps(d["item_data"], ensure_ascii=False) if d.get("item_data") else None,
         d.get("outcome", "unknown"))
    )
    return jsonify({"ok": True, "proposal_id": pid})


@app.route("/api/proposals/<pid>/outcome", methods=["PUT"])
@auth_required
def update_proposal_outcome(pid):
    uid     = str(g.current_user["id"])
    d       = request.json or {}
    outcome = d.get("outcome")
    if outcome not in ("accepted", "rejected", "ignored"):
        return jsonify({"error": "outcome は accepted/rejected/ignored のいずれかです"}), 400
    db_exec(
        "UPDATE lu_proposals SET outcome=%s, reject_reason=%s WHERE id=%s AND user_id=%s",
        (outcome, d.get("reject_reason"), pid, uid)
    )
    # proposal_historyと同様にuser_preferencesにも反映
    if outcome == "rejected":
        row = db_exec("SELECT ai_type, item_name FROM lu_proposals WHERE id=%s", (pid,), fetch="one")
        if row:
            try:
                save_feedback(user_id=uid, ai_type=row["ai_type"],
                              session_id="", proposal=row["item_name"],
                              outcome="rejected", reason=d.get("reject_reason",""))
            except Exception:
                pass
    return jsonify({"ok": True})


@app.route("/api/proposals", methods=["GET"])
@auth_required
def list_proposals():
    uid     = str(g.current_user["id"])
    ai_type = request.args.get("ai_type")
    outcome = request.args.get("outcome")
    limit   = min(int(request.args.get("limit", 20)), 100)

    where, params = ["user_id=%s"], [uid]
    if ai_type: where.append("ai_type=%s"); params.append(ai_type)
    if outcome: where.append("outcome=%s"); params.append(outcome)
    params.append(limit)

    rows = db_exec(
        f"SELECT id,ai_type,category,item_name,item_data,outcome,reject_reason,created_at "
        f"FROM lu_proposals WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT %s",
        params, fetch="all"
    ) or []
    result = []
    for r in rows:
        p = dict(r); p["id"] = str(p["id"])
        p["created_at"] = p["created_at"].isoformat() if p.get("created_at") else None
        if p.get("item_data") and isinstance(p["item_data"], str):
            try: p["item_data"] = json.loads(p["item_data"])
            except: pass
        result.append(p)
    return jsonify({"proposals": result})


# ══════════════════════════════════════════════════════════════
#  lu_action_logs: ユーザーの実行動記録
# ══════════════════════════════════════════════════════════════
VALID_ACTION_TYPES = ("visited","cooked","purchased","booked","diy_done","exercised","other")

@app.route("/api/actions", methods=["POST"])
@auth_required
def log_action():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    if not d.get("action_type") or d["action_type"] not in VALID_ACTION_TYPES:
        return jsonify({"error": f"action_type は {VALID_ACTION_TYPES} のいずれかです"}), 400
    if not d.get("ai_type"):
        return jsonify({"error": "ai_type は必須です"}), 400

    aid = str(uuid.uuid4())
    db_exec(
        "INSERT INTO lu_action_logs (id, user_id, ai_type, proposal_id, action_type, note, actioned_at) "
        "VALUES (%s,%s,%s,%s,%s,%s, NOW())",
        (aid, uid, d["ai_type"], d.get("proposal_id"), d["action_type"], d.get("note"))
    )

    # 実際に行動した = 最大重みの成長イベント
    _apply_score_event(uid, d["ai_type"], "action_done")

    # 行動ログを学習イベントとして記録
    _log_learning(uid, d["ai_type"], f"action_{d['action_type']}",
                  d.get("note","実行"), source="feedback", confidence=4.0)

    # proposal が存在すれば accepted に更新
    if d.get("proposal_id"):
        db_exec("UPDATE lu_proposals SET outcome='accepted' WHERE id=%s AND user_id=%s",
                (d["proposal_id"], uid))

    return jsonify({"ok": True, "action_id": aid})


@app.route("/api/actions", methods=["GET"])
@auth_required
def list_actions():
    uid     = str(g.current_user["id"])
    ai_type = request.args.get("ai_type")
    limit   = min(int(request.args.get("limit", 20)), 100)
    where, params = ["a.user_id=%s"], [uid]
    if ai_type: where.append("a.ai_type=%s"); params.append(ai_type)
    params.append(limit)
    rows = db_exec(
        f"SELECT a.id,a.ai_type,a.action_type,a.note,a.actioned_at,"
        f"p.item_name as proposal_name "
        f"FROM lu_action_logs a LEFT JOIN lu_proposals p ON a.proposal_id=p.id "
        f"WHERE {' AND '.join(where)} ORDER BY a.actioned_at DESC LIMIT %s",
        params, fetch="all"
    ) or []
    result = []
    for r in rows:
        rec = dict(r); rec["id"] = str(rec["id"])
        rec["actioned_at"] = rec["actioned_at"].isoformat() if rec.get("actioned_at") else None
        result.append(rec)
    return jsonify({"actions": result})


# ══════════════════════════════════════════════════════════════
#  lu_usage_stats / lu_learning_log ヘルパー
# ══════════════════════════════════════════════════════════════
def _upsert_usage_stats(user_id: str, ai_type: str):
    """日次集計を更新（会話数・平均評価）"""
    try:
        db_exec(
            "INSERT INTO lu_usage_stats (id, user_id, ai_type, date, msg_count) "
            "VALUES (gen_random_uuid(), %s, %s, CURRENT_DATE, 1) "
            "ON CONFLICT (user_id, ai_type, date) DO UPDATE SET "
            "msg_count = lu_usage_stats.msg_count + 1",
            (user_id, ai_type)
        )
        # avg_rating を lu_reactions から再計算
        db_exec(
            "UPDATE lu_usage_stats us SET avg_rating = ("
            "  SELECT AVG(CASE reaction "
            "    WHEN 'love' THEN 5 WHEN 'helpful' THEN 4 "
            "    WHEN 'boring' THEN 2 WHEN 'wrong' THEN 1 "
            "    WHEN 'off_topic' THEN 1 ELSE 3 END) "
            "  FROM lu_reactions r JOIN lu_messages m ON r.message_id=m.id "
            "  WHERE r.user_id=%s AND m.ai_type=%s "
            "    AND DATE(r.created_at)=CURRENT_DATE"
            ") WHERE us.user_id=%s AND us.ai_type=%s AND us.date=CURRENT_DATE",
            (user_id, ai_type, user_id, ai_type)
        )
        # lu_users.last_active_at / favorite_ai を更新
        db_exec(
            "UPDATE lu_users SET last_active_at=NOW(), "
            "first_chat_at=COALESCE(first_chat_at, NOW()), "
            "total_sessions=COALESCE(total_sessions,0)+1, "
            "favorite_ai=("
            "  SELECT ai_type FROM lu_usage_stats "
            "  WHERE user_id=%s GROUP BY ai_type ORDER BY SUM(msg_count) DESC LIMIT 1"
            ") WHERE id=%s",
            (user_id, user_id)
        )
    except Exception as e:
        print(f"[UsageStats] {e}")


def _log_learning(user_id: str, ai_type: str, key: str, val: str,
                  source: str = "conversation", confidence: float = 1.0):
    """lu_learning_log に学習イベントを記録"""
    try:
        db_exec(
            "INSERT INTO lu_learning_log (id, user_id, ai_type, learned_key, learned_val, source, confidence) "
            "VALUES (gen_random_uuid(),%s,%s,%s,%s,%s,%s)",
            (user_id, ai_type, key, val, source, confidence)
        )
    except Exception as e:
        print(f"[LearningLog] {e}")


@app.route("/api/usage-stats", methods=["GET"])
@auth_required
def get_usage_stats():
    uid  = str(g.current_user["id"])
    days = min(int(request.args.get("days", 30)), 90)
    rows = db_exec(
        "SELECT ai_type, date, msg_count, avg_rating "
        "FROM lu_usage_stats WHERE user_id=%s AND date >= CURRENT_DATE - %s::int "
        "ORDER BY date DESC, msg_count DESC",
        (uid, days), fetch="all"
    ) or []
    result = []
    for r in rows:
        rec = dict(r)
        rec["date"] = rec["date"].isoformat() if rec.get("date") else None
        if rec.get("avg_rating"): rec["avg_rating"] = round(rec["avg_rating"], 2)
        result.append(rec)
    return jsonify({"stats": result, "days": days})


# ══════════════════════════════════════════════════════════════
#  lu_favorites: お気に入り登録・一覧・削除
# ══════════════════════════════════════════════════════════════
@app.route("/api/favorites", methods=["POST"])
@auth_required
def add_favorite():
    uid = str(g.current_user["id"])
    d   = request.json or {}
    if not d.get("title"):
        return jsonify({"error": "title は必須です"}), 400
    fid = str(uuid.uuid4())
    db_exec(
        "INSERT INTO lu_favorites (id,user_id,ai_type,category,title,subtitle,detail,source_url,note) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (fid, uid,
         d.get("ai_type","general"), d.get("category","general"),
         d["title"], d.get("subtitle"),
         json.dumps(d["detail"], ensure_ascii=False) if d.get("detail") else None,
         d.get("source_url"), d.get("note"))
    )
    return jsonify({"ok": True, "favorite_id": fid})

@app.route("/api/favorites", methods=["GET"])
@auth_required
def list_favorites():
    uid = str(g.current_user["id"])
    ai_type  = request.args.get("ai_type")
    category = request.args.get("category")
    limit    = min(int(request.args.get("limit", 50)), 200)
    where, params = ["user_id=%s"], [uid]
    if ai_type:  where.append("ai_type=%s");  params.append(ai_type)
    if category: where.append("category=%s"); params.append(category)
    params.append(limit)
    rows = db_exec(
        f"SELECT id,ai_type,category,title,subtitle,detail,source_url,note,created_at "
        f"FROM lu_favorites WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT %s",
        params, fetch="all"
    ) or []
    result = []
    for r in rows:
        rec = dict(r); rec["id"] = str(rec["id"])
        rec["created_at"] = rec["created_at"].isoformat() if rec.get("created_at") else None
        if rec.get("detail") and isinstance(rec["detail"], str):
            try: rec["detail"] = json.loads(rec["detail"])
            except: pass
        result.append(rec)
    return jsonify({"favorites": result})

@app.route("/api/favorites/<fid>", methods=["DELETE"])
@auth_required
def delete_favorite(fid):
    uid = str(g.current_user["id"])
    db_exec("DELETE FROM lu_favorites WHERE id=%s AND user_id=%s", (fid, uid))
    return jsonify({"ok": True})

@app.route("/api/favorites/<fid>/note", methods=["PUT"])
@auth_required
def update_favorite_note(fid):
    uid  = str(g.current_user["id"])
    note = (request.json or {}).get("note","")
    db_exec("UPDATE lu_favorites SET note=%s WHERE id=%s AND user_id=%s", (note, fid, uid))
    return jsonify({"ok": True})


@app.route("/api/chat/sessions/<sid>/messages", methods=["GET"])
@auth_required
def get_session_messages(sid):
    """セッションの全メッセージを返す（会話の続き機能用）"""
    uid = str(g.current_user["id"])
    # セッションの所有者確認
    session = db_exec(
        "SELECT id, ai_type, title FROM lu_sessions WHERE id=%s AND user_id=%s",
        (sid, uid), fetch="one"
    )
    if not session:
        return jsonify({"error": "セッションが見つかりません"}), 404

    rows = db_exec(
        "SELECT role, content, ai_type, extra, created_at "
        "FROM lu_messages WHERE session_id=%s ORDER BY created_at ASC",
        (sid,), fetch="all"
    ) or []

    messages = []
    for r in rows:
        m = {
            "role":    r["role"],
            "content": r["content"],
            "ai_type": r["ai_type"],
        }
        # extraフィールド（ホテル・プランなどのカード表示用データ）
        if r.get("extra"):
            try:
                m["extra"] = json.loads(r["extra"]) if isinstance(r["extra"], str) else r["extra"]
            except Exception:
                pass
        if r.get("created_at"):
            m["created_at"] = r["created_at"].isoformat()
        messages.append(m)

    return jsonify({
        "session": {
            "id":      str(session["id"]),
            "ai_type": session["ai_type"],
            "title":   session["title"],
        },
        "messages": messages,
    })


@app.route("/api/chat/sessions", methods=["GET"])
@auth_required
def list_sessions():
    uid   = str(g.current_user["id"])
    limit = min(int(request.args.get("limit", 20)), 100)
    rows  = db_exec("SELECT id,ai_type,title,msg_count,started_at FROM lu_sessions"
                    " WHERE user_id=%s ORDER BY started_at DESC LIMIT %s", (uid, limit), fetch="all")
    sessions = []
    for r in (rows or []):
        s = dict(r); s["id"] = str(s["id"])
        s["started_at"] = s["started_at"].isoformat() if s.get("started_at") else None
        sessions.append(s)
    return jsonify({"sessions": sessions})

@app.route("/api/match-score", methods=["GET"])
@auth_required
def match_score():
    uid = str(g.current_user["id"])
    row = db_exec("SELECT * FROM lu_match_scores WHERE user_id=%s", (uid,), fetch="one")
    if not row:
        return jsonify({"overall_score":0,"total_sessions":0,"details":{}})
    r = dict(row)
    return jsonify({
        "overall_score":     round(r.get("overall_score",0),1),
        "total_sessions":    r.get("total_sessions",0),
        "helpful_count":     r.get("helpful_count",0),
        "not_helpful_count": r.get("not_helpful_count",0),
        "details": {"food":    round(r.get("food_score",0),1),
                    "travel":  round(r.get("travel_score",0),1),
                    "shopping":round(r.get("shopping_score",0),1),
                    "health":  round(r.get("health_score",0),1),
                    "home":    round(r.get("home_score",0),1),
                    "diy":     round(r.get("diy_score",0),1)},
        "last_updated": r["last_updated"].isoformat() if r.get("last_updated") else None,
    })

@app.route("/api/dashboard", methods=["GET"])
@auth_required
def dashboard():
    user = g.current_user
    uid  = str(user["id"])
    score_row = db_exec("SELECT * FROM lu_match_scores WHERE user_id=%s", (uid,), fetch="one")
    score = dict(score_row) if score_row else {}
    rows  = db_exec("SELECT id,ai_type,title,msg_count,started_at FROM lu_sessions"
                    " WHERE user_id=%s ORDER BY started_at DESC LIMIT 5", (uid,), fetch="all")
    recent = []
    for r in (rows or []):
        s = dict(r); s["id"] = str(s["id"])
        s["started_at"] = s["started_at"].isoformat() if s.get("started_at") else None
        recent.append(s)
    return jsonify({"user": serialize_user(user),
                    "match_score":    round(score.get("overall_score",0),1),
                    "total_sessions": score.get("total_sessions",0),
                    "usage": {"count": user["usage_count"],
                              "limit": PLAN_LIMITS.get(user["plan"],10),
                              "pct":   round(user["usage_count"]/PLAN_LIMITS.get(user["plan"],10)*100)},
                    "recent_sessions": recent})


# ══════════════════════════════════════════════════════════════
#  管理者 API
# ══════════════════════════════════════════════════════════════

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    d = request.json or {}
    email = d.get("email","").strip().lower()
    pw    = d.get("password","")
    user  = db_exec("SELECT * FROM lu_users WHERE email=%s AND is_admin=TRUE AND is_active=TRUE",
                    (email,), fetch="one")
    if not user or not check_pw(pw, user["password_hash"]):
        return jsonify({"error": "メールアドレスまたはパスワードが違います"}), 401
    token = create_token(str(user["id"]))
    return jsonify({"token": token, "admin": {"id": str(user["id"]), "email": user["email"], "nickname": user["nickname"]}})

@app.route("/api/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    """管理者ダッシュボード: KPI・ユーザー統計・API費用サマリー"""
    # ユーザー統計
    total_users  = db_exec("SELECT COUNT(*) as c FROM lu_users WHERE is_active=TRUE AND is_admin=FALSE", fetch="one")["c"]
    plan_counts  = db_exec("SELECT plan, COUNT(*) as c FROM lu_users WHERE is_active=TRUE AND is_admin=FALSE GROUP BY plan", fetch="all")
    new_today    = db_exec("SELECT COUNT(*) as c FROM lu_users WHERE DATE(created_at)=CURRENT_DATE AND is_admin=FALSE", fetch="one")["c"]
    new_month    = db_exec("SELECT COUNT(*) as c FROM lu_users WHERE DATE_TRUNC('month',created_at)=DATE_TRUNC('month',CURRENT_DATE) AND is_admin=FALSE", fetch="one")["c"]
    # セッション統計
    total_chats  = db_exec("SELECT COUNT(*) as c FROM lu_sessions", fetch="one")["c"]
    chats_today  = db_exec("SELECT COUNT(*) as c FROM lu_sessions WHERE DATE(started_at)=CURRENT_DATE", fetch="one")["c"]
    # 月間チャット数（直近6ヶ月）
    monthly_chats = db_exec(
        "SELECT TO_CHAR(DATE_TRUNC('month',started_at),'YYYY-MM') as month, COUNT(*) as c "
        "FROM lu_sessions WHERE started_at >= NOW() - INTERVAL '6 months' "
        "GROUP BY month ORDER BY month", fetch="all") or []
    # APIコスト
    budget_row   = db_exec("SELECT value FROM admin_settings WHERE key='monthly_budget_usd'", fetch="one")
    budget_usd   = float(budget_row["value"]) if budget_row else 100.0
    cost_row     = db_exec("SELECT SUM(cost_usd) as total FROM admin_cost_logs WHERE month=TO_CHAR(CURRENT_DATE,'YYYY-MM')", fetch="one")
    cost_usd     = float(cost_row["total"] or 0) if cost_row else 0.0
    # チャージ残高
    charged_total = db_exec("SELECT SUM(amount_usd) as total FROM admin_openai_budget", fetch="one")
    charged_usd   = float(charged_total["total"] or 0) if charged_total else 0.0
    # システム設定
    settings_rows = db_exec("SELECT key,value FROM admin_settings", fetch="all") or []
    settings = {r["key"]: r["value"] for r in settings_rows}

    plans = {r["plan"]: r["c"] for r in (plan_counts or [])}
    return jsonify({
        "users": {"total": total_users, "new_today": new_today, "new_month": new_month,
                  "plans": {"free": plans.get("free",0), "pro": plans.get("pro",0), "master": plans.get("master",0)}},
        "chats": {"total": total_chats, "today": chats_today,
                  "monthly": [{"month": r["month"], "count": r["c"]} for r in monthly_chats]},
        "cost":  {"budget_usd": budget_usd, "used_usd": cost_usd,
                  "charged_usd": charged_usd, "balance_usd": charged_usd - cost_usd,
                  "used_pct": round(cost_usd / budget_usd * 100, 1) if budget_usd else 0},
        "settings": settings,
    })

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    page  = max(1, int(request.args.get("page", 1)))
    limit = min(int(request.args.get("limit", 20)), 100)
    q     = request.args.get("q", "").strip()
    plan  = request.args.get("plan", "")
    offset = (page - 1) * limit
    where = "WHERE u.is_admin=FALSE"
    params = []
    if q:
        where += " AND (u.email ILIKE %s OR u.nickname ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if plan:
        where += " AND u.plan=%s"; params.append(plan)
    total = db_exec(f"SELECT COUNT(*) as c FROM lu_users u {where}", params or None, fetch="one")["c"]
    rows  = db_exec(
        f"SELECT u.id,u.nickname,u.email,u.plan,u.usage_count,u.is_active,u.created_at,"
        f" COALESCE(ms.total_sessions,0) as total_sessions"
        f" FROM lu_users u LEFT JOIN lu_match_scores ms ON ms.user_id=u.id"
        f" {where} ORDER BY u.created_at DESC LIMIT %s OFFSET %s",
        (params or []) + [limit, offset], fetch="all") or []
    users = []
    for r in rows:
        u = dict(r)
        u["id"] = str(u["id"])
        u["created_at"] = u["created_at"].isoformat() if u.get("created_at") else None
        users.append(u)
    return jsonify({"users": users, "total": total, "page": page, "pages": -(-total // limit)})

@app.route("/api/admin/users/<uid>", methods=["GET"])
@admin_required
def admin_get_user(uid):
    user = db_exec("SELECT * FROM lu_users WHERE id=%s AND is_admin=FALSE", (uid,), fetch="one")
    if not user:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    u = dict(user)
    u["id"] = str(u["id"])
    u.pop("password_hash", None)
    u["created_at"] = u["created_at"].isoformat() if u.get("created_at") else None
    sessions = db_exec("SELECT id,ai_type,msg_count,started_at FROM lu_sessions WHERE user_id=%s ORDER BY started_at DESC LIMIT 10", (uid,), fetch="all") or []
    sess = []
    for s in sessions:
        sv = dict(s); sv["id"] = str(sv["id"])
        sv["started_at"] = sv["started_at"].isoformat() if sv.get("started_at") else None
        sess.append(sv)
    return jsonify({"user": u, "sessions": sess})

@app.route("/api/admin/users/<uid>/plan", methods=["PUT"])
@admin_required
def admin_change_plan(uid):
    plan = (request.json or {}).get("plan")
    if plan not in ("free","pro","master"):
        return jsonify({"error": "プランが無効です"}), 400
    db_exec("UPDATE lu_users SET plan=%s, updated_at=NOW() WHERE id=%s AND is_admin=FALSE", (plan, uid))
    return jsonify({"ok": True})

@app.route("/api/admin/users/<uid>/deactivate", methods=["POST"])
@admin_required
def admin_deactivate_user(uid):
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE lu_users SET is_active=FALSE, updated_at=NOW() WHERE id=%s AND is_admin=FALSE",
                (uid,)
            )
            affected = cur.rowcount
        conn.commit()
        print(f"[Admin] deactivate uid={uid} affected={affected}")
        if affected == 0:
            return jsonify({"ok": False, "error": "対象ユーザーが見つかりません（管理者アカウントは変更不可）"}), 404
        return jsonify({"ok": True, "is_active": False})
    except Exception as e:
        print(f"[Admin] deactivate error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/users/<uid>/reactivate", methods=["POST"])
@admin_required
def admin_reactivate_user(uid):
    """停止中のアカウントを再有効化する"""
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE lu_users SET is_active=TRUE, updated_at=NOW() WHERE id=%s AND is_admin=FALSE",
                (uid,)
            )
            affected = cur.rowcount
        conn.commit()
        print(f"[Admin] reactivate uid={uid} affected={affected}")
        if affected == 0:
            return jsonify({"ok": False, "error": "対象ユーザーが見つかりません（管理者アカウントは変更不可）"}), 404
        return jsonify({"ok": True, "is_active": True})
    except Exception as e:
        print(f"[Admin] reactivate error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/users/<uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # 存在確認
            cur.execute("SELECT id, nickname FROM lu_users WHERE id=%s AND is_admin=FALSE", (uid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "ユーザーが見つかりません（管理者アカウントは削除不可）"}), 404
            nickname = row["nickname"] if row else "?"
            # 削除実行
            cur.execute("DELETE FROM lu_users WHERE id=%s AND is_admin=FALSE", (uid,))
            affected = cur.rowcount
        conn.commit()
        print(f"[Admin] deleted uid={uid} nickname={nickname} affected={affected}")
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[Admin] delete error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/costs", methods=["GET"])
@admin_required
def admin_costs():
    months = int(request.args.get("months", 6))
    rows   = db_exec(
        "SELECT month, model, SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens, SUM(cost_usd) as cost_usd "
        "FROM admin_cost_logs WHERE recorded_at >= NOW() - INTERVAL '%s months' "
        "GROUP BY month, model ORDER BY month DESC", (months,), fetch="all") or []
    charges = db_exec(
        "SELECT id, amount_usd, note, card_last4, charged_at FROM admin_openai_budget ORDER BY charged_at DESC LIMIT 30",
        fetch="all") or []
    ch_list = []
    for c in charges:
        cv = dict(c); cv["id"] = str(cv["id"])
        cv["charged_at"] = cv["charged_at"].isoformat() if cv.get("charged_at") else None
        ch_list.append(cv)
    cost_list = [{"month": r["month"], "model": r["model"],
                  "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
                  "cost_usd": float(r["cost_usd"] or 0)} for r in rows]
    return jsonify({"costs": cost_list, "charges": ch_list})

@app.route("/api/admin/charges", methods=["POST"])
@admin_required
def admin_add_charge():
    d = request.json or {}
    amount = float(d.get("amount_usd", 0))
    if amount == 0:
        return jsonify({"error": "金額が無効です"}), 400
    # マイナス値は残高調整として許可（理由メモ必須）
    if amount < 0 and not d.get("note", "").strip():
        return jsonify({"error": "残高調整にはメモ（理由）が必須です"}), 400
    db_exec("INSERT INTO admin_openai_budget(amount_usd,note,charged_by,card_last4) VALUES(%s,%s,%s,%s)",
            (amount, d.get("note",""), str(g.current_user["id"]), d.get("card_last4")))
    # チャージ後に残高を再チェック → フォールバックモードを自動解除
    _check_and_update_fallback_mode()
    return jsonify({"ok": True, "fallback_mode": is_fallback_mode()})

@app.route("/api/admin/cards", methods=["GET"])
@admin_required
def admin_get_cards():
    cards = db_exec("SELECT * FROM admin_cards ORDER BY is_default DESC, added_at DESC", fetch="all") or []
    return jsonify({"cards": [dict(c) for c in cards]})

@app.route("/api/admin/cards", methods=["POST"])
@admin_required
def admin_add_card():
    d = request.json or {}
    db_exec("UPDATE admin_cards SET is_default=FALSE")
    db_exec("INSERT INTO admin_cards(card_last4,card_brand,exp_month,exp_year,is_default) VALUES(%s,%s,%s,%s,TRUE)",
            (d.get("card_last4"), d.get("card_brand","Visa"), d.get("exp_month"), d.get("exp_year")))
    return jsonify({"ok": True})

@app.route("/api/admin/cards/<cid>", methods=["DELETE"])
@admin_required
def admin_delete_card(cid):
    db_exec("DELETE FROM admin_cards WHERE id=%s", (cid,))
    return jsonify({"ok": True})

@app.route("/api/admin/settings", methods=["GET"])
@admin_required
def admin_get_settings():
    rows = db_exec("SELECT key,value,updated_at FROM admin_settings", fetch="all") or []
    return jsonify({"settings": {r["key"]: r["value"] for r in rows}})

@app.route("/api/admin/settings", methods=["PUT"])
@admin_required
def admin_update_settings():
    d = request.json or {}
    for key, val in d.items():
        db_exec("INSERT INTO admin_settings(key,value,updated_at) VALUES(%s,%s,NOW()) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()", (key, str(val)))
    return jsonify({"ok": True})

@app.route("/api/admin/usage-log", methods=["GET"])
@admin_required
def admin_usage_log():
    limit = min(int(request.args.get("limit", 50)), 200)
    ai_type = request.args.get("ai_type", "")
    where = "WHERE 1=1"
    params = []
    if ai_type:
        where += " AND m.ai_type=%s"; params.append(ai_type)
    rows = db_exec(
        f"SELECT u.email, u.plan, m.ai_type, m.role, LEFT(m.content,80) as preview, m.created_at "
        f"FROM lu_messages m JOIN lu_users u ON u.id=m.user_id {where} "
        f"ORDER BY m.created_at DESC LIMIT %s",
        params + [limit], fetch="all") or []
    logs = []
    for r in rows:
        rv = dict(r)
        rv["created_at"] = rv["created_at"].isoformat() if rv.get("created_at") else None
        logs.append(rv)
    return jsonify({"logs": logs})

@app.route("/api/setup-admin", methods=["POST"])
def setup_admin():
    """一時的な管理者作成エンドポイント（初期セットアップ用）"""
    setup_key = os.getenv("SETUP_KEY", "")
    if not setup_key:
        return jsonify({"error": "SETUP_KEY が未設定です"}), 403
    d = request.json or {}
    if d.get("setup_key") != setup_key:
        return jsonify({"error": "setup_key が違います"}), 403
    email    = d.get("email", "").strip().lower()
    password = d.get("password", "")
    nickname = d.get("nickname", "Admin")
    if not email or not password:
        return jsonify({"error": "email と password は必須です"}), 400
    existing = db_exec("SELECT id FROM lu_users WHERE email=%s", (email,), fetch="one")
    if existing:
        db_exec("UPDATE lu_users SET is_admin=TRUE, password_hash=%s, is_active=TRUE WHERE email=%s",
                (hash_pw(password), email))
        return jsonify({"ok": True, "action": "upgraded", "email": email})
    db_exec("INSERT INTO lu_users(nickname,email,password_hash,plan,is_admin) VALUES(%s,%s,%s,'master',TRUE)",
            (nickname, email, hash_pw(password)))
    return jsonify({"ok": True, "action": "created", "email": email})

@app.route("/api/admin/ai-usage", methods=["GET"])
@admin_required
def admin_ai_usage():
    """AI別セッション数（当月）をDBから集計"""
    rows = db_exec(
        "SELECT ai_type, COUNT(*) as c FROM lu_sessions "
        "WHERE DATE_TRUNC('month', started_at) = DATE_TRUNC('month', CURRENT_DATE) "
        "GROUP BY ai_type", fetch="all") or []
    counts = {r["ai_type"]: r["c"] for r in rows}
    return jsonify({"counts": counts})

# ── OpenAI モデル別コスト定義（$/1M tokens）───────────────────
OPENAI_MODEL_COSTS = {
    "gpt-4o":                     {"input": 2.50,  "output": 10.00},
    "gpt-4o-2024-11-20":          {"input": 2.50,  "output": 10.00},
    "gpt-4o-2024-08-06":          {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":                {"input": 0.15,  "output": 0.60},
    "gpt-4o-mini-2024-07-18":     {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":                {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-2024-04-09":     {"input": 10.00, "output": 30.00},
    "gpt-4":                      {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo":              {"input": 0.50,  "output": 1.50},
    "gpt-3.5-turbo-0125":         {"input": 0.50,  "output": 1.50},
    "o1":                         {"input": 15.00, "output": 60.00},
    "o1-mini":                    {"input": 3.00,  "output": 12.00},
    "o3-mini":                    {"input": 1.10,  "output": 4.40},
    "_default":                   {"input": 2.50,  "output": 10.00},
}

def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """モデル名からコストを計算（$/1M tokens）"""
    # モデル名の部分一致でコストを検索
    for key in OPENAI_MODEL_COSTS:
        if key != "_default" and key in model:
            rates = OPENAI_MODEL_COSTS[key]
            return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    rates = OPENAI_MODEL_COSTS["_default"]
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

def _fetch_openai_usage(api_key: str, start_date: str, end_date: str) -> dict:
    """
    OpenAI Usage API を呼び出してトークン使用量を取得する。
    2025年以降の仕様変更対応版：UNIXタイムスタンプ形式で呼び出す
    """
    import urllib.request, urllib.error
    from datetime import datetime
    errors = []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # ── ① 新仕様 /v1/organization/usage/completions（UNIXタイムスタンプ） ──
    try:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_dt   = datetime.strptime(end_date, "%Y-%m-%d")
        end_ts   = int(end_dt.replace(hour=23, minute=59, second=59).timestamp())

        url = (
            f"https://api.openai.com/v1/organization/usage/completions"
            f"?start_time={start_ts}&end_time={end_ts}"
            f"&group_by=model&limit=100"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        by_model = {}
        for bucket in data.get("data", []):
            for result in bucket.get("results", []):
                model = result.get("model", "unknown")
                if model not in by_model:
                    by_model[model] = {"input": 0, "output": 0, "requests": 0}
                by_model[model]["input"]    += result.get("input_tokens", 0)
                by_model[model]["output"]   += result.get("output_tokens", 0)
                by_model[model]["requests"] += result.get("num_model_requests", 0)
        print(f"[OpenAI Usage] organization/usage 成功: {len(by_model)}モデル")
        return {"ok": True, "source": "v2_org", "by_model": by_model}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        err_detail = f"v2_org HTTP{e.code}: {body}"
        errors.append(err_detail)
        print(f"[OpenAI Usage] {err_detail}")
    except Exception as e:
        errors.append(f"v2_org: {e}")
        print(f"[OpenAI Usage] v2_org エラー: {e}")

    # ── ② 旧API /v1/usage（まだ動く環境向けフォールバック） ──
    try:
        url = f"https://api.openai.com/v1/usage?date={start_date}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        by_model = {}
        for item in data.get("data", []):
            model = item.get("snapshot_id", item.get("model", "unknown"))
            if model not in by_model:
                by_model[model] = {"input": 0, "output": 0, "requests": 0}
            by_model[model]["input"]    += item.get("n_context_tokens_total", 0)
            by_model[model]["output"]   += item.get("n_generated_tokens_total", 0)
            by_model[model]["requests"] += item.get("n_requests", 0)
        if by_model:
            print(f"[OpenAI Usage] v1/usage 成功: {len(by_model)}モデル")
            return {"ok": True, "source": "v1_legacy", "by_model": by_model}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        errors.append(f"v1_legacy HTTP{e.code}: {body}")
        print(f"[OpenAI Usage] v1/usage HTTP{e.code}: {body}")
    except Exception as e:
        errors.append(f"v1_legacy: {e}")

    # ── ③ Billing API（最終フォールバック） ──
    try:
        url = (
            f"https://api.openai.com/v1/dashboard/billing/usage"
            f"?start_date={start_date}&end_date={end_date}"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        total_cents = data.get("total_usage", 0)
        print(f"[OpenAI Usage] billing API 成功: ${total_cents/100:.4f}")
        return {
            "ok": True,
            "source": "billing",
            "cost_usd_direct": round(total_cents / 100, 4),
            "by_model": {},
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        errors.append(f"billing HTTP{e.code}: {body}")
        print(f"[OpenAI Usage] billing HTTP{e.code}: {body}")
    except Exception as e:
        errors.append(f"billing: {e}")

    print(f"[OpenAI Usage] 全エンドポイント失敗: {errors}")
    return {"ok": False, "errors": errors}


@app.route("/api/admin/openai-usage", methods=["GET"])
@admin_required
def admin_openai_usage():
    """
    自前トークン記録から使用量・コストを集計して返す。
    OpenAI Usage APIへの接続は不要（チャットのたびにbase.pyが記録したデータを使用）。
    """
    import calendar
    from datetime import date

    today     = date.today()
    month_str = request.args.get("month")  # YYYY-MM 形式

    if month_str:
        try:
            y, m   = int(month_str[:4]), int(month_str[5:7])
            target_month = f"{y:04d}-{m:02d}"
            start  = f"{y:04d}-{m:02d}-01"
            last_d = calendar.monthrange(y, m)[1]
            end    = f"{y:04d}-{m:02d}-{last_d:02d}"
        except Exception:
            target_month = today.strftime("%Y-%m")
            start = today.replace(day=1).strftime("%Y-%m-%d")
            end   = today.strftime("%Y-%m-%d")
    else:
        target_month = today.strftime("%Y-%m")
        start = today.replace(day=1).strftime("%Y-%m-%d")
        end   = today.strftime("%Y-%m-%d")

    # admin_cost_logs から対象月のデータを集計
    rows = db_exec(
        """SELECT model,
                  SUM(input_tokens)  AS input_tokens,
                  SUM(output_tokens) AS output_tokens,
                  SUM(cost_usd)      AS cost_usd,
                  COUNT(*)           AS requests
           FROM admin_cost_logs
           WHERE month = %s
           GROUP BY model
           ORDER BY SUM(cost_usd) DESC""",
        (target_month,), fetch="all"
    ) or []

    # モデル別詳細
    models_detail = []
    total_input = total_output = total_reqs = 0
    total_cost  = 0.0

    for r in rows:
        inp  = int(r["input_tokens"]  or 0)
        out  = int(r["output_tokens"] or 0)
        cost = float(r["cost_usd"]    or 0)
        reqs = int(r["requests"]      or 0)
        total_input  += inp
        total_output += out
        total_cost   += cost
        total_reqs   += reqs
        models_detail.append({
            "model":         r["model"],
            "input_tokens":  inp,
            "output_tokens": out,
            "requests":      reqs,
            "cost_usd":      round(cost, 4),
            "cost_jpy":      round(cost * 150),
        })

    # 予算との比較
    budget_row = db_exec("SELECT value FROM admin_settings WHERE key='monthly_budget_usd'", fetch="one")
    budget_usd = float(budget_row["value"]) if budget_row else 100.0
    used_pct   = round(total_cost / budget_usd * 100, 1) if budget_usd else 0

    return jsonify({
        "ok":    True,
        "source": "self_recorded",  # 自前記録であることを明示
        "period": {"start": start, "end": end},
        "total": {
            "input_tokens":  total_input,
            "output_tokens": total_output,
            "requests":      total_reqs,
            "cost_usd":      round(total_cost, 4),
            "cost_jpy":      round(total_cost * 150),
        },
        "budget": {
            "budget_usd": budget_usd,
            "used_pct":   used_pct,
        },
        "models":        models_detail,
        "dashboard_url": "https://platform.openai.com/usage",
        # 後方互換フィールド
        "input_tokens":  total_input,
        "output_tokens": total_output,
        "cost_usd":      round(total_cost, 4),
        "cost_jpy":      round(total_cost * 150),
    })

@app.route("/api/health", methods=["GET"])
def health_check():
    try: db_exec("SELECT 1"); db_ok=True
    except Exception: db_ok=False
    return jsonify({
        "status":      "ok" if db_ok else "degraded",
        "db":          "connected" if db_ok else "error",
        "openai":      "configured" if os.getenv("OPENAI_API_KEY") else "⚠ 未設定",
        "rakuten":     "configured" if os.getenv("RAKUTEN_APP_ID") else "未設定（任意）",
        "google_maps": "configured" if os.getenv("GOOGLE_MAPS_API_KEY") else "未設定（任意）",
    })


# ══════════════════════════════════════════════════════════════
#  フロントエンド用公開設定（APIキー等）
# ══════════════════════════════════════════════════════════════
def _get_budget_warning() -> str:
    """現在の予算警告レベルを返す（none/warning/critical）"""
    try:
        row = db_exec("SELECT value FROM admin_settings WHERE key='budget_warning_mode'", fetch="one")
        return row["value"] if row else "none"
    except Exception:
        return "none"

@app.route("/api/config", methods=["GET"])
def get_frontend_config():
    """フロントエンドが楽天APIを直接叩くために必要な公開設定を返す"""
    return jsonify({
        "rakuten_app_id":  os.getenv("RAKUTEN_APP_ID", ""),
        "fallback_mode":   is_fallback_mode(),
        "budget_warning":  _get_budget_warning(),  # none/warning/critical
    })

@app.route("/api/system/status", methods=["GET"])
def system_status():
    """フロントが定期ポーリングするシステム状態エンドポイント（認証不要）"""
    _check_and_update_fallback_mode()
    return jsonify({
        "fallback_mode":  is_fallback_mode(),
        "budget_warning": _get_budget_warning(),  # none/warning/critical
        "ok": True,
    })

@app.route("/api/admin/fallback-mode", methods=["POST"])
@admin_required
def admin_set_fallback_mode():
    """管理者がフォールバックモードを手動でON/OFFする"""
    d = request.json or {}
    enabled = d.get("enabled", False)
    # maintenance_mode を更新
    db_exec(
        "UPDATE admin_settings SET value=%s, updated_at=NOW() WHERE key='maintenance_mode'",
        ("true" if enabled else "false",)
    )
    # 手動フラグを更新（ON時はtrue、OFF時はfalse）
    db_exec(
        "UPDATE admin_settings SET value=%s, updated_at=NOW() WHERE key='maintenance_mode_manual'",
        ("true" if enabled else "false",)
    )
    print(f"[Fallback] 管理者が手動でフォールバックモードを {'ON' if enabled else 'OFF'} にしました")
    return jsonify({"ok": True, "fallback_mode": enabled})


@app.route("/api/admin/test-alert-email", methods=["POST"])
@admin_required
def admin_test_alert_email():
    """管理者向け予算アラートメールのテスト送信"""
    d     = request.json or {}
    level = int(d.get("level", 80))
    if level not in (80, 90, 100):
        return jsonify({"error": "level は 80/90/100 のいずれかを指定してください"}), 400
    budget_row = db_exec("SELECT value FROM admin_settings WHERE key='monthly_budget_usd'", fetch="one")
    budget_usd = float(budget_row["value"]) if budget_row else 100.0
    used_usd   = budget_usd * level / 100
    try:
        send_admin_budget_alert(used_usd, budget_usd, float(level), level)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    admin_email = os.getenv("ADMIN_EMAIL", "")
    return jsonify({"ok": True, "sent_to": admin_email or "(ADMIN_EMAIL未設定)",
                    "level": level, "used_usd": used_usd, "budget_usd": budget_usd})


@app.route("/api/admin/notify-users", methods=["POST"])
@admin_required
def admin_notify_users():
    """管理者がユーザー全員（または特定プラン）にお知らせメールを一括送信"""
    d           = request.json or {}
    subject     = (d.get("subject") or "").strip()
    body        = (d.get("body")    or "").strip()
    plan_filter = d.get("plan")
    if not subject or not body:
        return jsonify({"error": "subject と body は必須です"}), 400
    if plan_filter:
        users = db_exec("SELECT nickname, email FROM lu_users WHERE is_active=TRUE AND plan=%s",
                        (plan_filter,), fetch="all") or []
    else:
        users = db_exec("SELECT nickname, email FROM lu_users WHERE is_active=TRUE",
                        fetch="all") or []
    sent, failed = 0, 0
    for u in users:
        ok = send_user_notification(
            to_email=u["email"], nickname=u["nickname"],
            subject=subject, body_text=f"{u['nickname']} さん\n\n{body}")
        if ok: sent += 1
        else:  failed += 1
    return jsonify({"ok": True, "sent": sent, "failed": failed, "total": len(users)})


# ══════════════════════════════════════════════════════════════
#  静的ファイル配信（フロントエンドHTML）
# ══════════════════════════════════════════════════════════════
@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve(path):
    # /api/* はここに来ない（Flaskがルーティング済み）
    full = os.path.join(app.static_folder, path)
    if os.path.isfile(full):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 52)
    print("  Lumina AI  ─  Railway 対応版")
    print(f"  OpenAI  : {'✓' if os.getenv('OPENAI_API_KEY') else '⚠ OPENAI_API_KEY 未設定'}")
    print(f"  楽天    : {'✓' if os.getenv('RAKUTEN_APP_ID') else '未設定（任意）'}")
    print(f"  Google  : {'✓' if os.getenv('GOOGLE_MAPS_API_KEY') else '未設定（任意）'}")
    print(f"  RapidAPI: {'✓' if os.getenv('RAPIDAPI_KEY') else '未設定（任意・航空券検索）'}")
    print(f"  DB URL  : {'DATABASE_URL あり' if os.getenv('DATABASE_URL') else 'DB_HOST 使用'}")
    print(f"  PORT    : {PORT}")
    print("=" * 52)
    app.run(host="0.0.0.0", port=PORT, debug=False)