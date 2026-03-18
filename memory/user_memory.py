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
        likes    = {k: v for k, v in memory["preferences"].items() if v["confidence"] >= 0}
        dislikes = {k: v for k, v in memory["preferences"].items() if v["confidence"] < 0}

        if likes:
            lines.append(f"\n【{ai_type}での好み・嗜好（積極的に活用すること）】")
            for key, info in likes.items():
                conf_val = info["confidence"]
                if conf_val >= 7:
                    conf_label = "（確実・最重要）"
                elif conf_val >= 3:
                    conf_label = "（確実）"
                else:
                    conf_label = "（推測）"
                display_val = info["value"].replace("[嫌い]", "")
                if overall_score >= 25 and conf_val >= 3:
                    lines.append(f"  ★ {key}: {display_val} {conf_label}")
                else:
                    lines.append(f"  {key}: {display_val} {conf_label}")

        if dislikes:
            lines.append(f"\n【⚠️ {ai_type}での絶対除外リスト（提案に絶対含めないこと）】")
            for key, info in dislikes.items():
                conf_val = abs(info["confidence"])
                display_val = info["value"].replace("[嫌い]", "")
                if conf_val >= 4:
                    lines.append(f"  🚫 {key}: {display_val}（絶対NG・確定）")
                else:
                    lines.append(f"  ✕ {key}: {display_val}（NG・要確認）")

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
    {{"key": "項目名", "value": "値", "confidence": 確信度1-5, "sentiment": "like/dislike/neutral"}}
  ],
  "proposals": [
    {{"content": "提案内容の要約", "outcome": "accepted/rejected/unknown", "reason": "理由（あれば）"}}
  ]
}}

## 抽出のルール
- 好き嫌い・得意不得意は必ず抽出する（最重要）
  - 「〇〇は嫌い」「〇〇は苦手」「〇〇はやりたくない」→ sentiment: "dislike", confidence: 4
  - 「〇〇が好き」「〇〇なら続けられる」「〇〇は得意」→ sentiment: "like", confidence: 3
  - アレルギー・食事制限 → sentiment: "dislike", confidence: 5（最高確信度）
- 理由・動機の抽出（なぜそうしたいか）
  - 「ゆっくりしたいから旅行」→ travel_motivation: 癒し・リラックス
  - 「体重を落としたい」→ health_goal: 減量
- 好みの強さ（confidence）の基準:
  - 5: アレルギー・絶対条件（変わらない）
  - 4: 「嫌い」「苦手」と明言
  - 3: 「好き」「気に入った」と明言
  - 2: 行動から推測（選んだ・使った）
  - 1: 文脈から弱く推測
- dislike の preference は confidence を負の値で保存するためそのまま返す
  （DB側で sentiment=dislike を -confidence として扱う）

## 抽出例
- spice_level: 辛め (like, 3)
- budget_feel: コスパ重視 (like, 2)
- travel_motivation: 癒し・温泉 (like, 3)
- exercise_dislike: ランニング (dislike, 4)
- food_allergy: 甲殻類 (dislike, 5)
- travel_style: 一人旅 (like, 3)
- cooking_dislike: 揚げ物 (dislike, 3)

抽出できない項目はnullまたは空配列にする。
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
                # sentiment=dislike は confidence を負値で保存（好き=正、嫌い=負）
                for pref in (data.get("preferences") or []):
                    if not pref.get("key") or not pref.get("value"):
                        continue
                    raw_conf  = pref.get("confidence", 1)
                    sentiment = pref.get("sentiment", "like")
                    # 嫌い・苦手・アレルギーは負のconfidenceで保存
                    conf_val  = -abs(raw_conf) if sentiment == "dislike" else abs(raw_conf)
                    # dislike は value に [DISLIKE] プレフィックスを付けて区別可能にする
                    stored_val = f"[嫌い]{pref['value']}" if sentiment == "dislike" else pref["value"]
                    cur.execute("""
                        INSERT INTO user_preferences (user_id, ai_type, key, value, confidence, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (user_id, ai_type, key) DO UPDATE SET
                            value      = EXCLUDED.value,
                            confidence = LEAST(GREATEST(user_preferences.confidence + %s, -10.0), 10.0),
                            updated_at = NOW()
                    """, (user_id, ai_type,
                          pref["key"], stored_val, conf_val, conf_val))

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
