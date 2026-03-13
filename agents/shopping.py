"""
買い物提案AI
※ 楽天商品検索はフロントエンド（ブラウザ）から直接行うため、
  バックエンドでは search_products を呼ばない。
"""
from .base import BaseAgent
from tools import search_nearby


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    # 近くの実店舗検索のみ残す（楽天はフロント直接）
    TOOLS = [
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "ユーザーの近くにある実店舗を検索する（位置情報がある場合のみ使用）",
            "parameters": {"type": "object", "properties": {
                "lat":     {"type": "number"},
                "lng":     {"type": "number"},
                "keyword": {"type": "string"},
                "radius":  {"type": "number"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {
        "search_nearby": lambda a: search_nearby(**a),
    }
