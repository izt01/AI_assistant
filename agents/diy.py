"""
DIY提案AI
"""
from .base import BaseAgent
from tools import search_products


class DiyAgent(BaseAgent):
    AI_TYPE = "diy"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": "DIYに必要な材料・工具を楽天市場で検索する",
            "parameters": {"type": "object", "properties": {
                "keyword": {"type": "string"},
            }, "required": ["keyword"]},
        }},
    ]
    TOOL_MAP = {"search_products": lambda a: search_products(**a)}
