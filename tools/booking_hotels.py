"""
海外ホテル検索 - RapidAPI / Booking.com API
- ホスト: booking-com.p.rapidapi.com
- 環境変数: RAPIDAPI_KEY（航空券検索と共用）
- フロー:
    1. /v1/hotels/locations で都市の dest_id を取得
    2. /v1/hotels/search で dest_id → ホテル一覧を取得
- ホテルが取得できなかった場合は Booking.com / Agoda の検索URLをフォールバックとして返す
"""
import os, requests, time

_BASE = "https://booking-com.p.rapidapi.com"

# 主要都市の日本語名 → 英語都市名マッピング
_CITY_JA_TO_EN = {
    # アジア
    "バンコク": "Bangkok",         "タイ": "Bangkok",
    "パリ": "Paris",               "フランス": "Paris",
    "ロンドン": "London",          "イギリス": "London",
    "ニューヨーク": "New York",    "NY": "New York",
    "ロサンゼルス": "Los Angeles", "LA": "Los Angeles",
    "ハワイ": "Honolulu",          "ホノルル": "Honolulu",
    "シンガポール": "Singapore",
    "バリ": "Bali",                "バリ島": "Bali",
    "ソウル": "Seoul",             "韓国": "Seoul",
    "台湾": "Taipei",              "台北": "Taipei",
    "香港": "Hong Kong",
    "上海": "Shanghai",            "北京": "Beijing",
    "ベトナム": "Ho Chi Minh City","ホーチミン": "Ho Chi Minh City",
    "ハノイ": "Hanoi",
    "バリ": "Bali",
    "クアラルンプール": "Kuala Lumpur", "マレーシア": "Kuala Lumpur",
    "ジャカルタ": "Jakarta",       "インドネシア": "Jakarta",
    "マニラ": "Manila",            "フィリピン": "Manila",
    "セブ": "Cebu",
    "プーケット": "Phuket",        "チェンマイ": "Chiang Mai",
    "デリー": "Delhi",             "インド": "Delhi",
    "ムンバイ": "Mumbai",
    "ドバイ": "Dubai",             "UAE": "Dubai",
    "イスタンブール": "Istanbul",  "トルコ": "Istanbul",
    # ヨーロッパ
    "ローマ": "Rome",              "イタリア": "Rome",
    "ミラノ": "Milan",
    "バルセロナ": "Barcelona",     "スペイン": "Barcelona",
    "マドリード": "Madrid",
    "アムステルダム": "Amsterdam", "オランダ": "Amsterdam",
    "ベルリン": "Berlin",          "ドイツ": "Berlin",
    "ミュンヘン": "Munich",        "フランクフルト": "Frankfurt",
    "プラハ": "Prague",            "ウィーン": "Vienna",
    "チューリッヒ": "Zurich",      "ジュネーブ": "Geneva",
    "ブリュッセル": "Brussels",
    "コペンハーゲン": "Copenhagen","ストックホルム": "Stockholm",
    "ヘルシンキ": "Helsinki",      "オスロ": "Oslo",
    "リスボン": "Lisbon",          "ポルトガル": "Lisbon",
    "アテネ": "Athens",            "ギリシャ": "Athens",
    "サントリーニ": "Santorini",
    "クロアチア": "Dubrovnik",     "ドゥブロヴニク": "Dubrovnik",
    # アメリカ
    "ラスベガス": "Las Vegas",     "サンフランシスコ": "San Francisco",
    "シカゴ": "Chicago",           "マイアミ": "Miami",
    "バンクーバー": "Vancouver",   "カナダ": "Vancouver",
    "トロント": "Toronto",
    # オセアニア
    "シドニー": "Sydney",          "オーストラリア": "Sydney",
    "メルボルン": "Melbourne",
    "オークランド": "Auckland",    "ニュージーランド": "Auckland",
    # その他
    "モルディブ": "Malé",
    "グアム": "Tumon",             "サイパン": "Garapan",
    "ニューカレドニア": "Nouméa",
    "フィジー": "Nadi",
}


def _get_api_key() -> str:
    return os.getenv("RAPIDAPI_KEY", "").strip()


def _headers() -> dict:
    return {
        "X-RapidAPI-Key":  _get_api_key(),
        "X-RapidAPI-Host": "booking-com.p.rapidapi.com",
    }


def _city_en(city_ja: str) -> str:
    """日本語都市名を英語に変換。マップにない場合はそのまま返す（ローマ字等の場合）"""
    # 完全一致
    if city_ja in _CITY_JA_TO_EN:
        return _CITY_JA_TO_EN[city_ja]
    # 部分一致
    for ja, en in _CITY_JA_TO_EN.items():
        if ja in city_ja:
            return en
    return city_ja  # マップになければそのまま（英語で渡された場合など）


def _fallback_urls(city_en: str, checkin: str, checkout: str, adults: int) -> dict:
    """APIが失敗したときの Booking.com / Agoda 検索URLを生成"""
    from urllib.parse import quote
    q = quote(city_en)
    ci = checkin or ""
    co = checkout or ""
    booking_url = (
        f"https://www.booking.com/searchresults.ja.html"
        f"?ss={q}&checkin={ci}&checkout={co}&group_adults={adults}&no_rooms=1&lang=ja"
    )
    agoda_url = (
        f"https://www.agoda.com/ja-jp/search"
        f"?city={q}&checkIn={ci}&checkOut={co}&adults={adults}&rooms=1&ckuid=ja"
    )
    expedia_url = (
        f"https://www.expedia.co.jp/Hotel-Search"
        f"?destination={q}&startDate={ci}&endDate={co}&adults={adults}"
    )
    return {
        "booking_search_url": booking_url,
        "agoda_search_url":   agoda_url,
        "expedia_search_url": expedia_url,
    }


def search_overseas_hotels(
    city: str,
    checkin: str = "",
    checkout: str = "",
    adult_num: int = 2,
    max_results: int = 4,
) -> dict:
    """
    Booking.com API（RapidAPI経由）で海外ホテルを検索する。

    Returns:
        {
          "available": bool,
          "type": "overseas_hotels",
          "city_en": "Bangkok",
          "hotels": [
            {
              "name": "...",
              "price": 8500,            # 円換算（大体）
              "currency": "USD",
              "stars": 4,
              "review": 8.5,
              "review_count": 1234,
              "address": "...",
              "image": "https://...",
              "url": "https://www.booking.com/hotel/...",
              "checkin": "2025-06-01",
              "checkout": "2025-06-05",
              "adult_num": 2,
            }
          ],
          # APIが失敗した場合の代替URL
          "fallback_urls": { "booking_search_url": "...", "agoda_search_url": "...", "expedia_search_url": "..." }
        }
    """
    api_key = _get_api_key()
    if not api_key:
        return {
            "available": False,
            "reason": "RAPIDAPI_KEY が未設定です",
            **_fallback_urls(_city_en(city), checkin, checkout, adult_num),
        }

    city_en = _city_en(city)
    print(f"[OverseasHotels] city={city} → city_en={city_en}")

    try:
        # ── STEP 1: dest_id を取得 ──────────────────────────────────
        r1 = requests.get(
            f"{_BASE}/v1/hotels/locations",
            headers=_headers(),
            params={
                "name":   city_en,
                "locale": "ja",
            },
            timeout=10,
        )
        print(f"[OverseasHotels] locations status={r1.status_code}")

        if r1.status_code == 401:
            return {
                "available": False,
                "type": "overseas_hotels",
                "reason": "RAPIDAPI_KEY が無効です（Booking.com APIの購読が必要）",
                "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
            }

        if r1.status_code != 200:
            return {
                "available": False,
                "type": "overseas_hotels",
                "reason": f"Booking.com API エラー: HTTP {r1.status_code}",
                "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
            }

        locations = r1.json()
        if not locations:
            return {
                "available": True,
                "type": "overseas_hotels",
                "city_en": city_en,
                "hotels": [],
                "reason": f"'{city_en}' のロケーションが見つかりませんでした",
                "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
            }

        # city_type が "city" のものを優先
        dest = next(
            (loc for loc in locations if loc.get("dest_type") == "city"),
            locations[0],
        )
        dest_id   = dest.get("dest_id") or dest.get("city_ufi")
        dest_type = dest.get("dest_type", "city")
        print(f"[OverseasHotels] dest_id={dest_id} dest_type={dest_type}")

        # ── STEP 2: ホテル一覧を検索 ────────────────────────────────
        time.sleep(0.3)  # レート制限対策

        search_params = {
            "dest_id":      dest_id,
            "dest_type":    dest_type,
            "order_by":     "popularity",
            "adults_count": adult_num,
            "room_number":  1,
            "units":        "metric",
            "locale":       "ja",
            "currency_code":"JPY",
            "filter_by_currency": "JPY",
            "page_number":  0,
        }
        if checkin:  search_params["checkin_date"]  = checkin
        if checkout: search_params["checkout_date"] = checkout

        r2 = requests.get(
            f"{_BASE}/v1/hotels/search",
            headers=_headers(),
            params=search_params,
            timeout=12,
        )
        print(f"[OverseasHotels] search status={r2.status_code}")

        if r2.status_code != 200:
            return {
                "available": False,
                "type": "overseas_hotels",
                "reason": f"ホテル検索 API エラー: HTTP {r2.status_code}",
                "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
            }

        data = r2.json()
        raw_hotels = data.get("result", [])
        if not raw_hotels:
            return {
                "available": True,
                "type": "overseas_hotels",
                "city_en": city_en,
                "hotels": [],
                "reason": f"'{city_en}' でのホテルが見つかりませんでした",
                "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
            }

        hotels = []
        for h in raw_hotels[:max_results]:
            # 価格（min_total_price が円建てで入ることが多い）
            price = None
            price_raw = h.get("min_total_price") or h.get("price_breakdown", {}).get("gross_price")
            if price_raw is not None:
                try:
                    price = int(float(price_raw))
                except Exception:
                    pass

            hotels.append({
                "name":         h.get("hotel_name") or h.get("name", ""),
                "price":        price,
                "currency":     h.get("currency_code", "JPY"),
                "stars":        int(h.get("class", 0) or 0),
                "review":       h.get("review_score"),
                "review_label": h.get("review_score_word"),
                "review_count": h.get("review_nr"),
                "address":      h.get("address") or h.get("city", ""),
                "district":     h.get("district") or h.get("city", ""),
                "image":        h.get("max_photo_url") or h.get("main_photo_url"),
                "url":          h.get("url") or f"https://www.booking.com/hotel/{h.get('hotel_id', '')}.ja.html",
                "checkin":      checkin,
                "checkout":     checkout,
                "adult_num":    adult_num,
            })

        print(f"[OverseasHotels] {len(hotels)} 件取得")
        return {
            "available":    True,
            "type":         "overseas_hotels",
            "city":         city,
            "city_en":      city_en,
            "hotels":       hotels,
            "total":        data.get("count_properties", len(hotels)),
            "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
        }

    except Exception as e:
        print(f"[OverseasHotels] エラー: {e}")
        return {
            "available":    False,
            "type":         "overseas_hotels",
            "reason":       str(e),
            "fallback_urls": _fallback_urls(city_en, checkin, checkout, adult_num),
        }
