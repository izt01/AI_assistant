"""
買い物提案AI
楽天商品検索はバックエンド（Python）で行い、CORSエラーを回避する。
"""
from .base import BaseAgent
from tools import search_nearby
from tools.rakuten import search_products


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    TOOLS = [
        # ── 楽天市場 商品検索（バックエンド経由でCORSなし）──────────────
        {"type": "function", "function": {
            "name": "search_products",
            "description": (
                "楽天市場で商品を検索する。"
                "ユーザーが商品を探している・比較したい・購入を検討している場合に呼ぶ。"
                "深掘り質問が完了して検索キーワードが決まった後に呼ぶこと。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword":     {"type": "string",  "description": "楽天市場での検索キーワード（例: 'フライパン IH対応 軽量'）"},
                    "max_results": {"type": "integer", "description": "取得件数（デフォルト6、最大10）"},
                    "min_price":   {"type": "integer", "description": "最低価格（円）"},
                    "max_price":   {"type": "integer", "description": "最高価格（円）"},
                },
                "required": ["keyword"],
            },
        }},
        # ── 近くの実店舗検索（位置情報がある場合のみ）────────────────────
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "ユーザーの近くにある実店舗を検索する（位置情報がある場合のみ使用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat":     {"type": "number"},
                    "lng":     {"type": "number"},
                    "keyword": {"type": "string"},
                    "radius":  {"type": "number"},
                },
                "required": ["lat", "lng", "keyword"],
            },
        }},
    ]

    TOOL_MAP = {
        "search_products": lambda a: search_products(**a),
        "search_nearby":   lambda a: search_nearby(**a),
    }
