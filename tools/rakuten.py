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
# 楽天トラベルの地区コードマップ (middleClassCode, smallClassCode)
# smallClassCode は地区コードAPIで確認した正確な値を使用
_AREA_CODE_MAP = {
    # ── 北海道・東北 ──
    "札幌":("hokkaido","sapporo"),   "北海道":("hokkaido","sapporo"),
    "函館":("hokkaido","hakodate"),  "旭川":("hokkaido","asahikawa"),
    "富良野":("hokkaido","furano"),  "知床":("hokkaido","abashiri"),
    "仙台":("miyagi","sendai"),      "宮城":("miyagi","sendai"),
    "松島":("miyagi","matsushima"),  "青森":("aomori","aomori"),
    "弘前":("aomori","hirosaki"),     "八戸":("aomori","hachinohe"),
    "盛岡":("iwate","morioka"),       "岩手":("iwate","morioka"),
    "平泉":("iwate","hiraizumi"),     "花巻":("iwate","hanamaki"),
    "秋田":("akita","akita"),        "山形":("yamagata","yamagata"),
    "蔵王":("yamagata","zao"),       "福島":("fukushima","fukushima"),
    # ── 関東 ──
    "東京":("tokyo","tokyo"),        "新宿":("tokyo","tokyo"),
    "浅草":("tokyo","tokyo"),        "銀座":("tokyo","tokyo"),
    "横浜":("kanagawa","yokohama"),  "神奈川":("kanagawa","yokohama"),
    "箱根":("kanagawa","hakone"),    "鎌倉":("kanagawa","kamakura"),
    "日光":("tochigi","nikko"),      "栃木":("tochigi","nikko"),
    "草津":("gunma","kusatsu"),      "伊香保":("gunma","ikaho"),
    # ── 中部・北陸 ──
    "軽井沢":("nagano","karuizawa"), "長野":("nagano","nagano"),
    "松本":("nagano","matsumoto"),   "白馬":("nagano","hakuba"),
    "上高地":("nagano","kamikochi"), "新潟":("niigata","niigata"),
    "湯沢":("niigata","yuzawa"),     "金沢":("ishikawa","kanazawa"),
    "石川":("ishikawa","kanazawa"),  "富山":("toyama","toyama"),
    "山梨":("yamanashi","kofu"),     "富士":("shizuoka","fujinomiya"),
    "熱海":("shizuoka","atami"),     "伊豆":("shizuoka","izu"),
    "静岡":("shizuoka","shizuoka"),
    # ── 東海 ──
    "名古屋":("aichi","nagoya"),     "愛知":("aichi","nagoya"),
    "岐阜":("gifu","gifu"),          "白川郷":("gifu","shirakawago"),
    "伊勢":("mie","ise"),            "三重":("mie","ise"),
    # ── 近畿 ──
    "京都":("kyoto","shi"),          "嵐山":("kyoto","shi"),     # ★ shi = 京都市
    "祇園":("kyoto","shi"),          "清水":("kyoto","shi"),
    "大阪":("osaka","osaka"),        "難波":("osaka","osaka"),
    "神戸":("hyogo","kobe"),         "兵庫":("hyogo","kobe"),
    "有馬":("hyogo","arima"),        "城崎":("hyogo","kinosaki"),
    "奈良":("nara","nara"),          "吉野":("nara","yoshino"),
    "滋賀":("shiga","ootsu"),        "琵琶湖":("shiga","ootsu"),
    "和歌山":("wakayama","wakayama"),"白浜":("wakayama","shirahama"),
    # ── 中国・四国 ──
    "広島":("hiroshima","hiroshima"),"宮島":("hiroshima","miyajima"),
    "岡山":("okayama","okayama"),    "倉敷":("okayama","kurashiki"),
    "松江":("shimane","matsue"),     "出雲":("shimane","izumo"),
    "鳥取":("tottori","tottori"),    "山口":("yamaguchi","yamaguchi"),
    "松山":("ehime","matsuyama"),    "道後":("ehime","matsuyama"),
    "高知":("kochi","kochi"),        "香川":("kagawa","takamatsu"),
    "徳島":("tokushima","tokushima"),
    # ── 九州・沖縄 ──
    "福岡":("fukuoka","fukuoka"),    "博多":("fukuoka","fukuoka"),
    "長崎":("nagasaki","nagasaki"),  "佐世保":("nagasaki","sasebo"),
    "熊本":("kumamoto","kumamoto"),  "阿蘇":("kumamoto","aso"),
    "別府":("oita","beppu"),         "湯布院":("oita","yufuin"),
    "大分":("oita","beppu"),         "宮崎":("miyazaki","miyazaki"),
    "鹿児島":("kagoshima","kagoshima"),"指宿":("kagoshima","ibusuki"),
    "沖縄":("okinawa","naha"),       "那覇":("okinawa","naha"),
    "石垣":("okinawa","ishigaki"),   "宮古":("okinawa","miyakojima"),
}

# 都道府県名 → middleClassCode のフォールバックマップ
# エリアコードマップにない地名でも都道府県レベルで検索できるようにする
_PREF_FALLBACK = {
    "北海道": ("hokkaido","sapporo"),
    "青森県": ("aomori","aomori"),   "青森": ("aomori","aomori"),
    "岩手県": ("iwate","morioka"),   "岩手": ("iwate","morioka"),
    "宮城県": ("miyagi","sendai"),   "宮城": ("miyagi","sendai"),
    "秋田県": ("akita","akita"),     "秋田": ("akita","akita"),
    "山形県": ("yamagata","yamagata"),"山形": ("yamagata","yamagata"),
    "福島県": ("fukushima","fukushima"),"福島": ("fukushima","fukushima"),
    "茨城県": ("ibaraki","mito"),    "茨城": ("ibaraki","mito"),
    "栃木県": ("tochigi","nikko"),   "群馬県": ("gunma","kusatsu"),
    "埼玉県": ("saitama","omiya"),   "千葉県": ("chiba","chiba"),
    "東京都": ("tokyo","tokyo"),     "神奈川県": ("kanagawa","yokohama"),
    "新潟県": ("niigata","niigata"), "富山県": ("toyama","toyama"),
    "石川県": ("ishikawa","kanazawa"),"福井県": ("fukui","fukui"),
    "山梨県": ("yamanashi","kofu"),  "長野県": ("nagano","nagano"),
    "岐阜県": ("gifu","gifu"),       "静岡県": ("shizuoka","shizuoka"),
    "愛知県": ("aichi","nagoya"),    "三重県": ("mie","ise"),
    "滋賀県": ("shiga","ootsu"),     "京都府": ("kyoto","shi"),
    "大阪府": ("osaka","osaka"),     "兵庫県": ("hyogo","kobe"),
    "奈良県": ("nara","nara"),       "和歌山県": ("wakayama","wakayama"),
    "鳥取県": ("tottori","tottori"), "島根県": ("shimane","matsue"),
    "岡山県": ("okayama","okayama"), "広島県": ("hiroshima","hiroshima"),
    "山口県": ("yamaguchi","yamaguchi"),"徳島県": ("tokushima","tokushima"),
    "香川県": ("kagawa","takamatsu"),"愛媛県": ("ehime","matsuyama"),
    "高知県": ("kochi","kochi"),     "福岡県": ("fukuoka","fukuoka"),
    "佐賀県": ("saga","saga"),       "長崎県": ("nagasaki","nagasaki"),
    "熊本県": ("kumamoto","kumamoto"),"大分県": ("oita","beppu"),
    "宮崎県": ("miyazaki","miyazaki"),"鹿児島県": ("kagoshima","kagoshima"),
    "沖縄県": ("okinawa","naha"),
}

def _keyword_to_area_codes(keyword: str):
    """
    都市名・地名から (middleClassCode, smallClassCode) を返す。
    1. 完全一致 → 2. 部分一致 → 3. 都道府県名フォールバック → None
    """
    # 1. 完全一致
    if keyword in _AREA_CODE_MAP:
        return _AREA_CODE_MAP[keyword]
    # 2. keywordにエリア名が含まれる（例: "金沢駅周辺" → "金沢"）
    for name, codes in _AREA_CODE_MAP.items():
        if name in keyword:
            return codes
    # 3. 都道府県名フォールバック（例: "弘前市" → 青森県の主要エリアで検索）
    for pref, codes in _PREF_FALLBACK.items():
        if pref in keyword:
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
        # 一部都市(京都=shi, 東京=tokyo, 大阪=osaka等)はdetailClassCodeが必要
        # 指定しない場合は400エラーになる → "A"（主要市街地）を使用
        NEED_DETAIL = {"shi", "tokyo", "osaka", "nagoya", "yokohama",
                       "sendai", "sapporo", "fukuoka", "hiroshima"}
        params = {
            **_auth_params(),
            "largeClassCode":  "japan",
            "middleClassCode": middle_code,
            "smallClassCode":  small_code,
            "hits":            max_results,
            "responseType":    "small",
            "format":          "json",
        }
        if small_code in NEED_DETAIL:
            params["detailClassCode"] = "A"  # 主要市街地エリア
        if checkin:   params["checkinDate"]  = checkin
        if checkout:  params["checkoutDate"] = checkout
        if adult_num: params["adultNum"]     = adult_num

        # 429レート制限対策: 最大3回リトライ
        import time as _time
        for _attempt in range(3):
            r = requests.get(
                # ★ 正しいエンドポイント: engine/api（travel/api は誤り）
                "https://openapi.rakuten.co.jp/engine/api/Travel/SimpleHotelSearch/20170426",
                params=params,
                headers=_auth_headers(),
                timeout=8
            )
            detail = params.get("detailClassCode", "-")
            print(f"[Rakuten Hotels] keyword={keyword} middle={middle_code} small={small_code} detail={detail} status={r.status_code}")
            if r.status_code != 429:
                break
            print(f"[Rakuten Hotels] 429 Rate Limit, retry {_attempt+1}/3...")
            _time.sleep(1.5)

        data = r.json()
        if data.get("error"):
            print(f"[Rakuten Hotels] error={data.get('error')} desc={data.get('error_description')}")
            return {"available": False, "reason": f"{data.get('error')}: {data.get('error_description')}"}

        hotels = []
        for h in data.get("hotels", []):
            # 楽天トラベルAPIのレスポンス構造:
            # hotels[n] = {"hotel": [{"hotelBasicInfo": {...}}, {"roomInfo": [...]}]}
            try:
                if isinstance(h, dict) and "hotel" in h:
                    i = h["hotel"][0]["hotelBasicInfo"]   # 通常パターン
                elif isinstance(h, list):
                    i = h[0].get("hotelBasicInfo", {})    # 旧パターン
                else:
                    i = h.get("hotelBasicInfo", {})
            except (KeyError, IndexError, TypeError):
                continue
            if not i:
                continue
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
        # ── 0件のとき都道府県レベルで再検索 ──────────────────────
        if not hotels and small_code != "":
            # まず都道府県の主要都市（smallCode なし）で再検索
            fallback_params = {**params}
            fallback_params.pop("smallClassCode", None)
            fallback_params.pop("detailClassCode", None)
            fallback_params["hits"] = max_results

            for _attempt2 in range(2):
                r2 = requests.get(
                    "https://openapi.rakuten.co.jp/engine/api/Travel/SimpleHotelSearch/20170426",
                    params=fallback_params,
                    headers=_auth_headers(),
                    timeout=8,
                )
                print(f"[Rakuten Hotels] fallback middle={middle_code} only → status={r2.status_code}")
                if r2.status_code != 429:
                    break
                import time as _time2; _time2.sleep(1.5)

            data2 = r2.json()
            if not data2.get("error"):
                for h in data2.get("hotels", []):
                    try:
                        if isinstance(h, dict) and "hotel" in h:
                            i = h["hotel"][0]["hotelBasicInfo"]
                        elif isinstance(h, list):
                            i = h[0].get("hotelBasicInfo", {})
                        else:
                            i = h.get("hotelBasicInfo", {})
                    except (KeyError, IndexError, TypeError):
                        continue
                    if not i:
                        continue
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
                        "fallback_area": True,  # 代替エリアで見つかったフラグ
                    })
                if hotels:
                    print(f"[Rakuten Hotels] fallback で {len(hotels)} 件取得")

        result = {"available": True, "type": "hotels", "hotels": hotels, "adult_num": adult_num}
        if not hotels:
            result["reason"] = f"楽天トラベルで'{keyword}'周辺のホテルが見つかりませんでした"
            result["searched_area"] = middle_code
        elif any(h.get("fallback_area") for h in hotels):
            result["fallback_notice"] = f"'{keyword}'エリアが見つからなかったため、{middle_code}の近隣エリアで検索しました"
        return result
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