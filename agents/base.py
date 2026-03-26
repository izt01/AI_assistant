"""
専門AI基底クラス
- 記憶の注入（プロンプトへの組み込み）
- Function Callingループの共通処理
- 会話終了時の記憶保存
- 深掘り質問（clarifier）による意図理解の強化
を共通化する。各AIはこれを継承してSYSTEM_PROMPTとTOOLSだけ定義すればよい。
"""
import json
import uuid
from openai import OpenAI
from memory import load_memory, build_memory_prompt, extract_and_save_memory
from prompts import get_prompt
from .clarifier import analyze_intent, count_clarification_questions, build_clarification_response

client = OpenAI()

# 深掘り質問を行うAIタイプ（ツール検索系は意図理解が特に重要）
CLARIFY_ENABLED_TYPES = {"travel", "shopping", "appliance", "health", "gourmet", "recipe", "diy"}



# ── AI別専門外キーワード辞書 ──────────────────────────────────
# 各AIが担当しない話題のキーワードと、推奨リダイレクト先
OUT_OF_SCOPE_MAP = {
    "gourmet": {
        "redirect_to": [
            ("home",     ["冷蔵庫", "洗濯機", "エアコン", "テレビ", "家電", "掃除機", "電子レンジ",
                          "炊飯器", "ルンバ", "ドラム式", "インテリア", "照明", "ソファ", "カーテン"]),
            ("travel",   ["旅行", "ホテル", "観光", "新幹線", "飛行機", "宿", "温泉"]),
            ("shopping", ["買い物", "ショッピング", "プレゼント", "ギフト", "通販", "Amazon", "楽天市場"]),
            ("health",   ["ダイエット", "筋トレ", "運動", "フィットネス", "睡眠改善", "体重"]),
            ("diy",      ["DIY", "修理", "リフォーム", "棚を作", "壁を直", "ペンキ"]),
            ("recipe",   ["レシピ", "作り方", "料理を作", "献立", "手料理", "クックパッド"]),
        ],
        "self_keywords": ["食べ", "飲み", "ランチ", "ディナー", "お店", "レストラン", "カフェ",
                          "居酒屋", "ラーメン", "寿司", "焼肉", "イタリアン", "外食", "何食べ",
                          "お腹すい", "腹減", "今夜", "今日の昼", "うまい", "おいしい", "グルメ"],
    },
    "travel": {
        "redirect_to": [
            ("home",     ["冷蔵庫", "洗濯機", "エアコン", "テレビ", "家電", "掃除機", "インテリア"]),
            ("shopping", ["買い物", "プレゼント", "ギフト", "商品", "通販"]),
            ("health",   ["ダイエット", "筋トレ", "運動", "フィットネス"]),
            ("diy",      ["DIY", "修理", "リフォーム", "棚を作", "壁を直"]),
            ("recipe",   ["レシピ", "料理を作", "献立", "手料理"]),
            ("gourmet",  ["近くのレストラン", "近くのお店", "外食したい", "今夜どこで食べ",
                          "食べたい", "食べに行き", "魚料理", "肉料理",
                          "ランチ", "ディナー", "お腹すい", "近くで食べ"]),
        ],
        "self_keywords": ["旅行", "旅", "観光", "ホテル", "宿", "温泉", "飛行機", "新幹線",
                          "出かけ", "どこかに行き", "旅程", "プラン", "1泊", "2泊", "海外", "国内"],
    },
    "shopping": {
        "redirect_to": [
            ("home",     ["冷蔵庫が欲しい", "洗濯機が欲しい", "エアコンが欲しい",
                          "家電を選び", "家電を教えて", "家電おすすめ",
                          "インテリア", "部屋をコーディネート", "照明を変え"]),
            ("travel",   ["旅行", "ホテル", "観光"]),
            ("health",   ["ダイエット", "筋トレ", "運動"]),
            ("diy",      ["DIY", "修理", "リフォーム"]),
            ("recipe",   ["レシピ", "料理を作", "献立"]),
            ("gourmet",  ["外食", "レストラン", "お店を探",
                          "食べたい", "食べに行き", "飲食",
                          "ランチ", "ディナー", "魚料理", "肉料理",
                          "ラーメン", "寿司", "焼肉", "お腹すい",
                          "何食べ", "どこかで食べ", "近くで食べ", "グルメ"]),
        ],
        "self_keywords": ["買いたい", "欲しい", "おすすめ", "比較", "商品", "価格", "安い",
                          "ショッピング", "プレゼント", "ギフト", "通販", "レビュー"],
    },
    "home": {
        "redirect_to": [
            ("travel",   ["旅行", "ホテル", "観光"]),
            ("shopping", ["服", "食品", "本", "おもちゃ", "スポーツ用品"]),
            ("health",   ["ダイエット", "筋トレ", "運動"]),
            ("diy",      ["自分で作", "手作り", "ハンドメイド", "修理したい", "直したい"]),
            ("recipe",   ["レシピ", "料理を作", "献立"]),
            ("gourmet",  ["外食", "レストラン", "お店を探", "食べたい", "食べに行き",
                          "ランチ", "ディナー", "魚料理", "肉料理", "お腹すい",
                          "何食べ", "どこかで食べ", "近くで食べ", "グルメ"]),
        ],
        "self_keywords": ["家電", "冷蔵庫", "洗濯機", "エアコン", "テレビ", "掃除機",
                          "インテリア", "照明", "ソファ", "収納", "部屋", "家具"],
    },
    "health": {
        "redirect_to": [
            ("home",     ["冷蔵庫", "洗濯機", "家電"]),
            ("travel",   ["旅行", "ホテル", "観光"]),
            ("shopping", ["買い物", "プレゼント", "商品"]),
            ("diy",      ["DIY", "修理", "リフォーム"]),
            ("recipe",   ["レシピ", "料理を作", "献立"]),
            ("gourmet",  ["外食", "レストラン", "お店を探", "食べたい", "食べに行き",
                          "ランチ", "ディナー", "魚料理", "肉料理", "お腹すい",
                          "どこかで食べ", "近くで食べ"]),
        ],
        "self_keywords": ["健康", "運動", "ダイエット", "筋トレ", "体重", "睡眠", "疲れ",
                          "体調", "ストレス", "フィットネス", "カロリー", "栄養"],
    },
    "recipe": {
        "redirect_to": [
            ("home",     ["冷蔵庫", "洗濯機", "家電"]),
            ("travel",   ["旅行", "ホテル", "観光"]),
            ("shopping", ["買い物", "プレゼント", "商品"]),
            ("diy",      ["DIY", "修理", "リフォーム"]),
            ("health",   ["ダイエット", "筋トレ", "運動プラン", "フィットネス"]),
            ("gourmet",  ["お店を探", "レストランを探", "外食したい", "どこかで食べ",
                          "食べに行き", "ランチ", "ディナー", "近くで食べ", "おいしいお店"]),
        ],
        "self_keywords": ["レシピ", "料理", "作り方", "献立", "食材", "炒め", "煮る",
                          "焼く", "クックパッド", "手料理", "簡単料理", "時短"],
    },
    "diy": {
        "redirect_to": [
            ("home",     ["新しい家電", "家電を買", "冷蔵庫が欲しい", "洗濯機を買"]),
            ("travel",   ["旅行", "ホテル", "観光"]),
            ("shopping", ["商品を探", "買いたい", "おすすめを教えて"]),
            ("health",   ["ダイエット", "筋トレ", "運動"]),
            ("recipe",   ["レシピ", "料理を作", "献立"]),
            ("gourmet",  ["外食", "レストラン", "お店を探", "食べたい", "食べに行き",
                          "ランチ", "ディナー", "魚料理", "肉料理", "お腹すい",
                          "どこかで食べ", "近くで食べ"]),
        ],
        "self_keywords": ["DIY", "自分で作", "修理", "修繕", "リフォーム", "棚", "塗装",
                          "ペンキ", "壁", "床", "ハンドメイド", "工具", "材料"],
    },
}

AI_NAME_JP = {
    "gourmet":  "グルメAI",
    "travel":   "旅行AI",
    "shopping": "買い物AI",
    "home":     "家電・インテリアAI",
    "health":   "健康AI",
    "recipe":   "料理AI",
    "diy":      "DIY AI",
    "appliance":"家電・インテリアAI",
}

def _check_out_of_scope(ai_type: str, user_message: str):
    """
    ユーザーのメッセージが現在のAIの専門外かどうかを判定する。
    専門外なら {"redirect_to_ai": "xxx", "message": "..."} を返す。
    専門内またはAI設定がなければ None を返す。

    判定順序:
    1. redirect_to キーワードをまず確認（明確な専門外ワード優先）
    2. self_keywords に含まれていれば専門内
    3. どちらにも該当しなければ None（判定不能 → 通常応答）
    """
    config = OUT_OF_SCOPE_MAP.get(ai_type)
    if not config:
        return None

    # ① まず専門外キーワードを先にチェック（冷蔵庫・魚料理など明確なワード）
    for target_ai, keywords in config["redirect_to"]:
        for kw in keywords:
            if kw in user_message:
                target_name = AI_NAME_JP.get(target_ai, target_ai)
                return {
                    "redirect_to_ai": target_ai,
                    "message": f"このAIでは対応できません。{target_name}にお聞きください😊",
                }

    # ② 専門キーワードが含まれていれば専門内（専門外に当たらなかった場合のみ）
    for kw in config["self_keywords"]:
        if kw in user_message:
            return None

    return None

class BaseAgent:
    AI_TYPE  = "general"
    TOOLS    = []
    TOOL_MAP = {}

    def get_system_prompt(self) -> str:
        """YAMLからシステムプロンプトを読み込む（再起動不要で即反映）"""
        try:
            return get_prompt(self.AI_TYPE)
        except FileNotFoundError:
            return f"あなたは{self.AI_TYPE}の専門家AIです。日本語で丁寧に答えてください。"

    def build_system(self, user_id: str) -> str:
        """記憶とスコアを注入したシステムプロンプトを生成する"""
        from memory.db import get_conn
        import psycopg2.extras

        # overall_scoreを取得してbuild_memory_promptに渡す
        overall_score = 0.0
        try:
            with get_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT overall_score FROM lu_match_scores WHERE user_id=%s",
                        (user_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        overall_score = float(row["overall_score"] or 0)
        except Exception:
            pass

        memory   = load_memory(user_id, self.AI_TYPE)
        mem_text = build_memory_prompt(memory, self.AI_TYPE, overall_score=overall_score)

        if mem_text:
            # スコアが高いほど記憶の活用指示を強化する
            if overall_score >= 50:
                usage_instruction = (
                    "上記の記憶をすべて前提として使い、このユーザー専用に最適化された提案をすること。"
                    "★印の好みは確認なしで即採用。却下済みの提案（✕印）は絶対に繰り返さないこと。"
                    "好評履歴（✓印）に近い提案を優先的に出すこと。"
                )
            elif overall_score >= 25:
                usage_instruction = (
                    "上記の記憶を最大限活用し、このユーザーに最適化された提案をすること。"
                    "確実な好みは確認なしで前提として使う。却下済みの提案（✕印）は絶対に繰り返さないこと。"
                )
            elif overall_score >= 8:
                usage_instruction = (
                    "上記の記憶を参考にしながら提案すること。"
                    "「確実」の好みは前提として使ってよい。「推測」は一言確認してから使うこと。"
                    "却下された提案は繰り返さないこと。"
                )
            else:
                usage_instruction = (
                    "記憶はまだ少ないため参考程度に使い、足りない情報は質問して補うこと。"
                    "却下された提案は繰り返さないこと。"
                )

            return (
                self.get_system_prompt()
                + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + mem_text
                + "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + usage_instruction
            )
        return self.get_system_prompt()

    def _save_preferences_from_clarifier(self, user_id: str, preferences_found: list):
        """clarifierが検出した好き嫌いをDBに即時保存する"""
        if not preferences_found:
            return
        try:
            from memory.db import get_conn
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for pref in preferences_found:
                        key   = pref.get("key")
                        value = pref.get("value")
                        sentiment = pref.get("sentiment", "like")
                        if not key or not value:
                            continue
                        # 嫌いなものは負のconfidenceで保存、好きなものは正
                        confidence = -3 if sentiment == "dislike" else 2
                        cur.execute("""
                            INSERT INTO user_preferences (user_id, ai_type, key, value, confidence, updated_at)
                            VALUES (%s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (user_id, ai_type, key) DO UPDATE SET
                                value      = EXCLUDED.value,
                                confidence = LEAST(GREATEST(user_preferences.confidence + %s, -10), 10),
                                updated_at = NOW()
                        """, (user_id, self.AI_TYPE, key, value, confidence, confidence))
                conn.commit()
            print(f"[BaseAgent] 好み保存: {preferences_found}")

        except Exception as e:
            print(f"[BaseAgent] 好み保存エラー: {e}")

        # ── lu_pref_* / lu_constraints への即時同期（try/except を分離）──
        try:
            from memory.user_memory import _sync_pref_to_lu_tables
            _sync_pref_to_lu_tables(user_id, self.AI_TYPE, preferences_found)
        except Exception as e2:
            print(f"[BaseAgent] lu_sync エラー: {e2}")

    def run(self, messages: list, user_id: str = "default") -> dict:
        """専門AIを実行してパース済みdictを返す"""
        session_id = str(uuid.uuid4())

        # -- Travel AI: depart city check (runs before clarifier) --
        if self.AI_TYPE == "travel" and len(messages) >= 1:
            import re as _re_travel
            all_text = " ".join(
                m.get("content", "") for m in messages if isinstance(m, dict)
            )
            depart_keywords = (
                r'(\u6771\u4eac|\u5927\u962a|\u540d\u53e4\u5c4b|\u672d\u5e4c|\u798f\u5ca1|\u4ed5\u5409|\u5e83\u5cf6|\u6c96\u7e04|\u4eac\u90fd|\u795e\u6238|\u6a2a\u6d5c'
                r'|\u304b\u3089|\u51fa\u767a|\u767a|\u7fbd\u7530|\u6210\u7530|\u95a2\u897f\u7a7a\u6e2f|\u4f0a\u4e39|\u4e2d\u90e8|\u65b0\u5343\u6b73'
                r'|\u81ea\u5b85|\u5bb6|\u73fe\u5728\u5730|\u4eca\u3044\u308b|\u4f4f\u3093\u3067\u3044\u308b|\u4f4f\u3093\u3067\u308b|\u5730\u5143|\u5b9f\u5bb6)'
            )
            dest_keywords = (
                r'(\u884c\u304d\u305f\u3044|\u65c5\u884c|\u89b3\u5149|\u8a2a\u308c|\u8a2a\u554f|\u884c\u3053\u3046|\u884c\u3051\u305f\u3089|\u8a2a\u306d\u305f\u3044'
                r'|\u898b\u305f\u3044|\u3081\u3050\u308a|\u30c4\u30a2\u30fc|\u65c5\u306b|\u65c5\u3078|\u65c5\u3059\u308b)'
            )
            asked_keywords = (
                r'(\u3069\u3061\u3089\u304b\u3089|\u3054\u51fa\u767a|\u51fa\u767a\u5730|\u304a\u4f4f\u307e\u3044|\u3069\u3053\u304b\u3089|\u51fa\u767a\u3059\u308b\u90fd\u5e02)'
            )
            has_depart       = bool(_re_travel.search(depart_keywords,  all_text))
            has_dest         = bool(_re_travel.search(dest_keywords,    all_text))
            already_asked    = bool(_re_travel.search(asked_keywords,   all_text))
            if has_dest and not has_depart and not already_asked and len(messages) <= 3:
                return {
                    "ai": self.AI_TYPE,
                    "reply": (
                        "\u3069\u3061\u3089\u304b\u3089\u3054\u51fa\u767a\u306e\u3054\u4e88\u5b9a\u3067\u3059\u304b\uff1f "
                        "\u51fa\u767a\u5730\u3092\u6559\u3048\u3066\u3044\u305f\u3060\u304f\u3068\u3001"
                        "\u4ea4\u901a\u624b\u6bb5\u30fb\u6642\u523b\u30fb\u6599\u91d1\u307e\u3067\u542b\u3081\u305f"
                        "\u65c5\u884c\u30d7\u30e9\u30f3\u3092\u3054\u63d0\u6848\u3067\u304d\u307e\u3059\uff01"
                    ),
                    "needs_more_info": True,
                    "clarification_type": "depart_city",
                    "suggestions": [
                        "\u6771\u4eac\u304b\u3089",
                        "\u5927\u962a\u304b\u3089",
                        "\u81ea\u5206\u306e\u73fe\u5728\u5730\u304b\u3089",
                        "\u51fa\u767a\u5730\u306a\u3057\u3067\u30d7\u30e9\u30f3\u3060\u3051\u898b\u305f\u3044",
                    ],
                }

        # ── 専門外チェック（最初のユーザーメッセージのみ）──────────
        # clarifierより先に実行し、専門外なら即リダイレクト応答を返す
        first_user_messages = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
        if len(first_user_messages) == 1:  # 会話の1ターン目のみ
            first_msg = first_user_messages[0].get("content", "")
            oos = _check_out_of_scope(self.AI_TYPE, first_msg)
            if oos:
                return {
                    "ai":            self.AI_TYPE,
                    "reply":         oos["message"],
                    "redirect_to_ai": oos["redirect_to_ai"],
                    "suggestions":   [],
                    "needs_clarification": False,
                }

        # ── 深掘り質問フェーズ ──────────────────────────────
        if self.AI_TYPE in CLARIFY_ENABLED_TYPES and len(messages) >= 1:
            q_count = count_clarification_questions(messages)
            intent  = analyze_intent(messages, self.AI_TYPE, q_count)

            # clarifierが検出した好き嫌いを即時保存
            if intent.get("preferences_found"):
                self._save_preferences_from_clarifier(user_id, intent["preferences_found"])

            # まだ意図が不明で質問回数が少ない → 深掘り質問を返す
            if not intent["ready_to_propose"] and intent.get("next_question"):
                return build_clarification_response(
                    question=intent["next_question"],
                    ai_type=self.AI_TYPE,
                )

        system     = self.build_system(user_id)

        # 旅行AIは必ずJSON返却を先頭命令として強制
        if self.AI_TYPE == "travel":
            _jlines = [
                "CRITICAL INSTRUCTION - HIGHEST PRIORITY:",
                "You MUST respond ONLY with a raw JSON object.",
                "First character MUST be {. Last character MUST be }.",
                "NEVER use Markdown (####, ###, **, -, *). NEVER use code blocks.",
                "Even if tools fail, ALWAYS return JSON with plans/days/schedule arrays.",
                "NO apologies. NO alternative text. NO explanations outside JSON.",
                "---",
            ]
            system = "\n".join(_jlines) + "\n" + system

        msgs       = [{"role": "system", "content": system}] + messages

        last_assistant_msg = None  # 最後のassistantメッセージを確実に追跡
        # トークン使用量の累積（APIコールのたびに加算）
        _total_input_tokens  = 0
        _total_output_tokens = 0
        _model_used          = "gpt-4o"

        # GPT-4oが「了解しました。少々お待ちください」などの中間テキストを
        # ツール呼び出し前に返すパターンを検知するパターン群
        INTERIM_PATTERNS = [
            "お待ちください", "調べます", "探します", "提案します",
            "確認します", "検索します", "プランを", "ご提案",
            "少々", "しばらく", "おすすめ", "調べて",
        ]

        for i in range(5):  # 最大5回（通常: ①中間テキスト ②ツール呼び出し ③最終返答）
            kwargs = {
                "model":      "gpt-4o",
                "max_tokens": 4000,
                "messages":   msgs,
            }
            if self.TOOLS:
                kwargs["tools"] = self.TOOLS
                kwargs["tool_choice"] = "auto"

            res = client.chat.completions.create(**kwargs)
            msg = res.choices[0].message

            # トークン使用量を累積
            if hasattr(res, "usage") and res.usage:
                _total_input_tokens  += res.usage.prompt_tokens or 0
                _total_output_tokens += res.usage.completion_tokens or 0
                _model_used = res.model or "gpt-4o"

            # ── ツール呼び出しがある場合 → ツールを実行してループ続行 ──
            if getattr(msg, "tool_calls", None):
                msgs.append(msg)
                for tc in msg.tool_calls:
                    args   = json.loads(tc.function.arguments)
                    fn     = self.TOOL_MAP.get(tc.function.name, lambda a: {})
                    result = fn(args)
                    print(f"[Tool] {tc.function.name}({args}) → {str(result)[:200]}")
                    msgs.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      json.dumps(result, ensure_ascii=False),
                    })
                continue  # ツール結果を渡して次のループへ

            # ── テキスト返答の場合 ──
            content_text = (msg.content or "").strip()

            # 中間返答パターン（了解テキスト）かつまだリトライ余地がある場合
            # → コンテキストに追加してプランを出すよう促す
            is_interim = (
                self.TOOLS  # ツールを持つAIのみ対象
                and i < 3   # 最初の3回まで中間返答を許容
                and any(p in content_text for p in INTERIM_PATTERNS)
                and len(content_text) < 200  # 短いテキスト（本格的な返答ではない）
                and not content_text.lstrip().startswith("{")  # JSONでない
            )

            if is_interim:
                print(f"[Base] 中間返答を検知（{i+1}回目）: {content_text[:60]}... → リトライ")
                msgs.append(msg)
                # 「続けてプランや検索結果を出力してください」と促す
                msgs.append({
                    "role":    "user",
                    "content": (
                        "Return ONLY a raw JSON object starting with '{' and ending with '}'."
                        " Include plans with days and schedule arrays."
                        " Do NOT use Markdown. Do NOT use #### or - bullet points."
                        " Output JSON directly now."
                    ),
                })
                continue

            # 最終的な返答として確定
            last_assistant_msg = msg
            break

        else:
            last_assistant_msg = msg

        if last_assistant_msg is None:
            last_assistant_msg = msg

        # ── トークン使用量をDBに記録（コスト自前計算） ──────────────
        if _total_input_tokens > 0 or _total_output_tokens > 0:
            try:
                # モデル別コスト計算（$/1M tokens）
                MODEL_COSTS = {
                    "gpt-4o":           {"input": 2.50,  "output": 10.00},
                    "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
                    "gpt-4-turbo":      {"input": 10.00, "output": 30.00},
                    "o1":               {"input": 15.00, "output": 60.00},
                    "o1-mini":          {"input": 3.00,  "output": 12.00},
                    "o3-mini":          {"input": 1.10,  "output": 4.40},
                }
                model_key = next((k for k in MODEL_COSTS if k in _model_used), "gpt-4o")
                rates = MODEL_COSTS[model_key]
                cost_usd = (_total_input_tokens * rates["input"] + _total_output_tokens * rates["output"]) / 1_000_000

                from memory.db import get_conn as _mem_conn
                with _mem_conn() as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            """INSERT INTO admin_cost_logs
                               (id, month, model, input_tokens, output_tokens, cost_usd, recorded_at)
                               VALUES (gen_random_uuid(),
                                       to_char(NOW(),'YYYY-MM'),
                                       %s, %s, %s, %s, NOW())""",
                            (_model_used, _total_input_tokens, _total_output_tokens, round(cost_usd, 6))
                        )
                    _conn.commit()
            except Exception as _e:
                print(f"[Cost] トークン記録エラー: {_e}")

        text = last_assistant_msg.content or "{}"
        # JSONをロバストに抽出（Markdownや前後テキストが混入しても対応）
        def extract_json(s):
            import re as _re_ej
            # コードブロック・Markdown除去
            s = s.replace("```json", "").replace("```", "").strip()
            # 純粋JSONなら直接パース
            try:
                return json.loads(s)
            except Exception:
                pass
            # 最初の { から最後の } を抽出（ネスト対応）
            start = s.find("{")
            if start != -1:
                depth = 0
                end = -1
                in_str = False
                escape = False
                for i in range(start, len(s)):
                    ch = s[i]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\" and in_str:
                        escape = True
                        continue
                    if ch == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                if end != -1:
                    try:
                        return json.loads(s[start:end+1])
                    except Exception:
                        pass
                # ネスト解析失敗時は rfind でシンプルに試す
                end = s.rfind("}")
                if end > start:
                    try:
                        return json.loads(s[start:end+1])
                    except Exception:
                        pass
            return None

        parsed = extract_json(text)
        if parsed is None:
            parsed = {"ai": self.AI_TYPE, "message": text, "suggestions": []}

        parsed["ai"] = self.AI_TYPE

        # messageフィールドの正規化（message / reply どちらでも受け取れるように）
        if "message" in parsed and "reply" not in parsed:
            parsed["reply"] = parsed.pop("message")

        # search_keyword が含まれていればフロントに渡す（楽天ブラウザ検索用）
        if parsed.get("search_keyword"):
            parsed["_search_keyword"] = parsed["search_keyword"]
            print(f"[Shopping] search_keyword={parsed['_search_keyword']}")

        # ツール結果をパース済みdictに追加
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "tool":
                try:
                    data = json.loads(m["content"])
                    t = data.get("type")

                    # ホテル結果（旅行AI）: source フィールドを追加して将来の複数API拡張に対応
                    if t == "hotels":
                        data["source"] = data.get("source", "rakuten")  # ★ 将来: 'agoda' | 'booking'
                        parsed["_hotels"] = data

                    # 海外ホテル結果（旅行AI: Booking.com）
                    if t == "overseas_hotels":
                        data["source"] = "booking"
                        parsed["_overseas_hotels"] = data

                    # 航空券結果（旅行AI）
                    if t == "flights":
                        if data.get("available") and data.get("flights"):
                            parsed["_flights"] = data
                            print(f"[Travel] フライト取得成功: {len(data['flights'])}件")
                        elif data.get("fallback_url"):
                            # API失敗でもスカイスキャナーURLをフロントに渡す
                            parsed["_flight_fallback"] = data
                            print(f"[Travel] フライトfallback設定: {data['fallback_url']}")
                        else:
                            print(f"[Travel] フライト結果なし: available={data.get('available')} fallback={data.get('fallback_url')}")

                    # 商品結果（買い物AI・家電AI・DIY AI）
                    if t == "products":
                        parsed["_products"] = data

                    # ツアー・体験結果（旅行AI）
                    if t == "tours":
                        parsed["_tours"] = data

                    # 位置情報結果: 呼び出し元AIによって格納先キーを変える
                    # - gourmet → _places（飲食店カード）
                    # - shopping → _nearby_stores（近隣実店舗カード）★追加
                    # - recipe  → _nearby_stores（近隣スーパーカード）
                    if t == "places":
                        if self.AI_TYPE == "gourmet":
                            parsed["_places"] = data
                        elif self.AI_TYPE in ("shopping", "recipe"):
                            parsed["_nearby_stores"] = data
                        elif self.AI_TYPE == "travel":
                            # 旅行AIは観光スポット検索なので _places に格納
                            parsed["_places"] = data
                        else:
                            parsed["_places"] = data

                except Exception:
                    pass

        # 記憶を非同期的に保存（5ターン以上経ったら）
        if len(messages) >= 5:
            try:
                extract_and_save_memory(user_id, self.AI_TYPE, messages, session_id)
            except Exception as e:
                print(f"[BaseAgent] 記憶保存スキップ: {e}")

        return parsed