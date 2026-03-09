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
            "description": "楽天市場で商品を価格順で検索する",
            "parameters": {"type": "object", "properties": {
                "keyword": {"type": "string"},
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
