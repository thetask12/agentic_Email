"""
Indian state/city normalization. "Raipur, CG" / "Raipur, Chhattisgarh" /
"Raipur" all normalize to city=Raipur, state=Chhattisgarh.
"""
from __future__ import annotations
import re

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
    "Chandigarh", "Andaman and Nicobar Islands", "Dadra and Nagar Haveli and Daman and Diu",
    "Lakshadweep",
]

STATE_ABBREVIATIONS = {
    "CG": "Chhattisgarh", "MP": "Madhya Pradesh", "MH": "Maharashtra",
    "UP": "Uttar Pradesh", "RJ": "Rajasthan", "GJ": "Gujarat", "KA": "Karnataka",
    "TN": "Tamil Nadu", "TS": "Telangana", "AP": "Andhra Pradesh", "WB": "West Bengal",
    "PB": "Punjab", "HR": "Haryana", "BR": "Bihar", "JH": "Jharkhand", "OD": "Odisha",
    "OR": "Odisha", "KL": "Kerala", "AS": "Assam", "HP": "Himachal Pradesh",
    "UK": "Uttarakhand", "UA": "Uttarakhand", "GA": "Goa", "DL": "Delhi", "JK": "Jammu and Kashmir",
}

# A modest but useful city -> state map for common cities used in disambiguation
# when a source only supplies a city name. Extend as needed; not exhaustive.
CITY_STATE_HINTS = {
    "raipur": "Chhattisgarh", "bilaspur": "Chhattisgarh", "durg": "Chhattisgarh",
    "bhilai": "Chhattisgarh", "korba": "Chhattisgarh", "raigarh": "Chhattisgarh",
    "pune": "Maharashtra", "mumbai": "Maharashtra", "nagpur": "Maharashtra",
    "nashik": "Maharashtra", "thane": "Maharashtra",
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka",
    "hyderabad": "Telangana", "warangal": "Telangana",
    "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu",
    "delhi": "Delhi", "new delhi": "Delhi",
    "gurugram": "Haryana", "gurgaon": "Haryana", "faridabad": "Haryana",
    "noida": "Uttar Pradesh", "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh",
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan",
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
    "kolkata": "West Bengal", "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh",
    "patna": "Bihar", "ranchi": "Jharkhand", "bhubaneswar": "Odisha",
    "kochi": "Kerala", "thiruvananthapuram": "Kerala", "guwahati": "Assam",
    "chandigarh": "Chandigarh",
}


def normalize_state(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in STATE_ABBREVIATIONS:
        return STATE_ABBREVIATIONS[upper]
    for state in INDIAN_STATES:
        if state.lower() == raw.lower():
            return state
    return raw.title()


def normalize_city(raw: str | None) -> str | None:
    if not raw:
        return None
    city = re.split(r"[,/]", raw.strip())[0].strip()
    return city.title() if city else None


def normalize_location(location: str | None) -> tuple[str | None, str | None]:
    """Parse a free-text location string into (city, state)."""
    if not location:
        return None, None
    parts = [p.strip() for p in re.split(r"[,/]", location) if p.strip()]
    if not parts:
        return None, None
    city = normalize_city(parts[0])
    state = None
    if len(parts) > 1:
        state = normalize_state(parts[1])
    if not state and city:
        state = CITY_STATE_HINTS.get(city.lower())
    return city, state


def city_in_state(city: str | None, state: str | None) -> bool:
    if not city:
        return False
    hint = CITY_STATE_HINTS.get(city.lower())
    if not hint or not state:
        return True  # unknown mapping: don't over-filter
    return hint.lower() == state.lower()
