"""
買い物提案AI
楽天商品検索はバックエンド（Python）の search_products ツールで行う。
CORSエラー・APIキー漏洩を防ぐため、ブラウザから楽天APIを直接叩かない。
"""
from .base import BaseAgent
from tools import search_nearby
from tools.rakuten import search_products


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    TOOLS = [
        # ── 楽天市場 商品検索（最優先で使うツール）─────────────────────
        {"type": "function", "function": {
            "name": "search_products",
            "description": (
                "楽天市場で商品を検索する。"
                "ユーザーが商品を探している・比較したい・買い替えたい・購入を検討している場合は"
                "必ずこのツールを呼ぶこと。深掘り質問が完了してキーワードが決まったら即座に呼ぶ。"
                "search_nearbyより先に呼ぶこと。"
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
        # ── 近くの実店舗検索（位置情報がある場合・商品検索後の補足として使う）
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": (
                "ユーザーの近くにある実店舗を検索する。"
                "位置情報がある場合のみ使用。商品検索(search_products)の後、"
                "補足として実店舗情報を追加する場合に使う。"
            ),
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
