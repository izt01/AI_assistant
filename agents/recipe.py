"""
料理提案AI
- レシピ・献立提案: GPT-4o の知識のみで回答
- 近隣スーパー検索: 位置情報（lat/lng）がある場合のみ Google Maps で検索
"""
from .base import BaseAgent
from tools.maps import search_nearby


class RecipeAgent(BaseAgent):
    AI_TYPE = "recipe"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": (
                "ユーザーの位置情報（lat/lng）が提供されている場合に限り、"
                "近くのスーパー・食料品店を検索する。"
                "レシピ回答を返した後、買い物リストを案内するタイミングで呼ぶこと。"
                "位置情報（lat/lng）がない場合はこのツールを呼ばないこと。"
                "keyword は必ず 'スーパー 食料品' を使うこと。"
            ),
            "parameters": {"type": "object", "properties": {
                "lat":     {"type": "number", "description": "緯度"},
                "lng":     {"type": "number", "description": "経度"},
                "keyword": {"type": "string", "description": "検索キーワード（'スーパー 食料品' を推奨）"},
                "radius":  {"type": "number", "description": "検索半径メートル（デフォルト1500）"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {"search_nearby": lambda a: search_nearby(**a)}