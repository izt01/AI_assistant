"""
楽天API ツール
- 楽天トラベル: ホテル検索
- 楽天市場: 商品検索
"""
import os, requests


def _app_id() -> str:
    """毎回環境変数から取得（Railway追加後も再デプロイ不要）"""
    val = os.getenv("RAKUTEN_APP_ID", "").strip()
    return val


def search_hotels(keyword: str, checkin: str = "", checkout: str = "", max_results: int = 4) -> dict:
    """楽天トラベルでホテルを検索する"""
    app_id = _app_id()
    if not app_id:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    try:
        params = {
            "applicationId": app_id,
            "keyword":        keyword,
            "hits":           max_results,
            "responseType":   "small",
            "format":         "json",
        }
        if checkin:  params["checkinDate"]  = checkin
        if checkout: params["checkoutDate"] = checkout

        r = requests.get(
            "https://app.rakuten.co.jp/services/api/Travel/SimpleHotelSearch/20170426",
            params=params, timeout=5
        )
        hotels = []
        for h in r.json().get("hotels", []):
            i = h[0]["hotelBasicInfo"]
            hotels.append({
                "name":         i.get("hotelName"),
                "price":        i.get("hotelMinCharge"),
                "area":         i.get("address1", "") + i.get("address2", ""),
                "access":       i.get("access"),
                "review":       i.get("reviewAverage"),
                "review_count": i.get("reviewCount"),
                "url":          i.get("hotelInformationUrl"),
                "image":        i.get("hotelImageUrl"),
            })
        return {"available": True, "type": "hotels", "hotels": hotels}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def search_products(keyword: str, max_results: int = 6, min_price: int = None, max_price: int = None) -> dict:
    """楽天市場で商品を検索する（バックエンド経由・CORS問題なし）"""
    app_id = _app_id()
    if not app_id:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    try:
        params = {
            "applicationId": app_id,
            "keyword":       keyword,
            "hits":          max_results,
            "sort":          "standard",
            "availability":  1,
            "imageFlag":     1,
            "formatVersion": 2,   # ← フラット構造で返ってくる（item["Item"]ラップなし）
        }
        if min_price: params["minPrice"] = min_price
        if max_price: params["maxPrice"] = max_price

        r = requests.get(
            "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706",
            params=params,
            timeout=10
        )
        data = r.json()
        err  = data.get("error", "")
        desc = data.get("error_description", "")
        app_id_masked = app_id[:8] + "..." if len(app_id) > 8 else app_id
        print(f"[Rakuten] keyword={keyword} status={r.status_code} count={data.get('count',0)} error={err or 'none'} appId={app_id_masked}")

        if err:
            return {"available": False, "reason": f"{err}: {desc}"}

        items = []
        # formatVersion=2 ではItems直下がフラット（Item{}ラップなし）
        for item in data.get("Items", []):
            # 画像URL（mediumを優先、なければsmall）
            img_urls = item.get("mediumImageUrls") or item.get("smallImageUrls") or []
            if img_urls and isinstance(img_urls[0], dict):
                img = img_urls[0].get("imageUrl", "")
            elif img_urls and isinstance(img_urls[0], str):
                img = img_urls[0]
            else:
                img = ""

            items.append({
                "name":         (item.get("itemName") or "")[:80],
                "price":        item.get("itemPrice"),
                "shop":         item.get("shopName"),
                "shop_url":     item.get("shopUrl"),
                "url":          item.get("itemUrl"),
                "image":        img,
                "review":       item.get("reviewAverage"),
                "review_count": item.get("reviewCount"),
                "catchcopy":    (item.get("catchcopy") or "")[:60],
                "point":        item.get("pointRate"),
            })

        return {"available": True, "type": "products", "items": items, "total": data.get("count", 0)}

    except Exception as e:
        print(f"[Rakuten] エラー: {e}")
        return {"available": False, "reason": str(e)}
