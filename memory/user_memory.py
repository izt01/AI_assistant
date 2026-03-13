"""
ユーザー記憶の読み書き ― 成長型AIの核心部分

会話のたびに以下を蓄積する：
  1. 好み・嗜好（予算感・スタイル・辛さなど）
  2. ライフスタイル情報（家族・職業・エリア）
  3. 提案履歴（何を提案し、どう反応したか）
  4. 却下した提案と理由

これらをプロンプトに注入することで、使うほど精度が上がる。
"""
import json
from openai import OpenAI
from .db import get_conn

client = OpenAI()

# ── 記憶の読み込み ──────────────────────────────────────────

def load_memory(user_id: str, ai_type: str) -> dict:
    """ユーザーの記憶をDBから読み込んでdictで返す"""
    memory = {
        "profile":     {},
        "preferences": {},
        "history":     [],
        "rejections":  [],
    }
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # プロファイル
                cur.execute("SELECT * FROM user_profiles WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    memory["profile"] = dict(row)

                # 好み（このAIタイプ）
                cur.execute("""
                    SELECT key, value, confidence FROM user_preferences
                    WHERE user_id = %s AND ai_type = %s
                    ORDER BY confidence DESC
                """, (user_id, ai_type))
                for row in cur.fetchall():
                    memory["preferences"][row["key"]] = {
                        "value": row["value"],
                        "confidence": row["confidence"]
                    }

                # 提案履歴 — lu_proposals（新）+ proposal_history（旧互換）を統合
                cur.execute("""
                    SELECT item_name AS proposal, outcome, reject_reason AS reason, created_at
                    FROM lu_proposals
                    WHERE user_id = %s AND ai_type = %s
                    ORDER BY created_at DESC LIMIT 15
                """, (user_id, ai_type))
                lu_rows = cur.fetchall()

                cur.execute("""
                    SELECT proposal, outcome, reason, created_at FROM proposal_history
                    WHERE user_id = %s AND ai_type = %s
                    ORDER BY created_at DESC LIMIT 10
                """, (user_id, ai_type))
                old_rows = cur.fetchall()

                # 両テーブルをマージ（created_atで降順、最大20件）
                all_rows = sorted(
                    list(lu_rows) + list(old_rows),
                    key=lambda r: r["created_at"],
                    reverse=True
                )[:20]

                for row in all_rows:
                    entry = {
                        "proposal": row["proposal"],
                        "outcome":  row["outcome"],
                        "date":     str(row["created_at"])[:10],
                    }
                    if row["outcome"] == "rejected":
                        memory["rejections"].append({**entry, "reason": row.get("reason")})
                    else:
                        memory["history"].append(entry)

    except Exception as e:
        print(f"[Memory] 読み込みエラー: {e}")

    return memory


def build_memory_prompt(memory: dict, ai_type: str, overall_score: float = 0.0) -> str:
    """記憶をプロンプト文字列に変換する"""
    lines = []

    if memory["profile"]:
        p = memory["profile"]
        lines.append("【このユーザーの基本情報】")
        if p.get("name"):       lines.append(f"  名前: {p['name']}")
        if p.get("area"):       lines.append(f"  エリア: {p['area']}")
        if p.get("occupation"): lines.append(f"  職業: {p['occupation']}")
        if p.get("family"):     lines.append(f"  家族構成: {p['family']}")

    if memory["preferences"]:
        lines.append(f"\n【{ai_type}での蓄積された好み・嗜好】")
        # confidence高い順にソート済み（DBのORDER BY confidence DESCを活用）
        for key, info in memory["preferences"].items():
            conf_val = info["confidence"]
            if conf_val >= 7:
                conf_label = "（確実・最重要）"  # 迷わず前提として使う
            elif conf_val >= 3:
                conf_label = "（確実）"          # 確認なしで使う
            else:
                conf_label = "（推測）"          # 一言確認してから使う

            # スコアが高いほど確信度の高い好みを前面に出す
            if overall_score >= 25 and conf_val >= 3:
                lines.append(f"  ★ {key}: {info['value']} {conf_label}")
            else:
                lines.append(f"  {key}: {info['value']} {conf_label}")

    if memory["rejections"]:
        lines.append("\n【過去に却下された提案（絶対に繰り返さないこと）】")
        for r in memory["rejections"]:          # 全件表示（上限なし）
            reason = f" → 理由: {r['reason']}" if r.get("reason") else ""
            lines.append(f"  ✕ {r['proposal'][:80]}{reason}")

    if memory["history"]:
        accepted = [h for h in memory["history"] if h["outcome"] == "accepted"]
        if accepted:
            lines.append("\n【過去に好評だった提案（優先的に参考にすること）】")
            for h in accepted[:5]:  # 3件→5件に拡張
                lines.append(f"  ✓ {h['proposal'][:80]} ({h['date']})")

    if not lines:
        return ""

    return "\n".join(lines)


# ── 記憶の書き込み ──────────────────────────────────────────

def extract_and_save_memory(user_id: str, ai_type: str, messages: list, session_id: str):
    """
    会話履歴からAIが記憶すべき情報を抽出してDBに保存する。
    会話終了時（または一定ターンごと）に呼ぶ。
    """
    if len(messages) < 2:
        return

    conv_text = "\n".join([
        f"{'ユーザー' if m['role']=='user' else 'AI'}: {m['content'][:300]}"
        for m in messages[-20:]  # 直近20件
    ])

    extract_prompt = f"""
以下の会話から、ユーザーの記憶として保存すべき情報を抽出してください。

会話:
{conv_text}

以下のJSON形式のみで返答（余計なテキスト不要）:
{{
  "profile": {{
    "area": "居住エリア（あれば）",
    "occupation": "職業（あれば）",
    "family": "家族構成（あれば）"
  }},
  "preferences": [
    {{"key": "項目名", "value": "値", "confidence": 確信度1-5}}
  ],
  "proposals": [
    {{"content": "提案内容の要約", "outcome": "accepted/rejected/unknown", "reason": "理由（あれば）"}}
  ]
}}

抽出できない項目はnullまたは空配列にする。
preferenceの例: spice_level=辛め, budget_feel=コスパ重視, travel_style=アクティブ, exercise_habit=週2回
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=600,
            messages=[{"role": "user", "content": extract_prompt}]
        )
        raw = res.choices[0].message.content.strip()
        data = json.loads(raw.replace("```json", "").replace("```", "").strip())

        with get_conn() as conn:
            with conn.cursor() as cur:

                # プロファイル更新
                profile = {k: v for k, v in (data.get("profile") or {}).items() if v}
                if profile:
                    cur.execute("""
                        INSERT INTO user_profiles (user_id, area, occupation, family, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (user_id) DO UPDATE SET
                            area       = COALESCE(NULLIF(EXCLUDED.area,''), user_profiles.area),
                            occupation = COALESCE(NULLIF(EXCLUDED.occupation,''), user_profiles.occupation),
                            family     = COALESCE(NULLIF(EXCLUDED.family,''), user_profiles.family),
                            updated_at = NOW()
                    """, (user_id,
                          profile.get("area"),
                          profile.get("occupation"),
                          profile.get("family")))

                # 好み更新（confidence を累積）
                for pref in (data.get("preferences") or []):
                    if not pref.get("key") or not pref.get("value"):
                        continue
                    cur.execute("""
                        INSERT INTO user_preferences (user_id, ai_type, key, value, confidence, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (user_id, ai_type, key) DO UPDATE SET
                            value      = EXCLUDED.value,
                            confidence = LEAST(user_preferences.confidence + %s, 10.0),
                            updated_at = NOW()
                    """, (user_id, ai_type,
                          pref["key"], pref["value"],
                          pref.get("confidence", 1),
                          pref.get("confidence", 1)))

                # 提案履歴保存
                for prop in (data.get("proposals") or []):
                    if not prop.get("content"):
                        continue
                    cur.execute("""
                        INSERT INTO proposal_history
                            (user_id, ai_type, session_id, proposal, outcome, reason)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (user_id, ai_type, session_id,
                          prop["content"],
                          prop.get("outcome", "unknown"),
                          prop.get("reason")))

            conn.commit()
        print(f"[Memory] 記憶を保存しました (user={user_id}, ai={ai_type})")

    except Exception as e:
        print(f"[Memory] 保存エラー: {e}")


def save_feedback(user_id: str, ai_type: str, session_id: str,
                  proposal: str, outcome: str, reason: str = None):
    """ユーザーが明示的にフィードバックしたときに呼ぶ"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO proposal_history
                        (user_id, ai_type, session_id, proposal, outcome, reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, ai_type, session_id, proposal, outcome, reason))
            conn.commit()
    except Exception as e:
        print(f"[Memory] フィードバック保存エラー: {e}")
