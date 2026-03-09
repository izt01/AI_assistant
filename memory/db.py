"""
PostgreSQL 接続管理（Railway DATABASE_URL 対応版）
"""
import os, time
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

def get_conn(retries: int = 5, delay: float = 2.0):
    database_url = os.getenv("DATABASE_URL", "")
    for i in range(retries):
        try:
            if database_url:
                # Railway / Heroku: DATABASE_URL を直接使用
                return psycopg2.connect(database_url, sslmode="require")
            else:
                # ローカル: 個別パラメータを使用
                return psycopg2.connect(
                    host     = os.getenv("DB_HOST", "localhost"),
                    port     = int(os.getenv("DB_PORT", 5432)),
                    dbname   = os.getenv("DB_NAME", "ai_suite"),
                    user     = os.getenv("DB_USER", "ai_suite_user"),
                    password = os.getenv("DB_PASSWORD", "ai_suite_pass"),
                )
        except psycopg2.OperationalError as e:
            if i < retries - 1:
                print(f"[DB] 接続待機中... ({i+1}/{retries})")
                time.sleep(delay)
            else:
                raise RuntimeError(f"[DB] PostgreSQL に接続できませんでした: {e}")

def init_db():
    """記憶テーブルのスキーマを初期化"""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("[DB] 記憶スキーマ初期化完了")
