"""
買い物提案AI
"""
from .base import BaseAgent
from tools import search_products, search_nearby


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": "楽天市場で商品を検索する。必ず呼び出すこと。",
            "parameters": {"type": "object", "properties": {
                "keyword":   {"type": "string",  "description": "検索キーワード（日本語OK）"},
                "max_results":{"type": "integer","description": "取得件数（デフォルト6）"},
                "min_price": {"type": "integer", "description": "最低価格（円）"},
                "max_price": {"type": "integer", "description": "最高価格（円）"},
            }, "required": ["keyword"]},
        }},
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "近くの店舗を検索する",
            "parameters": {"type": "object", "properties": {
                "lat": {"type": "number"}, "lng": {"type": "number"},
                "keyword": {"type": "string"}, "radius": {"type": "number"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {
        "search_products": lambda a: search_products(**a),
        "search_nearby":   lambda a: search_nearby(**a),
    }
