"""
楽天API ツール
- 楽天トラベル: ホテル検索
- 楽天市場: 商品検索
"""
import os, requests


def _app_id() -> str:
    """毎回環境変数から取得（Railway追加後も再デプロイ不要）"""
    return os.getenv("RAKUTEN_APP_ID", "")


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
    """楽天市場で商品を検索する"""
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
        }
        if min_price: params["minPrice"] = min_price
        if max_price: params["maxPrice"] = max_price

        r = requests.get(
            "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706",
            params=params,
            timeout=10
        )
        data = r.json()
        print(f"[Rakuten] keyword={keyword} count={data.get('count',0)} error={data.get('error','none')}")
        if data.get("error"):
            return {"available": False, "reason": data.get("error_description", data["error"])}

        items = []
        for item in data.get("Items", []):
            i = item.get("Item", item)  # APIバージョンによりItem直下のこともある
            # 画像URL（smallは不鮮明なのでmediumを使う）
            img_urls = i.get("mediumImageUrls") or i.get("smallImageUrls") or []
            img = img_urls[0].get("imageUrl", "") if img_urls and isinstance(img_urls[0], dict) else ""
            items.append({
                "name":      i.get("itemName", "")[:80],
                "price":     i.get("itemPrice"),
                "shop":      i.get("shopName"),
                "shop_url":  i.get("shopUrl"),
                "url":       i.get("itemUrl"),
                "image":     img,
                "review":    i.get("reviewAverage"),
                "review_count": i.get("reviewCount"),
                "catchcopy": (i.get("catchcopy") or "")[:60],
                "point":     i.get("pointRate"),
            })
        return {"available": True, "type": "products", "items": items, "total": data.get("count", 0)}
    except Exception as e:
        print(f"[Rakuten] エラー: {e}")
        return {"available": False, "reason": str(e)}
