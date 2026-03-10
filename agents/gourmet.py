"""
グルメ（飲食店紹介）AI
- ユーザーが食べたいものの意図を自然言語から抽出
- Google Maps Places API で周辺の飲食店を検索
- 料理ジャンル・予算・雰囲気・距離などで絞り込み提案
"""
from .base import BaseAgent
from tools import search_nearby


class GourmetAgent(BaseAgent):
    AI_TYPE = "gourmet"

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "search_restaurants",
                "description": (
                    "ユーザーが食べたいものや気分から周辺の飲食店・レストランを検索する。"
                    "keyword には料理ジャンルや店の特徴（例: 'ラーメン', '焼肉 個室', 'カフェ 静か'）を入れる。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lat":     {"type": "number",  "description": "緯度（ユーザーの現在地）"},
                        "lng":     {"type": "number",  "description": "経度（ユーザーの現在地）"},
                        "keyword": {"type": "string",  "description": "検索キーワード（料理ジャンル・雰囲気など）"},
                        "radius":  {"type": "number",  "description": "検索半径（メートル）。デフォルト800"},
                    },
                    "required": ["lat", "lng", "keyword"],
                },
            },
        }
    ]

    TOOL_MAP = {
        "search_restaurants": lambda a: search_nearby(
            lat=a["lat"],
            lng=a["lng"],
            keyword=a.get("keyword", "レストラン"),
            radius=int(a.get("radius", 800)),
        )
    }
