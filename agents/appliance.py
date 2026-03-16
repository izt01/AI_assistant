"""
家電・インテリア提案AI
- min_price / max_price パラメータを追加（価格条件をキーワードに混ぜさせない）
- keyword サニタイザーで価格文字列を自動除去
"""
import re
from .base import BaseAgent
from tools import search_products


def _sanitize_keyword(keyword: str) -> str:
    """
    keywordから価格・予算に関する文字列を自動除去する。
    AIが誤って価格をキーワードに混ぜても0件にならないようにする。
    例: "冷蔵庫 予算30万 省エネ" → "冷蔵庫 省エネ"
    """
    # 「予算〇〇」「〇〇円以内/以下/まで/前後」「〇〇万円」などを除去
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
    # 余分なスペースを整理
    result = re.sub(r'\s+', ' ', result).strip()
    if result != keyword:
        print(f"[Appliance] keyword sanitized: '{keyword}' → '{result}'")
    return result or keyword  # 全部消えたら元に戻す


def _search_with_sanitize(args: dict) -> dict:
    """keywordをサニタイズしてからsearch_productsを呼ぶ"""
    kw = args.get("keyword", "")
    args["keyword"] = _sanitize_keyword(kw)
    result = search_products(**args)

    # 0件かつキーワードが長い場合、短くして再試行
    if result.get("available") and result.get("total", 0) == 0 and len(args["keyword"].split()) > 3:
        short_kw = " ".join(args["keyword"].split()[:3])
        print(f"[Appliance] 0件のため短縮再試行: '{args['keyword']}' → '{short_kw}'")
        args2 = {**args, "keyword": short_kw}
        result2 = search_products(**args2)
        if result2.get("total", 0) > 0:
            return result2

    return result


class ApplianceAgent(BaseAgent):
    AI_TYPE = "appliance"

    TOOLS = [
        {"type": "function", "function": {
            "name": "search_products",
            "description": (
                "家電・インテリアを楽天市場で検索する。"
                "ユーザーが商品を探している・買い替えたい・購入を検討しているときは必ず呼ぶ。"
                "【重要】keyword には商品名・メーカー・スペックのみを入れること。"
                "価格・予算（例: '30万円以内'）は keyword に含めず max_price パラメータで渡すこと。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "楽天市場の検索キーワード。商品名・型番・特徴のみ。"
                            "価格・予算・値段は絶対に含めないこと。"
                            "良い例: '冷蔵庫 大容量 500L 省エネ' / '4K テレビ 55インチ'"
                            "悪い例: '冷蔵庫 30万円以内' / '省エネ家電 予算30万'"
                        )
                    },
                    "max_results": {"type": "integer", "description": "取得件数（デフォルト6）"},
                    "min_price":   {"type": "integer", "description": "最低価格（円）。価格条件がある場合はここで指定"},
                    "max_price":   {"type": "integer", "description": "最高価格（円）。予算上限がある場合はここで指定。例: 30万円なら300000"},
                },
                "required": ["keyword"],
            },
        }},
    ]

    TOOL_MAP = {
        "search_products": _search_with_sanitize,
    }