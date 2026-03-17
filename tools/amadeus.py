"""
航空券検索 - RapidAPI / Google Flights Data API
- ホスト: google-flights-data.p.rapidapi.com
- 環境変数: RAPIDAPI_KEY
- エンドポイント: GET /flights/search
  パラメータ: departure_id, arrival_id, outbound_date, adults, currency
"""
import os, requests

# 日本の主要空港 IATAコード
CITY_TO_IATA = {
    "東京": "TYO", "羽田": "HND", "成田": "NRT",
    "大阪": "OSA", "伊丹": "ITM", "関西": "KIX",
    "名古屋": "NGO", "中部": "NGO",
    "札幌": "CTS", "新千歳": "CTS",
    "福岡": "FUK",
    "沖縄": "OKA", "那覇": "OKA",
    "金沢": "KMQ", "小松": "KMQ",
    "広島": "HIJ",
    "仙台": "SDJ",
    "鹿児島": "KOJ",
    "長崎": "NGS",
    "熊本": "KMJ",
    "高松": "TAK",
    "松山": "MYJ",
    "旭川": "AKJ",
    "函館": "HKD",
    "秋田": "AXT",
    "青森": "AOJ",
    "石垣": "ISG",
    "宮古": "MMY",
    "大分": "OIT",
    "宮崎": "KMI",
}

CARRIER_NAMES = {
    "NH": "ANA", "JL": "JAL", "MM": "Peach",
    "GK": "ジェットスター", "7G": "スターフライヤー",
    "BC": "スカイマーク", "HD": "エア・ドゥ",
    "NU": "JTA",
}


def _city_to_iata(city: str) -> str | None:
    for key, code in CITY_TO_IATA.items():
        if key in city:
            return code
    if len(city) == 3 and city.isalpha():
        return city.upper()
    return None


def _parse_duration(minutes: int) -> str:
    """分 → 'X時間Y分' 形式"""
    h, m = divmod(minutes, 60)
    return f"{h}時間{m}分" if m else f"{h}時間"


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 2,
    max_results: int = 5,
) -> dict:
    """
    Google Flights Data API でフライトを検索する

    Returns:
        {
          "available": bool,
          "type": "flights",
          "flights": [
            {
              "airline": "ANA",
              "flight_number": "NH683",
              "departure_time": "08:00",
              "arrival_time":   "09:30",
              "duration":       "1時間30分",
              "price":          18500,
              "direct":         True,
              "origin_iata":    "HND",
              "dest_iata":      "OKA",
              "book_url":       "https://www.google.com/travel/flights?..."
            }
          ],
          ...
        }
    """
    api_key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not api_key:
        return {"available": False, "reason": "RAPIDAPI_KEY が未設定です"}

    origin_iata = _city_to_iata(origin)
    dest_iata   = _city_to_iata(destination)

    if not origin_iata:
        return {"available": False, "reason": f"出発地 '{origin}' のIATAコードが不明です"}
    if not dest_iata:
        return {"available": False, "reason": f"目的地 '{destination}' のIATAコードが不明です"}

    print(f"[GoogleFlights] {origin_iata}→{dest_iata} on {departure_date} adults={adults}")

    # Google Flights Data API のエンドポイント
    url = "https://google-flights-data.p.rapidapi.com/flights/search"
    params = {
        "departure_id":  origin_iata,
        "arrival_id":    dest_iata,
        "outbound_date": departure_date,
        "adults":        adults,
        "currency":      "JPY",
        "hl":            "ja",
        "gl":            "jp",
        "type":          "2",   # 1=往復, 2=片道
    }
    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": "google-flights-data.p.rapidapi.com",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"[GoogleFlights] status={r.status_code}")

        if r.status_code == 404:
            # エンドポイントが違う場合 → flights/booking-details 以外を試す
            # フォールバック: /flights/search-one-way を試す
            url2 = "https://google-flights-data.p.rapidapi.com/flights/search-one-way"
            r = requests.get(url2, headers=headers, params=params, timeout=15)
            print(f"[GoogleFlights] fallback status={r.status_code}")

        if r.status_code != 200:
            return {"available": False, "reason": f"HTTP {r.status_code}"}

        data = r.json()

        # レスポンス構造の解析（best_flights / other_flights）
        all_flights = []
        for key in ("best_flights", "other_flights"):
            for group in data.get(key, []):
                segs = group.get("flights", [])
                if not segs:
                    continue
                first_seg = segs[0]
                last_seg  = segs[-1]

                dep_airport = first_seg.get("departure_airport", {})
                arr_airport = last_seg.get("arrival_airport",   {})
                dep_time = dep_airport.get("time", "")[-5:]   # "YYYY-MM-DD HH:MM" → "HH:MM"
                arr_time = arr_airport.get("time", "")[-5:]
                airline  = first_seg.get("airline", "")
                flight_no = first_seg.get("flight_number", "")
                duration_min = group.get("total_duration", 0)
                price    = group.get("price", 0)
                is_direct = len(segs) == 1

                # スカイスキャナー予約URLを生成（Google Flightsは直接予約リンクなし）
                date_fmt = departure_date.replace("-", "")
                book_url = f"https://www.skyscanner.jp/routes/{origin_iata}/{dest_iata}/{date_fmt}/"

                # ANAなど日本語短縮名に変換
                for code, name in CARRIER_NAMES.items():
                    if code in flight_no:
                        airline = name
                        break

                all_flights.append({
                    "airline":        airline,
                    "flight_number":  flight_no,
                    "departure_time": dep_time,
                    "arrival_time":   arr_time,
                    "duration":       _parse_duration(duration_min),
                    "price":          int(price),
                    "direct":         is_direct,
                    "origin_iata":    origin_iata,
                    "dest_iata":      dest_iata,
                    "book_url":       book_url,
                })

        if not all_flights:
            return {"available": False, "reason": f"{origin_iata}→{dest_iata} の便が見つかりませんでした"}

        # 価格でソート
        all_flights.sort(key=lambda x: x["price"])
        all_flights = all_flights[:max_results]

        cheapest = all_flights[0]["price"]
        print(f"[GoogleFlights] {len(all_flights)}件 最安値: ¥{cheapest:,}")

        return {
            "available":      True,
            "type":           "flights",
            "flights":        all_flights,
            "origin_iata":    origin_iata,
            "dest_iata":      dest_iata,
            "departure_date": departure_date,
        }

    except Exception as e:
        print(f"[GoogleFlights] エラー: {e}")
        return {"available": False, "reason": str(e)}