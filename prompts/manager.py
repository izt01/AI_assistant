"""
プロンプトマネージャー
YAMLファイルからプロンプトを読み込み、テンプレートを展開する。

使い方:
  from prompts import get_prompt

  # defaultパックのrecipeプロンプトを取得
  system_prompt = get_prompt("recipe")

  # 別パックを使う場合（PROMPT_PACK環境変数 or 引数で指定）
  system_prompt = get_prompt("recipe", pack="my_custom_pack")

パックの切り替え:
  - 環境変数: PROMPT_PACK=my_custom_pack
  - prompts/packs/my_custom_pack/ フォルダを作り、変更したいYAMLだけ置く
  - 存在しないYAMLはdefaultにフォールバック
"""

import os
import yaml
from jinja2 import Template

PACKS_DIR   = os.path.join(os.path.dirname(__file__), "packs")
DEFAULT_PACK = "default"


def _load_yaml(ai_name: str, pack: str) -> dict:
    """指定パック → defaultの順でYAMLを探して読み込む"""
    for p in [pack, DEFAULT_PACK]:
        path = os.path.join(PACKS_DIR, p, f"{ai_name}.yaml")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"プロンプトが見つかりません: {ai_name} (pack={pack})")


def get_prompt(ai_name: str, pack: str = None) -> str:
    """
    AIの名前を渡すとシステムプロンプト文字列を返す。

    Args:
        ai_name: "recipe" / "travel" / "shopping" / "diy" / "appliance" / "health" / "router"
        pack:    使用するパック名（省略時は環境変数PROMPT_PACKまたはdefault）
    """
    if pack is None:
        pack = os.getenv("PROMPT_PACK", DEFAULT_PACK)

    data = _load_yaml(ai_name, pack)
    template_str = data.get("system", "")

    # Jinja2でテンプレート展開
    rendered = Template(template_str).render(
        **data,
        enumerate=enumerate,  # Jinja2でenumerateを使えるようにする
    )
    return rendered.strip()


def get_router_specialists(pack: str = None) -> dict:
    """ルーターの専門AI一覧を返す"""
    if pack is None:
        pack = os.getenv("PROMPT_PACK", DEFAULT_PACK)
    data = _load_yaml("router", pack)
    return data.get("specialists", {})


def list_packs() -> list:
    """利用可能なパック一覧を返す"""
    if not os.path.exists(PACKS_DIR):
        return []
    return [d for d in os.listdir(PACKS_DIR)
            if os.path.isdir(os.path.join(PACKS_DIR, d))]
