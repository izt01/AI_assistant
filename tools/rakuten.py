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


def search_hotels(keyword: str, checkin: str = "", checkout: str = "", adult_num: int = 2, max_results: int = 4) -> dict:
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
        if adult_num:  params["adultNum"]     = adult_num

        r = requests.get(
            "https://app.rakuten.co.jp/services/api/Travel/SimpleHotelSearch/20170426",
            params=params, timeout=5
        )
        hotels = []
        for h in r.json().get("hotels", []):
            i = h[0]["hotelBasicInfo"]
            
            hotel_no = i.get("hotelNo", "")
            checkin_fmt = checkin.replace("-", "") if checkin else ""
            deep_url = f"https://hotel.travel.rakuten.co.jp/hotelinfo/plan/{hotel_no}"
            if checkin_fmt:
                deep_url += f"?f_hizuke={checkin_fmt}&f_otona_su={adult_num}&f_heya_su=1&f_syu=ch"
            hotels.append({
                "name":         i.get("hotelName"),
                "price":        i.get("hotelMinCharge"),
                "area":         i.get("address1", "") + i.get("address2", ""),
                "access":       i.get("access"),
                "review":       i.get("reviewAverage"),
                "review_count": i.get("reviewCount"),
                "url":          i.get("hotelInformationUrl"),
                "image":        i.get("hotelImageUrl"),
                "hotel_no":  hotel_no,
                "deep_url":  deep_url,
                "checkin":   checkin,
                "checkout":  checkout,
                "adult_num": adult_num,
            })
        return {"available": True, "type": "hotels", "hotels": hotels, "adult_num": adult_num}
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
        err  = data.get("error", "")
        desc = data.get("error_description", "")
        app_id_masked = app_id[:8] + "..." if len(app_id) > 8 else app_id
        print(f"[Rakuten] keyword={keyword} status={r.status_code} count={data.get('count',0)} error={err or 'none'} desc={desc} appId={app_id_masked} len={len(app_id)}")
        print(f"[Rakuten] full_response={str(data)[:300]}")
        if err:
            return {"available": False, "reason": f"{err}: {desc}"}

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
