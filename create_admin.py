"""
管理者アカウント作成スクリプト
使い方: python create_admin.py
Railway環境: railway run python create_admin.py
"""
import os, sys, bcrypt, psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.getenv("DATABASE_URL","")
if not DB_URL:
    print("❌ DATABASE_URL が未設定です")
    sys.exit(1)

email    = input("管理者メール: ").strip()
password = input("パスワード: ").strip()
nickname = input("表示名（任意）[Admin]: ").strip() or "Admin"

if not email or not password:
    print("❌ メールとパスワードは必須です")
    sys.exit(1)

pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor, sslmode="require")
cur  = conn.cursor()

# 既存ユーザーを管理者に昇格するか、新規作成
cur.execute("SELECT id FROM lu_users WHERE email=%s", (email,))
existing = cur.fetchone()

if existing:
    cur.execute("UPDATE lu_users SET is_admin=TRUE, password_hash=%s, is_active=TRUE WHERE email=%s",
                (pw_hash, email))
    print(f"✅ 既存アカウント ({email}) を管理者に昇格しました")
else:
    cur.execute(
        "INSERT INTO lu_users(nickname,email,password_hash,plan,is_admin) VALUES(%s,%s,%s,'master',TRUE)",
        (nickname, email, pw_hash))
    print(f"✅ 管理者アカウント ({email}) を作成しました")

conn.commit()
cur.close()
conn.close()
print("→ admin-login.html からログインしてください")
