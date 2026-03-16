"""
楽天API ツール（2026年新API対応版）
- 2026年2月10日より新エンドポイントへの移行が必要
- 旧: app.rakuten.co.jp  → 新: openapi.rakuten.co.jp
- 認証: applicationId のみ → applicationId + accessKey の両方が必要
- 移行期限: 2026年5月13日（以降は旧APIが完全停止）

必要な環境変数:
  RAKUTEN_APP_ID    : アプリケーションID（UUID形式）
  RAKUTEN_ACCESS_KEY: アクセスキー（楽天アプリ管理画面から取得）
"""
import os, requests


def _app_id() -> str:
    return os.getenv("RAKUTEN_APP_ID", "").strip()

def _access_key() -> str:
    return os.getenv("RAKUTEN_ACCESS_KEY", "").strip()

def _auth_params() -> dict:
    """新APIに必要な認証パラメータを返す"""
    return {
        "applicationId": _app_id(),
        "accessKey":     _access_key(),
    }

def _auth_headers(app_url: str = "") -> dict:
    """新APIに必要なReferer/Originヘッダーを返す（登録済みのアプリURLを使う）"""
    url = app_url or os.getenv("RAKUTEN_APP_URL", "https://aiassistant-production-264e.up.railway.app")
    return {
        "Referer": url + "/",
        "Origin":  url,
    }


# 楽天トラベルのエリアコードマップ
# (middleClassCode, smallClassCode) のタプルで返す
# smallClassCode は都道府県の主要エリアを代表値として設定
_AREA_CODE_MAP = {
    # キーワード: (middleClassCode, smallClassCode)
    "札幌":("hokkaido","sapporo"),  "北海道":("hokkaido","sapporo"),
    "函館":("hokkaido","hakodate"), "旭川":("hokkaido","asahikawa"),
    "仙台":("miyagi","sendai"),     "宮城":("miyagi","sendai"),
    "青森":("aomori","aomori"),     "岩手":("iwate","morioka"),
    "秋田":("akita","akita"),       "山形":("yamagata","yamagata"),
    "福島":("fukushima","fukushima"),
    "東京":("tokyo","tokyo"),       "新宿":("tokyo","tokyo"),
    "渋谷":("tokyo","tokyo"),       "浅草":("tokyo","tokyo"),
    "横浜":("kanagawa","yokohama"), "神奈川":("kanagawa","yokohama"),
    "箱根":("kanagawa","hakone"),   "鎌倉":("kanagawa","kamakura"),
    "埼玉":("saitama","saitama"),   "千葉":("chiba","chiba"),
    "茨城":("ibaraki","mito"),      "栃木":("tochigi","nikko"),
    "日光":("tochigi","nikko"),     "群馬":("gunma","kusatsu"),
    "草津":("gunma","kusatsu"),     "軽井沢":("nagano","karuizawa"),
    "長野":("nagano","nagano"),     "松本":("nagano","matsumoto"),
    "新潟":("niigata","niigata"),   "富山":("toyama","toyama"),
    "金沢":("ishikawa","kanazawa"), "石川":("ishikawa","kanazawa"),
    "福井":("fukui","fukui"),       "山梨":("yamanashi","kofu"),
    "富士":("shizuoka","fujinomiya"),"静岡":("shizuoka","shizuoka"),
    "熱海":("shizuoka","atami"),    "伊豆":("shizuoka","izu"),
    "名古屋":("aichi","nagoya"),    "愛知":("aichi","nagoya"),
    "岐阜":("gifu","gifu"),         "三重":("mie","ise"),
    "伊勢":("mie","ise"),           "滋賀":("shiga","biwako"),
    "琵琶湖":("shiga","biwako"),
    "京都":("kyoto","kyoto"),       "嵐山":("kyoto","kyoto"),
    "大阪":("osaka","osaka"),       "難波":("osaka","osaka"),
    "兵庫":("hyogo","kobe"),        "神戸":("hyogo","kobe"),
    "有馬":("hyogo","arima"),       "奈良":("nara","nara"),
    "和歌山":("wakayama","wakayama"),
    "広島":("hiroshima","hiroshima"),"宮島":("hiroshima","miyajima"),
    "岡山":("okayama","okayama"),   "鳥取":("tottori","tottori"),
    "島根":("shimane","matsue"),    "出雲":("shimane","izumo"),
    "山口":("yamaguchi","yamaguchi"),
    "徳島":("tokushima","tokushima"),"香川":("kagawa","takamatsu"),
    "愛媛":("ehime","matsuyama"),   "高知":("kochi","kochi"),
    "福岡":("fukuoka","fukuoka"),   "博多":("fukuoka","fukuoka"),
    "佐賀":("saga","saga"),         "長崎":("nagasaki","nagasaki"),
    "熊本":("kumamoto","kumamoto"), "大分":("oita","beppu"),
    "別府":("oita","beppu"),        "湯布院":("oita","yufuin"),
    "宮崎":("miyazaki","miyazaki"), "鹿児島":("kagoshima","kagoshima"),
    "沖縄":("okinawa","naha"),      "那覇":("okinawa","naha"),
    "石垣":("okinawa","ishigaki"),
}

def _keyword_to_area_codes(keyword: str) -> tuple | None:
    """都市名・地名から (middleClassCode, smallClassCode) を返す。見つからなければNone。"""
    for name, codes in _AREA_CODE_MAP.items():
        if name in keyword:
            return codes
    return None


def search_hotels(keyword: str, checkin: str = "", checkout: str = "", adult_num: int = 2, max_results: int = 4) -> dict:
    """楽天トラベルでホテルを検索する（新API対応・エリアコード変換付き）"""
    app_id = _app_id()
    if not app_id:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    if not _access_key():
        return {"available": False, "reason": "RAKUTEN_ACCESS_KEY が未設定です（2026年新API対応に必要）"}
    try:
        # keywordから (middleClassCode, smallClassCode) に変換
        area_codes = _keyword_to_area_codes(keyword)
        if not area_codes:
            print(f"[Rakuten Hotels] 対応エリアコードなし: keyword={keyword}")
            return {"available": True, "type": "hotels", "hotels": [], "adult_num": adult_num,
                    "reason": f"楽天トラベルで'{keyword}'に対応するエリアが見つかりませんでした"}

        middle_code, small_code = area_codes
        params = {
            **_auth_params(),
            "largeClassCode":  "japan",
            "middleClassCode": middle_code,
            "smallClassCode":  small_code,
            "hits":            max_results,
            "responseType":    "small",
            "format":          "json",
        }
        if checkin:   params["checkinDate"]  = checkin
        if checkout:  params["checkoutDate"] = checkout
        if adult_num: params["adultNum"]     = adult_num

        r = requests.get(
            # ★ 正しいエンドポイント: engine/api（travel/api は誤り）
            "https://openapi.rakuten.co.jp/engine/api/Travel/SimpleHotelSearch/20170426",
            params=params,
            headers=_auth_headers(),
            timeout=8
        )
        print(f"[Rakuten Hotels] keyword={keyword} middle={middle_code} small={small_code} status={r.status_code}")

        data = r.json()
        if data.get("error"):
            print(f"[Rakuten Hotels] error={data.get('error')} desc={data.get('error_description')}")
            return {"available": False, "reason": f"{data.get('error')}: {data.get('error_description')}"}

        hotels = []
        for h in data.get("hotels", []):
            # 新APIはhotel[0]ではなくhotel直下の場合もある
            info = h[0] if isinstance(h, list) else h
            i = info.get("hotelBasicInfo", info)
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
                "hotel_no":     hotel_no,
                "deep_url":     deep_url,
                "checkin":      checkin,
                "checkout":     checkout,
                "adult_num":    adult_num,
            })
        return {"available": True, "type": "hotels", "hotels": hotels, "adult_num": adult_num}
    except Exception as e:
        print(f"[Rakuten Hotels] エラー: {e}")
        return {"available": False, "reason": str(e)}


def search_products(keyword: str, max_results: int = 6, min_price: int = None, max_price: int = None) -> dict:
    """楽天市場で商品を検索する（新API対応）"""
    app_id = _app_id()
    if not app_id:
        return {"available": False, "reason": "RAKUTEN_APP_ID が未設定です"}
    if not _access_key():
        return {"available": False, "reason": "RAKUTEN_ACCESS_KEY が未設定です（2026年新API対応に必要）"}
    try:
        params = {
            **_auth_params(),
            "keyword":       keyword,
            "hits":          max_results,
            "sort":          "standard",
            "availability":  1,
            "imageFlag":     1,
            "formatVersion": 2,
        }
        if min_price: params["minPrice"] = min_price
        if max_price: params["maxPrice"] = max_price

        r = requests.get(
            # ★ 新エンドポイント（旧: app.rakuten.co.jp/services/api/IchibaItem/Search/20170706）
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601",
            params=params,
            headers=_auth_headers(),
            timeout=10
        )
        data = r.json()
        err  = data.get("error", "")
        desc = data.get("error_description", "")
        app_id_masked = app_id[:8] + "..." if len(app_id) > 8 else app_id
        print(f"[Rakuten] keyword={keyword} status={r.status_code} count={data.get('count',0)} error={err or 'none'} desc={desc} appId={app_id_masked}")
        if err:
            return {"available": False, "reason": f"{err}: {desc}"}

        items = []
        for item in data.get("Items", []):
            i = item.get("Item", item)
            img_urls = i.get("mediumImageUrls") or i.get("smallImageUrls") or []
            img = img_urls[0].get("imageUrl", "") if img_urls and isinstance(img_urls[0], dict) else ""
            items.append({
                "name":         i.get("itemName", "")[:80],
                "price":        i.get("itemPrice"),
                "shop":         i.get("shopName"),
                "shop_url":     i.get("shopUrl"),
                "url":          i.get("itemUrl"),
                "image":        img,
                "review":       i.get("reviewAverage"),
                "review_count": i.get("reviewCount"),
                "catchcopy":    (i.get("catchcopy") or "")[:60],
                "point":        i.get("pointRate"),
            })
        return {"available": True, "type": "products", "items": items, "total": data.get("count", 0)}
    except Exception as e:
        print(f"[Rakuten] エラー: {e}")
        return {"available": False, "reason": str(e)}