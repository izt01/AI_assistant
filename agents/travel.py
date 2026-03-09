"""
旅行プラン提案AI
"""
from .base import BaseAgent
from tools import search_hotels, search_nearby


class TravelAgent(BaseAgent):
    AI_TYPE = "travel"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_hotels",
            "description": "楽天トラベルでホテルを検索する",
            "parameters": {"type": "object", "properties": {
                "keyword":  {"type": "string"},
                "checkin":  {"type": "string"},
                "checkout": {"type": "string"},
            }, "required": ["keyword"]},
        }},
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "周辺の観光スポット・飲食店を検索する",
            "parameters": {"type": "object", "properties": {
                "lat": {"type": "number"}, "lng": {"type": "number"},
                "keyword": {"type": "string"}, "radius": {"type": "number"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {
        "search_hotels":  lambda a: search_hotels(**a),
        "search_nearby":  lambda a: search_nearby(**a),
    }
