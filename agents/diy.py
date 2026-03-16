"""
DIY提案AI
- min_price / max_price パラメータを追加（価格条件をキーワードに混ぜさせない）
- keyword サニタイザーで価格文字列を自動除去
"""
import re
from .base import BaseAgent
from tools import search_products


def _sanitize_keyword(keyword: str) -> str:
    """keywordから価格・予算に関する文字列を自動除去する"""
    patterns = [
        r'予算\s*[\d,]+\s*万?円?',
        r'[\d,]+\s*万円(以内|以下|まで|前後|程度|くらい|ぐらい)?',
        r'[\d,]+\s*円(以内|以下|まで|前後|程度|くらい|ぐらい)',
        r'(安い|高い|コスパ|お手頃|リーズナブル|格安)',
        r'予算\s*[\d,]+',
        r'\d+万(以内|以下|まで|前後|程度)?',
    ]
    result = keyword
    for p in patterns:
        result = re.sub(p, '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    if result != keyword:
        print(f"[DIY] keyword sanitized: '{keyword}' → '{result}'")
    return result or keyword


def _search_with_sanitize(args: dict) -> dict:
    """keywordをサニタイズしてからsearch_productsを呼ぶ"""
    kw = args.get("keyword", "")
    args["keyword"] = _sanitize_keyword(kw)
    result = search_products(**args)

    # 0件かつキーワードが長い場合、短くして再試行
    if result.get("available") and result.get("total", 0) == 0 and len(args["keyword"].split()) > 3:
        short_kw = " ".join(args["keyword"].split()[:3])
        print(f"[DIY] 0件のため短縮再試行: '{args['keyword']}' → '{short_kw}'")
        args2 = {**args, "keyword": short_kw}
        result2 = search_products(**args2)
        if result2.get("total", 0) > 0:
            return result2

    return result


class DiyAgent(BaseAgent):
    AI_TYPE = "diy"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": (
                "DIYに必要な材料・工具を楽天市場で検索する。"
                "必要な材料・工具が確定したら必ず呼ぶ。"
                "【重要】keyword には商品名・材質・規格のみを入れること。"
                "価格・予算は keyword に含めず max_price パラメータで渡すこと。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "楽天市場の検索キーワード。商品名・材質・規格のみ。"
                            "価格・予算は絶対に含めないこと。"
                            "良い例: '木材 2x4 SPF 1820mm' / '電動ドリル 充電式 初心者'"
                            "悪い例: '木材 5000円以内' / '工具 予算1万円'"
                        )
                    },
                    "max_results": {"type": "integer", "description": "取得件数（デフォルト6）"},
                    "min_price":   {"type": "integer", "description": "最低価格（円）"},
                    "max_price":   {"type": "integer", "description": "最高価格（円）。予算上限がある場合はここで指定"},
                },
                "required": ["keyword"],
            },
        }},
    ]

    TOOL_MAP = {
        "search_products": _search_with_sanitize,
    }