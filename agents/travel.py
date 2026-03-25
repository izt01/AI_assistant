"""
旅行プラン提案AI
- search_hotels:  楽天トラベルでホテルを検索
- search_flights: Amadeus APIで航空券の料金を検索
- search_nearby:  Google Maps で観光スポットを検索
"""
from .base import BaseAgent
from tools import search_hotels, search_nearby, search_flights, search_overseas_hotels, search_tours


class TravelAgent(BaseAgent):
    AI_TYPE = "travel"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_hotels",
            "description": "楽天トラベルでホテルを検索する（国内旅行のみ）",
            "parameters": {"type": "object", "properties": {
                "keyword":   {"type": "string",  "description": "都市名・ホテル名・エリア名"},
                "checkin":   {"type": "string",  "description": "チェックイン日 YYYY-MM-DD"},
                "checkout":  {"type": "string",  "description": "チェックアウト日 YYYY-MM-DD"},
                "adult_num": {"type": "integer", "description": "大人の人数（デフォルト2）"},
            }, "required": ["keyword"]},
        }},
        {"type": "function", "function": {
            "name": "search_flights",
            "description": "Google Flights Data APIで航空券を検索して便名・出発時刻・到着時刻・料金を取得する。国内・海外を問わず飛行機移動が含まれるプランで必ず呼ぶ。",
            "parameters": {"type": "object", "properties": {
                "origin":         {"type": "string",  "description": "出発地の都市名（例: 東京, 大阪）"},
                "destination":    {"type": "string",  "description": "目的地の都市名（例: 福岡, 沖縄）"},
                "departure_date": {"type": "string",  "description": "出発日 YYYY-MM-DD"},
                "adults":         {"type": "integer", "description": "大人の人数（デフォルト2）"},
            }, "required": ["origin", "destination", "departure_date"]},
        }},
        {"type": "function", "function": {
            "name": "search_overseas_hotels",
            "description": "Booking.com経由で海外（国外）のホテルを検索する。海外旅行でホテルが必要な場合に呼ぶ。",
            "parameters": {"type": "object", "properties": {
                "city":      {"type": "string",  "description": "目的地の都市名（日本語可。例: バンコク, パリ, ハワイ, ソウル）"},
                "checkin":   {"type": "string",  "description": "チェックイン日 YYYY-MM-DD"},
                "checkout":  {"type": "string",  "description": "チェックアウト日 YYYY-MM-DD"},
                "adult_num": {"type": "integer", "description": "大人の人数（デフォルト2）"},
            }, "required": ["city"]},
        }},
        {"type": "function", "function": {
            "name": "search_tours",
            "description": (
                "Google検索で目的地のツアー・体験・アクティビティを検索して上位件数を返す。"
                "「ツアーある？」「体験したい」「何かアクティビティを」「日帰りで楽しめるものは？」など"
                "ツアーやアクティビティの提案が求められるときに呼ぶ。"
                "keywordには茶道・ダイビング・日帰りなど具体的な体験内容を入れると精度が上がる。"
            ),
            "parameters": {"type": "object", "properties": {
                "destination": {"type": "string",  "description": "目的地（例: 京都, 沖縄, バリ島）"},
                "keyword":     {"type": "string",  "description": "体験・活動の種類（例: 茶道体験, ダイビング, 日帰りバスツアー）省略可"},
                "max_results": {"type": "integer", "description": "返却件数（デフォルト5）"},
            }, "required": ["destination"]},
        }},
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "周辺の観光スポット・飲食店を検索する",
            "parameters": {"type": "object", "properties": {
                "lat":     {"type": "number"},
                "lng":     {"type": "number"},
                "keyword": {"type": "string"},
                "radius":  {"type": "number"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {
        "search_hotels":  lambda a: search_hotels(**a),
        "search_flights": lambda a: search_flights(**a),
        "search_overseas_hotels": lambda a: search_overseas_hotels(**a),
        "search_tours":   lambda a: search_tours(**a),
        "search_nearby":  lambda a: search_nearby(**a),
    }