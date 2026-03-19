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
                    "content": "続けて、具体的なプランや検索結果を出力してください。",
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
        # JSONをロバストに抽出（コードブロックや前後テキストが混入しても対応）
        def extract_json(s):
            # コードブロック除去
            s = s.replace("```json", "").replace("```", "").strip()
            # 純粋JSONなら直接パース
            try:
                return json.loads(s)
            except Exception:
                pass
            # 最初の { から最後の } を抽出
            start = s.find("{")
            end   = s.rfind("}")
            if start != -1 and end != -1 and end > start:
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

                    # 航空券結果（旅行AI）
                    if t == "flights":
                        parsed["_flights"] = data

                    # 商品結果（買い物AI・家電AI・DIY AI）
                    if t == "products":
                        parsed["_products"] = data

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