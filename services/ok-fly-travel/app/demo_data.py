from __future__ import annotations

from typing import Any, Dict, List


CITY_DEMO_DATA: Dict[str, Dict[str, Any]] = {
    "Tokyo": {
        "city_code": "TYO",
        "display_name": "Tokyo, Japan",
        "crypto_friendly": {
            "tags": ["high_card_acceptance", "tech_friendly", "web3_presence"],
            "areas": ["Shibuya", "Shinjuku", "Ginza"],
            "notes": [
                "Prefer card-friendly hotels and easy late check-in.",
                "Strong fit for tech-savvy and crypto-native travelers.",
            ],
        },
        "fallback_pois": [
            {"name": "Senso-ji", "kind": "historic", "rating": 4.8, "distance_km": 2.1},
            {"name": "Tokyo Skytree", "kind": "viewpoint", "rating": 4.7, "distance_km": 3.4},
            {"name": "Shibuya Crossing", "kind": "attraction", "rating": 4.9, "distance_km": 1.2},
            {"name": "teamLab Planets", "kind": "museum", "rating": 4.6, "distance_km": 4.1},
            {"name": "Meiji Jingu", "kind": "historic", "rating": 4.5, "distance_km": 2.8},
            {"name": "Harajuku Takeshita St", "kind": "attraction", "rating": 4.3, "distance_km": 2.5},
            {"name": "Shinjuku Gyoen", "kind": "park", "rating": 4.6, "distance_km": 3.0},
            {"name": "Akihabara Electric Town", "kind": "attraction", "rating": 4.4, "distance_km": 2.9},
        ],
    },
    "Singapore": {
        "city_code": "SIN",
        "display_name": "Singapore",
        "crypto_friendly": {
            "tags": ["cashless", "fintech_hub", "safe_transit"],
            "areas": ["Marina Bay", "Bugis", "Orchard"],
            "notes": [
                "Excellent cashless infrastructure.",
                "Good for short premium trips and business travel.",
            ],
        },
        "fallback_pois": [
            {"name": "Marina Bay Sands", "kind": "attraction", "rating": 4.8, "distance_km": 1.0},
            {"name": "Gardens by the Bay", "kind": "park", "rating": 4.9, "distance_km": 1.6},
            {"name": "Chinatown", "kind": "historic", "rating": 4.4, "distance_km": 2.3},
            {"name": "National Gallery Singapore", "kind": "museum", "rating": 4.7, "distance_km": 1.9},
            {"name": "Clarke Quay", "kind": "attraction", "rating": 4.3, "distance_km": 2.1},
        ],
    },
    "Hong Kong": {
        "city_code": "HKG",
        "display_name": "Hong Kong",
        "crypto_friendly": {
            "tags": ["card_acceptance", "dense_city", "web3_presence"],
            "areas": ["Central", "Tsim Sha Tsui", "Causeway Bay"],
            "notes": ["Best for short trips, nightlife, and efficient transit."],
        },
        "fallback_pois": [
            {"name": "Victoria Peak", "kind": "viewpoint", "rating": 4.9, "distance_km": 3.2},
            {"name": "Tsim Sha Tsui Promenade", "kind": "attraction", "rating": 4.6, "distance_km": 2.0},
            {"name": "M+ Museum", "kind": "museum", "rating": 4.5, "distance_km": 2.8},
            {"name": "Temple Street Night Market", "kind": "market", "rating": 4.3, "distance_km": 1.8},
        ],
    },
    "Bangkok": {
        "city_code": "BKK",
        "display_name": "Bangkok, Thailand",
        "crypto_friendly": {
            "tags": ["budget_friendly", "street_food", "growing_fintech"],
            "areas": ["Sukhumvit", "Silom", "Rattanakosin"],
            "notes": ["Excellent value destination. Growing crypto ATM presence."],
        },
        "fallback_pois": [
            {"name": "Wat Phra Kaew", "kind": "historic", "rating": 4.9, "distance_km": 2.5},
            {"name": "Chatuchak Weekend Market", "kind": "market", "rating": 4.6, "distance_km": 8.0},
            {"name": "Wat Arun", "kind": "historic", "rating": 4.7, "distance_km": 3.1},
            {"name": "Asiatique The Riverfront", "kind": "attraction", "rating": 4.4, "distance_km": 6.2},
        ],
    },
    "Seoul": {
        "city_code": "SEL",
        "display_name": "Seoul, South Korea",
        "crypto_friendly": {
            "tags": ["tech_hub", "cashless", "crypto_friendly"],
            "areas": ["Gangnam", "Hongdae", "Myeongdong"],
            "notes": ["South Korea has high crypto adoption. Strong cashless payment infrastructure."],
        },
        "fallback_pois": [
            {"name": "Gyeongbokgung Palace", "kind": "historic", "rating": 4.8, "distance_km": 3.0},
            {"name": "N Seoul Tower", "kind": "viewpoint", "rating": 4.7, "distance_km": 2.5},
            {"name": "Bukchon Hanok Village", "kind": "historic", "rating": 4.6, "distance_km": 3.2},
            {"name": "Hongdae Street", "kind": "attraction", "rating": 4.5, "distance_km": 5.0},
        ],
    },
    "Dubai": {
        "city_code": "DXB",
        "display_name": "Dubai, UAE",
        "crypto_friendly": {
            "tags": ["luxury", "international", "crypto_regulation_friendly"],
            "areas": ["Downtown", "Marina", "Palm Jumeirah"],
            "notes": [
                "Dubai has a crypto-friendly regulatory environment.",
                "Premium destination with strong card acceptance.",
            ],
        },
        "fallback_pois": [
            {"name": "Burj Khalifa", "kind": "viewpoint", "rating": 4.9, "distance_km": 1.0},
            {"name": "Dubai Mall", "kind": "attraction", "rating": 4.7, "distance_km": 1.2},
            {"name": "Palm Jumeirah", "kind": "attraction", "rating": 4.6, "distance_km": 8.0},
            {"name": "Gold Souk", "kind": "market", "rating": 4.4, "distance_km": 5.0},
        ],
    },
}


def city_demo_by_name(destination: str) -> Dict[str, Any]:
    key = destination.strip().lower()
    for city, data in CITY_DEMO_DATA.items():
        if city.lower() in key or key in city.lower():
            return data
    return {
        "city_code": "TYO",
        "display_name": destination,
        "crypto_friendly": {
            "tags": ["cashless_recommended", "card_payment_check"],
            "areas": ["city center", "transit-rich district"],
            "notes": ["Use heuristic crypto-friendly labels as advisory only."],
        },
        "fallback_pois": [
            {"name": "City Center Walk", "kind": "attraction", "rating": 4.0, "distance_km": 1.2},
            {"name": "Local Museum", "kind": "museum", "rating": 4.1, "distance_km": 2.0},
            {"name": "Best Viewpoint", "kind": "viewpoint", "rating": 4.2, "distance_km": 3.1},
            {"name": "Central Park", "kind": "park", "rating": 4.0, "distance_km": 1.5},
        ],
    }
