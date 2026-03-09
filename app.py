"""
Lumina AI  ─  統合バックエンドサーバー（Railway対応版）
OpenAI GPT-4o × 記憶成長型AIエージェント

起動: python app.py
Railway: Procfile の `web: python app.py` で自動起動
"""
import json, os, sys, uuid
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
        updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
    );
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
        updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lu_match_scores (
        user_id           UUID PRIMARY KEY REFERENCES lu_users(id) ON DELETE CASCADE,
        overall_score     FLOAT NOT NULL DEFAULT 0.0,
        food_score        FLOAT NOT NULL DEFAULT 0.0,
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
    CREATE INDEX IF NOT EXISTS idx_lu_messages_session ON lu_messages(session_id, created_at);
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
PLAN_LIMITS = {"free": 10, "pro": 50, "master": 200}

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
                     ("lu_match_scores","match_score")]:
        row  = db_exec(f"SELECT * FROM {tbl} WHERE user_id=%s", (user_id,), fetch="one")
        data = {k: safe_json(v) for k, v in dict(row).items()} if row else {}
        ctx[key] = data
    row = db_exec("SELECT nickname FROM lu_users WHERE id=%s", (user_id,), fetch="one")
    ctx["nickname"] = row["nickname"] if row else "ユーザー"
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

    if ai_type in ("recipe", "health", "general"):
        fd = ctx.get("food", {})
        if fd.get("liked_cuisines"):    lines.append(f"好きな料理: {', '.join(fd['liked_cuisines'])}")
        if fd.get("disliked_cuisines"): lines.append(f"苦手な料理: {', '.join(fd['disliked_cuisines'])}")
        if fd.get("allergies"):         lines.append(f"⚠️ アレルギー: {', '.join(fd['allergies'])} ←絶対に提案しないこと")
        if fd.get("spice_level"):       lines.append(f"辛さの好み: {fd['spice_level']}/5")

    if ai_type in ("travel", "general"):
        t = ctx.get("travel", {})
        if t.get("travel_styles"):    lines.append(f"旅行スタイル: {', '.join(t['travel_styles'])}")
        if t.get("budget_range"):     lines.append(f"旅行予算帯: {t['budget_range']}")
        if t.get("max_travel_hours"): lines.append(f"移動許容時間: {t['max_travel_hours']}時間まで")

    if ai_type in ("shopping", "appliance", "diy", "general"):
        s = ctx.get("shopping", {})
        if s.get("liked_brands"):    lines.append(f"好きなブランド: {', '.join(s['liked_brands'])}")
        if s.get("disliked_brands"): lines.append(f"苦手なブランド: {', '.join(s['disliked_brands'])}")

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
    if cl:
        lines.append("⚠️ 以下は絶対に守ること（除外ルール）:")
        for x in cl: lines.append(f"   - {x}")

    sc = ctx.get("match_score", {})
    if sc.get("total_sessions", 0) > 0:
        lines.append(f"（会話実績: {sc['total_sessions']}回 / マッチ度: {round(sc.get('overall_score',0))}%）")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def update_match_score(user_id, ai_type, rating=0):
    col = {"recipe":"food_score","travel":"travel_score","shopping":"shopping_score",
           "health":"health_score","appliance":"home_score","diy":"diy_score"}.get(ai_type,"overall_score")
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lu_match_scores (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        if rating == 1:
            cur.execute(f"UPDATE lu_match_scores SET helpful_count=helpful_count+1,"
                        f"total_sessions=total_sessions+1,{col}=LEAST(100,{col}+2.5),"
                        f"overall_score=LEAST(100,overall_score+1.5),last_updated=NOW() WHERE user_id=%s", (user_id,))
        elif rating == -1:
            cur.execute(f"UPDATE lu_match_scores SET not_helpful_count=not_helpful_count+1,"
                        f"total_sessions=total_sessions+1,{col}=GREATEST(0,{col}-0.5),"
                        f"last_updated=NOW() WHERE user_id=%s", (user_id,))
        else:
            cur.execute(f"UPDATE lu_match_scores SET total_sessions=total_sessions+1,"
                        f"{col}=LEAST(100,{col}+0.8),overall_score=LEAST(100,overall_score+0.4),"
                        f"last_updated=NOW() WHERE user_id=%s", (user_id,))
    conn.commit()


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
                    "lu_pref_restaurant","lu_constraints","lu_match_scores"]:
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
               "monthly_budget","outing_budget","weekday_style","weekend_style","favorite_services"]
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
                                            "max_travel_time_min"]),
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

    if not messages_in:
        return jsonify({"error": "メッセージがありません"}), 400

    limit = PLAN_LIMITS.get(user["plan"], 10)
    if user["plan"] != "master" and user["usage_count"] >= limit:
        return jsonify({"error": "usage_limit_reached", "limit": limit}), 429

    AI_NAME_MAP = {"all": None, "cooking": "recipe", "travel": "travel",
                   "shopping": "shopping", "diy": "diy", "home": "appliance", "health": "health"}
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

    context_injection = build_context_injection(uid, agent_name)
    agent = AGENT_MAP.get(agent_name)

    try:
        if agent:
            original_build = agent.build_system
            def patched_build(_):
                return original_build(uid) + "\n\n" + context_injection
            agent.build_system = patched_build
            result = agent.run(messages_in, user_id=uid)
            agent.build_system = original_build
        else:
            from openai import OpenAI
            client = OpenAI()
            res = client.chat.completions.create(
                model="gpt-4o", max_tokens=1200,
                messages=[{"role":"system","content":
                    f"あなたは親切な日本語AIアシスタントです。\n\n{context_injection}\n\n"
                    '必ず次のJSONのみで返答: {"ai":"general","message":"応答","suggestions":["選択肢1","選択肢2"]}'}
                ] + messages_in)
            raw = res.choices[0].message.content.strip()
            try:    result = json.loads(raw.replace("```json","").replace("```","").strip())
            except: result = {"ai":"general","message":raw,"suggestions":[]}
    except Exception as e:
        print(f"[Chat Error] {e}")
        return jsonify({"error": f"AI応答エラー: {str(e)}"}), 500

    result["ai"]  = ai_type
    reply_text    = result.get("message", "")
    suggestions   = result.get("suggestions", [])
    extra         = {k:v for k,v in result.items() if k not in ("ai","message","suggestions")}
    msg_id_ai     = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute("INSERT INTO lu_messages (id,session_id,user_id,role,content,ai_type,extra)"
                    " VALUES (%s,%s,%s,'assistant',%s,%s,%s)",
                    (msg_id_ai, session_id, uid, reply_text, ai_type,
                     json.dumps(extra, ensure_ascii=False) if extra else None))
        cur.execute("UPDATE lu_sessions SET msg_count=msg_count+2 WHERE id=%s", (session_id,))
        cur.execute("UPDATE lu_users SET usage_count=usage_count+1 WHERE id=%s", (uid,))
    conn.commit()

    update_match_score(uid, agent_name or "general")

    return jsonify({"reply": reply_text, "suggestions": suggestions, "extra": extra,
                    "session_id": session_id, "message_id": msg_id_ai,
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
    return jsonify({"ok": True})

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
    print(f"  DB URL  : {'DATABASE_URL あり' if os.getenv('DATABASE_URL') else 'DB_HOST 使用'}")
    print(f"  PORT    : {PORT}")
    print("=" * 52)
    app.run(host="0.0.0.0", port=PORT, debug=False)
