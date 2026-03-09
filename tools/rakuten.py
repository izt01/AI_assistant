"""
楽天API ツール
- 楽天トラベル: ホテル検索
- 楽天市場: 商品検索
"""
import os, requests

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")


def search_hotels(keyword: str, checkin: str = "", checkout: str = "", max_results: int = 4) -> dict:
    """楽天トラベルでホテルを検索する"""
    if not RAKUTEN_APP_ID:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    try:
        params = {
            "applicationId": RAKUTEN_APP_ID,
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


def search_products(keyword: str, max_results: int = 5) -> dict:
    """楽天市場で商品を価格順で検索する"""
    if not RAKUTEN_APP_ID:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    try:
        r = requests.get(
            "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706",
            params={
                "applicationId": RAKUTEN_APP_ID,
                "keyword":       keyword,
                "hits":          max_results,
                "sort":          "+itemPrice",
                "format":        "json",
            },
            timeout=5
        )
        items = []
        for item in r.json().get("Items", []):
            i = item["Item"]
            items.append({
                "name":      i.get("itemName"),
                "price":     i.get("itemPrice"),
                "shop":      i.get("shopName"),
                "url":       i.get("itemUrl"),
                "image":     (i.get("mediumImageUrls") or [{}])[0].get("imageUrl", ""),
                "review":    i.get("reviewAverage"),
                "catchcopy": i.get("catchcopy", ""),
            })
        return {"available": True, "type": "products", "items": items}
    except Exception as e:
        return {"available": False, "reason": str(e)}
