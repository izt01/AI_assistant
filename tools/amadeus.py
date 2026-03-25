"""
航空券検索 - RapidAPI / Google Flights Data API
- ホスト: google-flights-data.p.rapidapi.com
- 環境変数: RAPIDAPI_KEY
- エンドポイント: GET /flights/search
  パラメータ: departure_id, arrival_id, outbound_date, adults, currency
"""
import os, requests

# 日本 + 主要海外空港 IATAコード（国内・海外両対応）
CITY_TO_IATA = {
    # ── 日本 ──────────────────────────────────────────
    "東京": "TYO", "羽田": "HND", "成田": "NRT",
    "大阪": "OSA", "伊丹": "ITM", "関西": "KIX",
    "名古屋": "NGO", "中部": "NGO",
    "札幌": "CTS", "新千歳": "CTS",
    "福岡": "FUK",
    "沖縄": "OKA", "那覇": "OKA",
    "金沢": "KMQ", "小松": "KMQ",
    "広島": "HIJ", "仙台": "SDJ",
    "鹿児島": "KOJ", "長崎": "NGS",
    "熊本": "KMJ", "高松": "TAK",
    "松山": "MYJ", "旭川": "AKJ",
    "函館": "HKD", "秋田": "AXT",
    "青森": "AOJ", "石垣": "ISG",
    "宮古": "MMY", "大分": "OIT",
    "宮崎": "KMI",
    # ── ヨーロッパ ────────────────────────────────────
    "ロンドン": "LHR", "ヒースロー": "LHR", "ガトウィック": "LGW",
    "パリ": "CDG", "シャルルドゴール": "CDG", "オルリー": "ORY",
    "ローマ": "FCO", "フィウミチーノ": "FCO",
    "ミラノ": "MXP", "マルペンサ": "MXP",
    "フィレンツェ": "FLR", "ベネチア": "VCE", "ナポリ": "NAP",
    "バルセロナ": "BCN", "マドリード": "MAD",
    "アムステルダム": "AMS", "スキポール": "AMS",
    "フランクフルト": "FRA", "ミュンヘン": "MUC",
    "ベルリン": "BER", "デュッセルドルフ": "DUS",
    "プラハ": "PRG", "ウィーン": "VIE",
    "チューリッヒ": "ZRH", "ジュネーブ": "GVA",
    "ブリュッセル": "BRU",
    "コペンハーゲン": "CPH", "ストックホルム": "ARN",
    "ヘルシンキ": "HEL", "オスロ": "OSL",
    "リスボン": "LIS", "マドリード": "MAD",
    "アテネ": "ATH", "サントリーニ": "JTR",
    "イスタンブール": "IST", "ドバイ": "DXB",
    "アブダビ": "AUH", "ドーハ": "DOH",
    # ── アジア ────────────────────────────────────────
    "ソウル": "ICN", "仁川": "ICN", "金浦": "GMP",
    "台北": "TPE", "桃園": "TPE", "松山": "TSA",
    "香港": "HKG",
    "上海": "PVG", "浦東": "PVG", "虹橋": "SHA",
    "北京": "PEK", "首都": "PEK",
    "広州": "CAN", "深圳": "SZX", "成都": "CTU",
    "バンコク": "BKK", "スワンナプーム": "BKK", "ドンムアン": "DMK",
    "シンガポール": "SIN", "チャンギ": "SIN",
    "クアラルンプール": "KUL", "マレーシア": "KUL",
    "バリ": "DPS", "デンパサール": "DPS",
    "ジャカルタ": "CGK",
    "マニラ": "MNL", "セブ": "CEB",
    "ホーチミン": "SGN", "ハノイ": "HAN",
    "プーケット": "HKT", "チェンマイ": "CNX",
    "デリー": "DEL", "ムンバイ": "BOM",
    "コロンボ": "CMB", "カトマンズ": "KTM",
    # ── アメリカ・カナダ ────────────────────────────
    "ニューヨーク": "JFK", "ケネディ": "JFK", "ラガーディア": "LGA", "ニューアーク": "EWR",
    "ロサンゼルス": "LAX", "LA": "LAX",
    "ハワイ": "HNL", "ホノルル": "HNL",
    "サンフランシスコ": "SFO", "SF": "SFO",
    "シカゴ": "ORD", "オヘア": "ORD",
    "ラスベガス": "LAS",
    "マイアミ": "MIA", "シアトル": "SEA",
    "ボストン": "BOS", "ワシントン": "IAD",
    "バンクーバー": "YVR", "トロント": "YYZ",
    # ── オセアニア・太平洋 ────────────────────────────
    "シドニー": "SYD", "メルボルン": "MEL",
    "ブリスベン": "BNE", "パース": "PER",
    "オークランド": "AKL",
    "グアム": "GUM", "サイパン": "SPN",
    "フィジー": "NAN", "タヒチ": "PPT",
    # ── アフリカ ─────────────────────────────────────
    "カイロ": "CAI", "ケープタウン": "CPT", "ナイロビ": "NBO",
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
            # API失敗でもスカイスキャナー検索URLをフォールバックとして返す
            sky_url = f"https://www.skyscanner.jp/routes/{origin_iata}/{dest_iata}/"
            return {
                "available": False,
                "reason": f"HTTP {r.status_code}",
                "type": "flights",
                "fallback_url": sky_url,
                "origin_iata": origin_iata,
                "dest_iata": dest_iata,
            }

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

# ══════════════════════════════════════════════════════════════
#  ツアー・体験検索 - RapidAPI Google Search
#  既存の RAPIDAPI_KEY をそのまま使用
#  RapidAPIで "Google Search" API（neoscrap-net/google-search72）を
#  追加購読するだけで動作（無料プランあり）
#  ホスト: google-search72.p.rapidapi.com
# ══════════════════════════════════════════════════════════════

import re as _re

# ── 国内目的地リスト（これ以外は海外とみなす）──────────────────
DOMESTIC_DESTINATIONS = {
    "東京", "大阪", "京都", "沖縄", "北海道", "札幌", "福岡", "広島",
    "名古屋", "奈良", "神戸", "横浜", "仙台", "金沢", "長崎", "鹿児島",
    "熊本", "高松", "松山", "旭川", "函館", "秋田", "青森", "石垣",
    "宮古", "那覇", "箱根", "日光", "鎌倉", "軽井沢", "富士山", "富士",
    "草津", "別府", "湯布院", "由布院", "白川郷", "高山", "飛騨",
    "伊勢", "高野山", "吉野", "宮島", "尾道", "倉敷", "萩", "津和野",
    "屋久島", "種子島", "五島列島", "壱岐", "対馬",
}

def _is_overseas(destination: str) -> bool:
    """目的地が海外かどうか判定する"""
    return not any(d in destination for d in DOMESTIC_DESTINATIONS)

def search_tours(
    destination: str,
    keyword: str = "",
    max_results: int = 5,
    # 旅行AIからstart_date/end_dateが渡されても無視（互換性のため受け取る）
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    RapidAPI Google Search でツアー・体験を検索して上位件数を返す。

    既存の RAPIDAPI_KEY を使用。
    RapidAPIダッシュボードで "google-search72" を追加購読すること（無料枠あり）。

    Args:
        destination: 目的地（例: 京都, 沖縄, バリ）
        keyword:     絞り込みキーワード（例: 茶道体験, ダイビング, 日帰り）
        max_results: 返却件数（デフォルト5）

    Returns:
        {
          "available": True,
          "type":      "tours",
          "destination": "京都",
          "keyword":   "茶道体験",
          "tours": [
            {
              "title":       "京都 茶道体験ツアー｜じゃらん",
              "description": "京都の老舗茶室で本格的な茶道体験...",
              "url":         "https://www.jalan.net/...",
              "site":        "jalan.net",
              "price_hint":  "3,000円〜",  # スニペットから抽出（任意）
            }, ...
          ]
        }
    """
    api_key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not api_key:
        return {"available": False, "reason": "RAPIDAPI_KEY が未設定です"}

    # 国内 or 海外を自動判定してクエリを最適化
    overseas = _is_overseas(destination)
    if overseas:
        # 海外：日本発のツアーを検索。「海外ツアー」「現地ツアー」を加える
        extra = keyword or "現地ツアー 体験 予約"
        kw_parts = [destination, extra, "海外ツアー 日本語"]
    else:
        # 国内：通常検索
        extra = keyword or "ツアー 体験 予約"
        kw_parts = [destination, extra]
    query = " ".join(p for p in kw_parts if p)
    print(f"[TourSearch] {'海外' if overseas else '国内'}ツアー検索")

    print(f"[TourSearch] Google検索: '{query}'")

    try:
        r = requests.get(
            "https://google-search72.p.rapidapi.com/search",
            headers={
                "X-RapidAPI-Key":  api_key,
                "X-RapidAPI-Host": "google-search72.p.rapidapi.com",
            },
            params={
                "q":   query,
                "gl":  "jp",   # 日本の検索結果
                "hl":  "ja",   # 日本語
                "num": max_results * 2,  # 多めに取って絞り込む
            },
            timeout=12,
        )
        print(f"[TourSearch] status={r.status_code}")

        if r.status_code == 403:
            return {
                "available": False,
                "reason": (
                    "google-search72 API の購読が必要です。"
                    "RapidAPIダッシュボードで 'google-search72' を検索して追加購読してください（無料枠あり）。"
                ),
            }
        if r.status_code != 200:
            return {"available": False, "reason": f"Google Search API エラー: HTTP {r.status_code}"}

        data  = r.json()
        items = data.get("items", [])   # google-search72 のレスポンス形式

        # items がない場合は他のキーを試す（APIにより異なる）
        if not items:
            items = data.get("organic", data.get("results", []))

        if not items:
            return {"available": False, "reason": f"{destination} のツアーが見つかりませんでした"}

        tours = []
        for item in items:
            title   = item.get("title", "")
            url     = item.get("link",  item.get("url", ""))
            snippet = item.get("snippet", item.get("description", ""))

            if not title or not url:
                continue

            # 価格っぽい文字列をスニペットから抽出
            price_hint = _extract_price(snippet)

            # ドメイン名を取得してサイト名として表示
            site = _extract_domain(url)

            tours.append({
                "title":       title,
                "description": snippet,
                "url":         url,
                "site":        site,
                "price_hint":  price_hint,
                "image_url":   item.get("thumbnail", item.get("image", "")),
            })

            if len(tours) >= max_results:
                break

        if not tours:
            return {"available": False, "reason": f"{destination} のツアーが見つかりませんでした"}

        print(f"[TourSearch] {len(tours)}件取得")
        return {
            "available":   True,
            "type":        "tours",
            "destination": destination,
            "keyword":     keyword,
            "tours":       tours,
            "search_query": query,
        }

    except Exception as e:
        print(f"[TourSearch] エラー: {e}")
        return {"available": False, "reason": str(e)}


def _extract_price(text: str) -> str:
    """スニペットから価格っぽい文字列を抽出する"""
    if not text:
        return ""
    # ¥1,000 / 1,000円 / 1000円 などにマッチ
    m = _re.search(r'[¥￥]?\s*[\d,]+\s*円|[\d,]+\s*円\s*[〜～~]', text)
    if m:
        return m.group(0).strip()
    m = _re.search(r'[¥￥]\s*[\d,]+', text)
    if m:
        return m.group(0).strip()
    return ""


def _extract_domain(url: str) -> str:
    """URLからドメイン名を取得"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain
    except Exception:
        return ""
