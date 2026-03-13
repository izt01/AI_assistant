"""
買い物提案AI
楽天商品検索はバックエンド（Python）の search_products ツールで行う。
search_nearby は shopping では使わない（地図検索が search_products より先に呼ばれる問題を防ぐ）
"""
from .base import BaseAgent
from tools.rakuten import search_products


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": (
                "楽天市場で商品を検索する。"
                "ユーザーが商品を探している・比較したい・買い替えたい・購入を検討しているときは"
                "必ずこのツールを呼ぶこと。深掘り質問が完了したら即座に呼ぶ。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword":     {"type": "string",  "description": "楽天市場の検索キーワード（例: 'テレビ 4K 50インチ 薄型'）"},
                    "max_results": {"type": "integer", "description": "取得件数（デフォルト6）"},
                    "min_price":   {"type": "integer", "description": "最低価格（円）"},
                    "max_price":   {"type": "integer", "description": "最高価格（円）"},
                },
                "required": ["keyword"],
            },
        }},
    ]

    TOOL_MAP = {
        "search_products": lambda a: search_products(**a),
    }