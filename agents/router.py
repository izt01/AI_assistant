"""
ルーターAI ― どの専門AIに振り分けるかを判定する
プロンプトは prompts/packs/{PROMPT_PACK}/router.yaml から読み込む
"""
import json
from openai import OpenAI
from prompts import get_prompt

client = OpenAI()


def route(messages: list) -> str:
    try:
        system = get_prompt("router")
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=30,
            messages=[{"role": "system", "content": system}] + messages[-6:],
        )
        data = json.loads(res.choices[0].message.content
                          .replace("```json","").replace("```","").strip())
        return data.get("ai", "general")
    except Exception as e:
        print(f"[Router] {e}")
        return "general"
