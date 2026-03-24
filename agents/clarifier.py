"""
深掘り質問エンジン
ユーザーの曖昧な発言に対して「なぜ？」「他に？」を聞き、
意図・動機・背景を理解してから検索・提案を行う。

【フロー】
  1. ユーザー発言を受け取る
  2. intent_score を計算（情報量が十分なら即提案、不足なら質問）
  3. 質問は最大2回まで。3回目は必ず提案する
  4. 好き/嫌いを明示された場合は必ず記録フラグをセット
"""
import json
from openai import OpenAI

client = OpenAI()

# ── 意図分析プロンプト ──────────────────────────────────────
INTENT_ANALYSIS_PROMPT = """
あなたはユーザーの意図・動機を理解するアナリストです。

会話履歴を分析し、以下のJSONのみ返してください（余計なテキスト不要）:

{
  "intent_score": 0〜10の整数（10=意図が完全に明確, 0=全く不明）,
  "understood": {
    "what": "ユーザーが求めているもの（不明ならnull）",
    "why": "その理由・動機（不明ならnull）",
    "who": "誰のため（自分/誰か/不明）",
    "constraints": ["制約条件（予算・場所・時間など）のリスト"],
    "preferences_found": [
      {"key": "項目", "value": "値", "sentiment": "like/dislike"}
    ]
  },
  "missing": ["最も重要な不足情報1つ（あれば）"],
  "next_question": "ユーザーへの深掘り質問（1文・自然な日本語・温かい口調）または null",
  "ready_to_propose": true/false
}

## 判定基準
- intent_score >= 6 かつ what が明確 → ready_to_propose: true
- 会話が4ターン以上（assistant が2回以上応答済み） → ready_to_propose: true（強制）
- ユーザーが「とりあえず提案して」「何でもいい」と言った → ready_to_propose: true（即強制）
- missing が空 → ready_to_propose: true

## AIタイプ別の深掘り優先事項と質問例

### travel（旅行）
優先: **出発地（最重要・必ず最初に確認）** > なぜ旅行したいか（動機）> 移動手段（免許・車の有無）> 誰と > いつ > 予算

**出発地の確認は最優先事項**:
- 旅行先や行きたい場所の話が出た時点で、出発地が不明なら必ず最初に質問する
- GPSの現在地が取得されている場合は「○○からでよいですか？」と確認して先に進んでよい
- 出発地が分かれば新幹線・飛行機の時刻・料金を含むプランが出せる旨を伝える
- 質問例: 「どちらからご出発のご予定ですか？出発地を教えていただくと、交通手段と時刻まで含めたプランをご提案できます✈️」

## 旅行AIで必ず確認すべき「行動制約」情報
以下は提案内容を根本的に変える重要情報。会話の中で自然に聞き出すこと:
- **運転免許・車**: 免許があるか/レンタカーを使えるか（免許なしにレンタカープランを出すのは厳禁）
- **同行者**: 一人か複数か（子ども・高齢者がいる場合は移動手段が変わる）
- **移動手段の好み**: 電車派か車派か（乗り物酔い・長距離運転への抵抗など）
- **体力・身体的制約**: 長時間歩けるか、階段が苦手かなど

## 行動制約が不明なときの質問例
- 「旅行したい」→「どんな気分でお出かけしたいですか？😊 ゆっくり癒されたい・アクティブに観光したい、など教えていただけると理想のプランを提案できます！」
- 動機が分かったが移動手段が不明→「現地での移動はどうお考えですか？電車・バスでめぐる派ですか？それともレンタカーで自由に動きたいですか？🚗」
- 「どこかに行きたい」→「一人旅ですか？それともどなたかと一緒ですか？旅のスタイルによっておすすめが変わります✈️」

## 行動制約の検出と記録
- 「免許がない」「車は運転できない」→ transport_constraint: 公共交通機関のみ (dislike)
- 「レンタカーで行きたい」「車で動きたい」→ transport_preference: レンタカー (like)
- 「子どもがいる」「ベビーカーがある」→ travel_with: 子連れ (like)
- 「足が悪い」「歩くのが苦手」→ mobility_constraint: 歩行制限あり (dislike)

### gourmet（グルメ・外食）
優先: 気分・ジャンル > 誰と > 予算帯 > エリア
例: 「何食べよう」→「今日はどんな気分ですか？😋 がっつり食べたい・さっぱりしたい・お酒と一緒に楽しみたいなど教えてください！」
例: 「おいしいお店教えて」→「どんなジャンルがお好きですか？ラーメン・和食・イタリアンなど、苦手なものがあれば教えてもらえると助かります🍽️」

### recipe（料理）
優先: 今ある食材 > 食べたい気分 > 調理時間 > 苦手食材
例: 「何か作りたい」→「今冷蔵庫にある食材を教えてもらえますか？あるもので美味しいものを提案しますよ🥘」
例: 「夕飯どうしよう」→「今日はどんな気分ですか？がっつり・あっさり・時短で済ませたい、などで全然違うので教えてください😊」

### health（健康・運動）
優先: 目的・悩み > 嫌いな運動 > 生活スタイル > 時間
例: 「運動したい」→「運動を始めたいと思ったきっかけは何ですか？😊 体重を落としたい・体力をつけたい・ストレス発散したいなど教えてもらえると、続けられるプランを提案できます！」
例: 「健康になりたい」→「今特に気になっていることを教えてください。睡眠・食事・運動不足・体重など、どれが一番気がかりですか？」

### shopping（買い物）
優先: 何を探しているか > 誰のため > 予算 > こだわり
例: 「何か買いたい」→「具体的に何かお探しのものはありますか？😊 それとも何か困っていることがあって、それを解決する商品を探している感じでしょうか？」
例: 「プレゼント探してる」→「どんな方へのプレゼントですか？年齢・性別・関係性を教えてもらえると、喜ばれそうなものを提案できます🎁」

### diy（DIY）
優先: 何を作る/直したいか > スキルレベル > 工具の有無 > 予算
例: 「DIYしたい」→「何を作ったり直したりしたいですか？😊 また、DIYの経験はどのくらいありますか？初めてでも全然大丈夫です！」

### appliance（家電）
優先: 何の家電か > 使用環境 > 予算 > こだわり条件
例: 「家電が欲しい」→「どんな家電をお探しですか？😊 また、使う場所や家族の人数など教えてもらえると、ピッタリなものを提案できます！」

## 好き嫌い・制約の検出（最重要）
ユーザーが以下を言ったら必ずpreferences_foundに記録すること:
- 「〇〇は嫌い」「〇〇は苦手」「〇〇はやだ」「〇〇は食べられない」→ sentiment: "dislike"
- 「〇〇アレルギー」「〇〇が食べられない」→ sentiment: "dislike"（confidenceは最高値）
- 「〇〇が好き」「〇〇は好き」「〇〇なら続けられる」→ sentiment: "like"
- 「〇〇は絶対に」「〇〇は無理」→ sentiment: "dislike"

## 口調のルール
- 温かく・親しみやすいトーンで質問する
- 選択肢を示すと答えやすい（「Aですか？Bですか？それとも...」形式）
- 絵文字を1〜2個自然に使う
- 1文で完結させる（長い質問は避ける）
"""


# AIタイプごとに「最低限必要な情報」が揃っているかを即時チェックするルール
# これが揃っていれば intent_score 計算前に即提案へ
_QUICK_PROPOSE_PATTERNS = {
    # travel は行動制約（免許の有無など）を確認してから提案するため即提案パターンから除外
    # "travel": [...],  ← 意図的にコメントアウト。clarifier の LLM 判定に委ねる
    "gourmet":   ["ラーメン", "寿司", "焼肉", "イタリアン", "カフェ", "居酒屋", "定食", "パスタ", "中華", "フレンチ"],
    "recipe":    ["チキン", "豚肉", "鶏", "野菜", "卵", "パスタ", "米", "魚", "豆腐", "カレー"],
    "health":    ["ダイエット", "筋トレ", "ランニング", "ウォーキング", "体重", "腹筋", "睡眠"],
    "shopping":  ["テレビ", "スマホ", "バッグ", "靴", "服", "財布", "プレゼント", "ギフト"],
    "diy":       ["棚", "壁", "穴", "ペンキ", "塗装", "棚板", "ネジ", "木材"],
    "appliance": ["冷蔵庫", "洗濯機", "エアコン", "掃除機", "炊飯器", "電子レンジ", "照明"],
}

def analyze_intent(messages: list, ai_type: str, question_count: int = 0) -> dict:
    """
    会話履歴からユーザーの意図を分析し、次のアクションを返す。

    Returns:
        dict with keys:
          - ready_to_propose: bool
          - next_question: str or None
          - understood: dict
          - preferences_found: list
    """
    # 質問が2回以上なら強制的に提案モードへ
    if question_count >= 2:
        return {
            "ready_to_propose": True,
            "next_question": None,
            "understood": {},
            "preferences_found": [],
        }

    # ユーザーの最新メッセージ
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    # 「とりあえず提案して」「何でもいい」→ 即提案
    force_propose_keywords = [
        "とりあえず", "何でもいい", "なんでもいい", "お任せ", "おまかせ",
        "提案して", "決めて", "教えて", "選んで",
    ]
    if any(kw in last_user_msg for kw in force_propose_keywords):
        return {
            "ready_to_propose": True,
            "next_question": None,
            "understood": {},
            "preferences_found": [],
        }

    # 具体的なキーワードが含まれている → 意図が十分明確 → 即提案
    quick_patterns = _QUICK_PROPOSE_PATTERNS.get(ai_type, [])
    all_user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    )
    if any(kw in all_user_text for kw in quick_patterns):
        # ただし好き嫌いの抽出は必要なので LLM を呼ぶ（prefs only mode）
        prefs = _extract_preferences_only(messages, ai_type)
        return {
            "ready_to_propose": True,
            "next_question": None,
            "understood": {},
            "preferences_found": prefs,
        }

    # 最初の1ターンだけで発言が非常に短い（5文字以内）→ 絶対に質問
    if len(messages) <= 2 and len(last_user_msg.strip()) <= 5:
        pass  # 以下の LLM 判定へ（強制質問ではなく LLM に委ねる）

    recent = messages[-6:] if len(messages) > 6 else messages
    conv_text = "\n".join([
        f"{'ユーザー' if m['role']=='user' else 'AI'}: {m['content'][:200]}"
        for m in recent
    ])

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=[
                {"role": "system", "content": INTENT_ANALYSIS_PROMPT},
                {"role": "user", "content": f"AIタイプ: {ai_type}\n\n会話:\n{conv_text}"},
            ],
        )
        raw = res.choices[0].message.content.strip()
        data = json.loads(raw.replace("```json", "").replace("```", "").strip())
        return {
            "ready_to_propose":  data.get("ready_to_propose", True),
            "next_question":     data.get("next_question"),
            "understood":        data.get("understood", {}),
            "preferences_found": data.get("understood", {}).get("preferences_found", []),
        }
    except Exception as e:
        print(f"[Clarifier] 意図分析エラー: {e}")
        return {
            "ready_to_propose": True,
            "next_question": None,
            "understood": {},
            "preferences_found": [],
        }


def _extract_preferences_only(messages: list, ai_type: str) -> list:
    """
    提案が即座に可能な場合でも、会話中の好き嫌い情報だけを抽出する。
    LLM呼び出しコストを最小化するため軽量プロンプトを使う。
    """
    all_user_text = "\n".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    )
    # 嫌い・好きキーワードがなければスキップ
    dislike_signals = ["嫌い", "苦手", "食べられない", "アレルギー", "やだ", "無理", "できない"]
    like_signals    = ["好き", "好みは", "よく食べる", "いつも", "気に入っ"]
    if not any(s in all_user_text for s in dislike_signals + like_signals):
        return []
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "以下の発言から好き嫌い情報のみをJSONで抽出してください（余計なテキスト不要）。\n"
                    "形式: [{\"key\":\"項目\",\"value\":\"値\",\"sentiment\":\"like/dislike\"}]\n\n"
                    "発言: " + all_user_text[:300]
                )
            }]
        )
        raw = res.choices[0].message.content.strip()
        return json.loads(raw.replace("```json","").replace("```","").strip())
    except Exception:
        return []


def count_clarification_questions(messages: list) -> int:
    """
    会話の中でAIが既に深掘り質問した回数をカウントする。
    フロントから来る messages の assistant content は plain text の場合があるため、
    JSON パース失敗時はターン数ベースのヒューリスティックを使う。
    """
    count = 0
    assistant_turns = 0
    for m in messages:
        if m.get("role") == "assistant":
            assistant_turns += 1
            text = m.get("content", "")
            if not isinstance(text, str):
                continue
            # ① JSON内の needs_clarification フラグを検出
            try:
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                if data.get("needs_clarification") or data.get("clarification_question"):
                    count += 1
                    continue
            except Exception:
                pass
            # ② plain text の場合: 質問っぽい文末・キーワードで検出
            # （clarifier が返す質問文のパターンにマッチ）
            clarify_signals = [
                "？", "ですか？", "でしょうか？",
                "教えてください", "聞かせてください",
                "どんな", "なぜ", "誰と", "いつ頃",
            ]
            # 短い質問文（200文字以内）かつ質問シグナルを含む
            if len(text) <= 200 and any(sig in text for sig in clarify_signals):
                # ただし提案文（plans/ホテル名など）を含む長い文は除外
                if not any(kw in text for kw in ["プラン", "おすすめ", "ホテル", "商品", "レシピ"]):
                    count += 1
    return count


def build_clarification_response(question: str, ai_type: str, suggestions: list = None) -> dict:
    """深掘り質問のレスポンスを生成する"""
    if suggestions is None:
        suggestions = ["もう少し詳しく教えます", "とりあえず提案してください", "別の角度から話します"]
    
    return {
        "ai": ai_type,
        "reply": question,
        "needs_clarification": True,
        "suggestions": suggestions,
    }
