"""
フォールバックモードエンジン
OpenAI APIが使えない場合（残高ゼロ・メンテナンス時）に
YAMLシナリオに基づいてシステム的に返答する。
"""
import os
import re
import yaml
import json
from tools import search_hotels, search_nearby, search_products


# シナリオキャッシュ
_SCENARIO_CACHE: dict = {}

# AI種別 → YAMLファイル名のマッピング
AI_SCENARIO_MAP = {
    "travel":    "travel",
    "gourmet":   "gourmet",
    "recipe":    "recipe",
    "cooking":   "recipe",
    "shopping":  "shopping",
    "health":    "health",
    "diy":       "diy",
    "appliance": "appliance",
    "home":      "appliance",
    "general":   "travel",  # 総合はとりあえず旅行
}


def _load_scenario(ai_type: str) -> dict:
    """AIタイプに対応するシナリオを読み込む"""
    scenario_name = AI_SCENARIO_MAP.get(ai_type, "travel")
    if scenario_name in _SCENARIO_CACHE:
        return _SCENARIO_CACHE[scenario_name]

    path = os.path.join(
        os.path.dirname(__file__), "..",
        "prompts", "fallback", f"{scenario_name}.yaml"
    )
    try:
        with open(path, encoding="utf-8") as f:
            scenario = yaml.safe_load(f)
        _SCENARIO_CACHE[scenario_name] = scenario
        return scenario
    except Exception as e:
        print(f"[Fallback] シナリオ読み込みエラー: {e}")
        return {
            "name": "AI（メンテナンス中）",
            "greeting": "現在メンテナンス中です。しばらくお待ちください。",
            "steps": []
        }


def _get_step(scenario: dict, step_id: str) -> dict | None:
    """シナリオからステップIDに対応するステップを取得"""
    for step in scenario.get("steps", []):
        if step["id"] == step_id:
            return step
    return None


def _format_message(template: str, context: dict) -> str:
    """テンプレート文字列にコンテキスト変数を埋め込む"""
    for key, val in context.items():
        template = template.replace(f"{{{key}}}", str(val))
    return template


def _extract_number(text: str, default: int = 2) -> int:
    """テキストから数字を抽出（人数・泊数など）"""
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else default


def _run_search_action(action: str, context: dict) -> dict:
    """
    検索アクションを実行してツール結果を返す
    """
    if action == "search_hotels":
        destination = context.get("destination", "")
        adult_num = _extract_number(context.get("adult_num", "2"))
        return search_hotels(keyword=destination, adult_num=adult_num, max_results=4)

    elif action == "search_nearby":
        area  = context.get("area", "")
        genre = context.get("genre", "レストラン")
        return search_nearby(query=f"{area} {genre}", radius=500)

    elif action == "search_products":
        item = context.get("item", "")
        return search_products(keyword=item, max_results=6)

    return {}


def run_fallback(ai_type: str, messages: list, session_state: dict) -> dict:
    """
    フォールバックモードのメイン処理。
    session_state: セッションごとのフォールバック進行状態
      {
        "step": "destination",   # 現在のステップID
        "context": {}            # 収集済みの情報
      }
    
    Returns:
      {
        "reply": str,
        "extra": dict,           # ホテルカード等のツール結果
        "suggestions": list,
        "session_state": dict    # 更新後のセッション状態
      }
    """
    scenario = _load_scenario(ai_type)
    steps    = scenario.get("steps", [])

    # 初回（セッション開始）
    if not session_state or not session_state.get("step"):
        session_state = {"step": steps[0]["id"] if steps else "done", "context": {}}
        return {
            "reply":         scenario.get("greeting", "ご相談をお聞きします。"),
            "extra":         {},
            "suggestions":   [],
            "session_state": session_state,
        }

    current_step_id = session_state.get("step", "done")
    context         = session_state.get("context", {})

    # ユーザーの最新メッセージを取得
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    # 現在のステップでユーザーの返答を収集
    current_step = _get_step(scenario, current_step_id)
    if current_step and current_step.get("extract") and user_msg:
        context[current_step["extract"]] = user_msg

    # 次のステップへ
    next_step_id = current_step.get("next", "done") if current_step else "done"
    next_step    = _get_step(scenario, next_step_id)

    if not next_step:
        # シナリオ終了
        return {
            "reply":         "ご利用ありがとうございました。サービス復旧後にまたご相談ください！",
            "extra":         {},
            "suggestions":   [],
            "session_state": {"step": steps[0]["id"] if steps else "done", "context": {}},
        }

    # 検索アクションがある場合
    extra = {}
    reply = _format_message(next_step.get("message", ""), context)

    if next_step.get("action"):
        tool_result = _run_search_action(next_step["action"], context)
        hotels   = tool_result.get("hotels", [])
        places   = tool_result.get("places", [])
        items    = tool_result.get("items", [])

        if hotels:
            extra["_hotels"] = tool_result
            reply = _format_message(next_step.get("result_message", reply), context)
        elif places:
            extra["_places"] = places
            reply = _format_message(next_step.get("result_message", reply), context)
        elif items:
            extra["_products"] = tool_result
            reply = _format_message(next_step.get("result_message", reply), context)
        else:
            reply = _format_message(next_step.get("fallback_message", reply), context)

        # 検索後は次のステップへ
        after_search_id = next_step.get("next", "done")
        after_step      = _get_step(scenario, after_search_id)
        if after_step:
            reply += "\n\n" + _format_message(after_step.get("message", ""), context)
            next_step_id = after_search_id

    session_state = {"step": next_step_id, "context": context}

    return {
        "reply":         reply,
        "extra":         extra,
        "suggestions":   [],
        "session_state": session_state,
    }
