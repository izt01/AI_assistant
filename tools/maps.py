"""
Google Maps Places API ツール
- 現在地周辺の店舗・施設を検索する
- 住所テキストをlat/lngに変換する
"""
import os, requests


def _api_key() -> str:
    """起動後に設定された環境変数も拾えるよう毎回取得する"""
    return os.getenv("GOOGLE_MAPS_API_KEY", "")


def geocode_address(address: str) -> dict:
    """住所テキスト → lat/lng に変換する（Geocoding API）"""
    key = _api_key()
    if not key:
        return {"ok": False, "reason": "GOOGLE_MAPS_API_KEY が未設定です"}
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "language": "ja", "key": key},
            timeout=5
        )
        results = r.json().get("results", [])
        if not results:
            return {"ok": False, "reason": f"住所が見つかりませんでした: {address}"}
        loc = results[0]["geometry"]["location"]
        return {"ok": True, "lat": loc["lat"], "lng": loc["lng"],
                "formatted": results[0].get("formatted_address", address)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def search_nearby(lat: float, lng: float, keyword: str, radius: int = 800) -> dict:
    """現在地周辺の店舗・観光スポットを検索する。0件なら自動的にradiusを広げて再検索。"""
    key = _api_key()
    if not key:
        return {"available": False, "reason": "GOOGLE_MAPS_API_KEY が未設定です"}

    # 0件なら radius を段階的に広げる
    for r in sorted({radius, 1500, 3000}):
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{lat},{lng}",
                    "radius":   r,
                    "keyword":  keyword,
                    "language": "ja",
                    "key":      key,
                },
                timeout=8
            )
            data = resp.json()
            print(f"[Maps] keyword={keyword} radius={r} status={data.get('status')} results={len(data.get('results',[]))}")

            results = data.get("results", [])
            if results:
                places = []
                for p in results[:5]:
                    places.append({
                        "name":     p.get("name"),
                        "address":  p.get("vicinity"),
                        "rating":   p.get("rating"),
                        "open_now": p.get("opening_hours", {}).get("open_now"),
                        "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id')}",
                    })
                return {"available": True, "type": "places", "places": places, "radius_used": r}

        except Exception as e:
            print(f"[Maps] エラー radius={r}: {e}")
            return {"available": False, "reason": str(e)}

    return {"available": True, "type": "places", "places": [], "radius_used": 3000,
            "message": "3000m以内でお店が見つかりませんでした"}
