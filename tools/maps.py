"""
Google Maps Places API ツール
- 現在地周辺の店舗・施設を検索する
"""
import os, requests

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


def search_nearby(lat: float, lng: float, keyword: str, radius: int = 1000) -> dict:
    """現在地周辺の店舗・観光スポットを検索する"""
    if not GOOGLE_MAPS_API_KEY:
        return {"available": False, "reason": "GOOGLE_MAPS_API_KEY が未設定です"}
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius":   radius,
                "keyword":  keyword,
                "language": "ja",
                "key":      GOOGLE_MAPS_API_KEY,
            },
            timeout=5
        )
        places = []
        for p in r.json().get("results", [])[:5]:
            places.append({
                "name":     p.get("name"),
                "address":  p.get("vicinity"),
                "rating":   p.get("rating"),
                "open_now": p.get("opening_hours", {}).get("open_now"),
                "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id')}",
            })
        return {"available": True, "type": "places", "places": places}
    except Exception as e:
        return {"available": False, "reason": str(e)}
