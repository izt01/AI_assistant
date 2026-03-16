"""
専門AI基底クラス
- 記憶の注入（プロンプトへの組み込み）
- Function Callingループの共通処理
- 会話終了時の記憶保存
を共通化する。各AIはこれを継承してSYSTEM_PROMPTとTOOLSだけ定義すればよい。
"""
import json
import uuid
from openai import OpenAI
from memory import load_memory, build_memory_prompt, extract_and_save_memory
from prompts import get_prompt

client = OpenAI()


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

    def run(self, messages: list, user_id: str = "default") -> dict:
        """専門AIを実行してパース済みdictを返す"""
        session_id = str(uuid.uuid4())
        system     = self.build_system(user_id)
        msgs       = [{"role": "system", "content": system}] + messages

        last_assistant_msg = None  # 最後のassistantメッセージを確実に追跡

        for i in range(3):
            kwargs = {
                "model":      "gpt-4o",
                "max_tokens": 1500,
                "messages":   msgs,
            }
            if self.TOOLS:
                kwargs["tools"] = self.TOOLS
                # 1回目はtool呼び出しを強制、2回目以降はauto
                kwargs["tool_choice"] = "auto"

            res = client.chat.completions.create(**kwargs)
            msg = res.choices[0].message

            if not getattr(msg, "tool_calls", None):
                last_assistant_msg = msg
                break

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
        else:
            last_assistant_msg = msg

        if last_assistant_msg is None:
            last_assistant_msg = msg

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