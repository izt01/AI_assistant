"""
家電・インテリア提案AI
"""
from .base import BaseAgent
from tools import search_products


class ApplianceAgent(BaseAgent):
    AI_TYPE = "appliance"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": "家電・インテリアを楽天市場で検索する",
            "parameters": {"type": "object", "properties": {
                "keyword": {"type": "string"},
            }, "required": ["keyword"]},
        }},
    ]
    TOOL_MAP = {"search_products": lambda a: search_products(**a)}
