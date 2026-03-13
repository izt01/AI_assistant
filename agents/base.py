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

        for _ in range(3):
            kwargs = {
                "model":      "gpt-4o",
                "max_tokens": 1500,
                "messages":   msgs,
            }
            if self.TOOLS:
                kwargs["tools"]       = self.TOOLS
                kwargs["tool_choice"] = "auto"

            res = client.chat.completions.create(**kwargs)
            msg = res.choices[0].message

            if not getattr(msg, "tool_calls", None):
                break

            msgs.append(msg)
            for tc in msg.tool_calls:
                args   = json.loads(tc.function.arguments)
                fn     = self.TOOL_MAP.get(tc.function.name, lambda a: {})
                result = fn(args)
                msgs.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result, ensure_ascii=False),
                })

        text = msg.content or "{}"
        try:
            parsed = json.loads(text.replace("```json", "").replace("```", "").strip())
        except Exception:
            parsed = {"ai": self.AI_TYPE, "message": text, "suggestions": []}

        parsed["ai"] = self.AI_TYPE

        # ツール結果をパース済みdictに追加
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "tool":
                try:
                    data = json.loads(m["content"])
                    t = data.get("type")
                    if t == "hotels":   parsed["_hotels"]   = data
                    if t == "products": parsed["_products"] = data
                    if t == "places":   parsed["_places"]   = data
                except Exception:
                    pass

        # 記憶を非同期的に保存（5ターン以上経ったら）
        if len(messages) >= 5:
            try:
                extract_and_save_memory(user_id, self.AI_TYPE, messages, session_id)
            except Exception as e:
                print(f"[BaseAgent] 記憶保存スキップ: {e}")

        return parsed
