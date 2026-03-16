"""
買い物提案AI
楽天市場商品検索 + Google Maps 近隣実店舗検索 の2ツールを使用する。
- search_products: 楽天市場で商品をオンライン検索
- search_nearby:   位置情報がある場合のみ近隣の実店舗を検索
"""
from .base import BaseAgent
from tools.rakuten import search_products
from tools.maps import search_nearby


class ShoppingAgent(BaseAgent):
    AI_TYPE = "shopping"

    TOOLS = [
        # ── 楽天市場 商品検索 ──────────────────────────────────
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
        # ── Google Maps 近隣実店舗検索 ─────────────────────────
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": (
                "ユーザーの位置情報（lat/lng）が提供されている場合に限り、"
                "近くの取り扱い実店舗を検索する。"
                "位置情報がない場合はこのツールを呼ばないこと。"
                "search_products の後に呼ぶこと（商品検索を先に行う）。"
                "keyword には商品カテゴリを日本語で指定する。"
                "例: 'ホームセンター', '電器店 家電', 'スポーツ用品店'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat":     {"type": "number", "description": "緯度"},
                    "lng":     {"type": "number", "description": "経度"},
                    "keyword": {"type": "string", "description": "検索キーワード（例: 'ホームセンター', '電器店'）"},
                    "radius":  {"type": "number", "description": "検索半径メートル（デフォルト1500）"},
                },
                "required": ["lat", "lng", "keyword"],
            },
        }},
    ]

    TOOL_MAP = {
        "search_products": lambda a: search_products(**a),
        "search_nearby":   lambda a: search_nearby(**a),
    }