# Lumina AI  ─  Railway デプロイガイド

## 必要な外部APIキー

| # | サービス | 環境変数 | 必須/任意 | 取得先 |
|---|---------|----------|----------|--------|
| 1 | **OpenAI** | `OPENAI_API_KEY` | **必須** | https://platform.openai.com/api-keys |
| 2 | **楽天 WebService** | `RAKUTEN_APP_ID` | 任意 | https://webservice.rakuten.co.jp/ |
| 3 | **Google Maps Places API** | `GOOGLE_MAPS_API_KEY` | 任意 | https://console.cloud.google.com/ |

---

## Railway へのデプロイ手順

### ① GitHubにpush

```bash
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/あなたのID/lumina-ai.git
git push -u origin main
```

### ② Railway でプロジェクト作成

1. https://railway.app にアクセス（GitHubアカウントでログイン）
2. **「New Project」→「Deploy from GitHub repo」**
3. `lumina-ai` リポジトリを選択 → **「Deploy Now」**

### ③ PostgreSQL を追加

1. Railwayプロジェクト画面で **「+ New」→「Database」→「PostgreSQL」**
2. 自動で `DATABASE_URL` が生成される（設定不要）

### ④ 環境変数を設定

Railwayの Flask サービス → **「Variables」タブ** で以下を入力：

| 変数名 | 値 |
|--------|-----|
| `OPENAI_API_KEY` | `sk-proj-xxxxxx` |
| `SECRET_KEY` | ランダムな文字列（例: `openssl rand -hex 32` の出力） |
| `RAKUTEN_APP_ID` | 楽天のID（任意） |
| `GOOGLE_MAPS_API_KEY` | GoogleのAPIキー（任意） |

> `DATABASE_URL` は Railway が PostgreSQL と自動的に繋いでくれるため、**手動設定不要**

### ⑤ 完了・URL確認

Railway の **「Settings」→「Domains」→「Generate Domain」** で公開URLが発行される。

**以降は `git push` するだけで自動デプロイ。**

---

## ローカル開発

```bash
# 1. PostgreSQL を Docker で起動
docker run -d --name lumina-db \
  -e POSTGRES_DB=ai_suite \
  -e POSTGRES_USER=ai_suite_user \
  -e POSTGRES_PASSWORD=ai_suite_pass \
  -p 5432:5432 postgres:16-alpine

# 2. 依存パッケージをインストール
pip install -r requirements.txt

# 3. 環境変数を設定
cp .env.example .env
# .env を編集して OPENAI_API_KEY などを入力

# 4. 起動
python app.py
# → http://localhost:5001
```

---

## フォルダ構成

```
lumina-ai/              ← GitHubリポジトリのルート
├── app.py              ★ メインサーバー（Railway はここを起動）
├── Procfile            ★ Railway起動コマンド: web: python app.py
├── requirements.txt    ★ 依存パッケージ
├── .env.example        環境変数テンプレート
├── .gitignore
├── agents/             専門AIエージェント群
│   ├── base.py         BaseAgent（OpenAI Function Calling）
│   ├── travel.py       旅行AI（楽天ホテル・Google Maps）
│   ├── recipe.py       料理AI（Google Maps 周辺スーパー）
│   ├── shopping.py     買い物AI（楽天市場・Google Maps）
│   ├── appliance.py    家電・インテリアAI（楽天市場）
│   ├── diy.py          DIY AI（楽天市場）
│   ├── health.py       健康AI（外部API不要）
│   └── router.py       ルーターAI（GPT-4o-mini で自動振り分け）
├── memory/             記憶・学習システム
│   ├── db.py           DB接続（DATABASE_URL 対応）
│   ├── user_memory.py  記憶の読み書き
│   └── schema.sql      記憶テーブルスキーマ
├── tools/              外部API連携
│   ├── rakuten.py      楽天API（ホテル・商品検索）
│   └── maps.py         Google Maps API（周辺検索）
├── prompts/            AIプロンプト（YAML）
│   └── packs/default/  各AI用プロンプトファイル
├── index.html          ← フロントエンド（ここから配信）
├── login.html
├── register.html
├── dashboard.html
├── chat.html
├── profile.html
├── shared.js
└── shared.css
```
