"""
料理提案AI
"""
from .base import BaseAgent
from tools import search_products, search_nearby


class RecipeAgent(BaseAgent):
    AI_TYPE = "recipe"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_nearby",
            "description": "近くのスーパー・食料品店を検索する",
            "parameters": {"type": "object", "properties": {
                "lat":     {"type": "number"},
                "lng":     {"type": "number"},
                "keyword": {"type": "string"},
                "radius":  {"type": "number"},
            }, "required": ["lat", "lng", "keyword"]},
        }},
    ]
    TOOL_MAP = {"search_nearby": lambda a: search_nearby(**a)}
