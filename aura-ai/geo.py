"""Geographic data for AURA AI food banks.

Each food bank in the catalog directory is given a real latitude/longitude so it
can be placed accurately on the map. Coordinates are approximate street-level
points for the named organization where known, otherwise the city center.

Also provides a small helper to turn the engine's per-food-bank coverage/urgency
into a map status color (green / yellow / red) and a point-in-danger-zone test
used for the "safest route" avoidance logic.
"""
from __future__ import annotations

import math

# City centers (fallback when an exact org location isn't pinned).
CITY_COORDS: dict[str, tuple[float, float]] = {
    "San Jose": (37.3382, -121.8863),
    "Alviso": (37.4269, -121.9752),
    "Campbell": (37.2872, -121.9500),
    "Cupertino": (37.3230, -122.0322),
    "Gilroy": (37.0058, -121.5683),
    "Milpitas": (37.4323, -121.8996),
    "Morgan Hill": (37.1305, -121.6544),
    "Mountain View": (37.3861, -122.0839),
    "Palo Alto": (37.4419, -122.1430),
    "Santa Clara": (37.3541, -121.9552),
    "Sunnyvale": (37.3688, -122.0363),
    "Half Moon Bay": (37.4636, -122.4286),
    "Pacifica": (37.6138, -122.4869),
    "East Palo Alto": (37.4688, -122.1411),
    "Daly City": (37.6879, -122.4702),
    "Redwood City": (37.4852, -122.2364),
    "Unknown": (37.3541, -121.9552),  # fall back to county center
}

# Street-level coordinates for specific organizations (approximate but realistic).
ORG_COORDS: dict[str, tuple[float, float]] = {
    "Second Harvest of Silicon Valley": (37.4138, -121.9637),
    "Our Lady Star of the Sea Church": (37.4258, -121.9741),
    "Campbell United Methodist Church": (37.2874, -121.9470),
    "LifeSTEPS – Rincon Gardens": (37.2905, -121.9513),
    "St. Lucy Catholic Parish": (37.2855, -121.9412),
    "The Home Church": (37.2918, -121.9601),
    "West Valley Community Services": (37.3192, -122.0146),
    "Union Church of Cupertino": (37.3169, -122.0420),
    "West Valley Presbyterian Church": (37.3098, -122.0269),
    "De Anza College Food Pantry": (37.3192, -122.0450),
    "South County Community Services": (37.0101, -121.5660),
    "The Salvation Army – Gilroy": (37.0047, -121.5760),
    "Gavilan College Food Pantry": (36.9986, -121.5900),
    "Rebekah Children’s Services": (37.1201, -121.6410),
    "Christian Worship Center": (37.4280, -121.9050),
    "Mt. Olive Ministries": (37.4360, -121.9020),
    "Crosspoint Church of Silicon Valley": (37.4150, -121.8970),
    "Muslim Sisters Helping": (37.4401, -121.8905),
    "St. Catherine Church – Reachout": (37.1289, -121.6520),
    "Community Solutions – La Casa del Puente": (37.1340, -121.6480),
    "Community Services Agency": (37.3930, -122.0810),
    "Hope’s Corner": (37.3975, -122.0795),
    "Mountain View Senior Center": (37.4007, -122.0880),
    "Alta Housing": (37.4440, -122.1600),
    "South Palo Alto Food Closet": (37.4190, -122.1210),
    "Downtown Food Closet of Palo Alto": (37.4450, -122.1610),
    "St. Andrew’s United Methodist Church": (37.4100, -122.1180),
    "Sacred Heart Community Service": (37.3220, -121.8640),
    "The Jerry Larson Food Basket": (37.3350, -121.8900),
    "FISH of South Valley": (37.2400, -121.7900),
    "True Vine Food Pantry": (37.3490, -121.9080),
    "CityTeam in the Neighborhood": (37.3390, -121.8980),
    "El Buen Pastor Food Pantry": (37.3480, -121.8550),
    "Loaves & Fishes Family Kitchen": (37.3700, -121.8600),
    "Martha’s Kitchen": (37.3110, -121.8560),
    "St. Justin Community Ministry": (37.3230, -121.9780),
    "Mission Market Pantry": (37.3490, -121.9390),
    "River of Life Foundation": (37.3880, -121.9790),
    "Sunnyvale Community Services": (37.3780, -122.0210),
    "The Salvation Army – Sunnyvale": (37.3760, -122.0300),
    "Our Daily Bread": (37.3690, -122.0290),
    "Corner Pantry": (37.3620, -122.0420),
    "Coastside Hope": (37.4640, -122.4310),
    "Pacifica Resource Center – Buel": (37.6160, -122.4880),
    "Ecumenical Hunger Program": (37.4650, -122.1390),
    "WeHOPE": (37.4700, -122.1350),
    "Daly City Partnership": (37.6860, -122.4680),
    "St. Vincent de Paul – St. Pius": (37.4830, -122.2290),
    "The Salvation Army – Redwood City": (37.4870, -122.2290),
    "St. Francis Center": (37.4760, -122.2080),
}


def coords_for(org: str, city: str) -> tuple[float, float]:
    """Best-known location for an organization, else its city center."""
    if org in ORG_COORDS:
        return ORG_COORDS[org]
    return CITY_COORDS.get(city, CITY_COORDS["Unknown"])


def status_from_metrics(coverage: float | None, max_urgency: int) -> str:
    """Map a food bank's coverage + top urgency to a green/yellow/red status.

    red    -> critical need or coverage under 50%
    yellow -> elevated need or coverage 50-80%
    green  -> well supplied (coverage >= 80%, no critical open need)
    """
    if coverage is None:
        return "none"
    if max_urgency >= 5 or coverage < 0.5:
        return "red"
    if max_urgency >= 3 or coverage < 0.8:
        return "yellow"
    return "green"


# --------------------------------------------------------------------------- #
# Geometry helpers (used by routing to avoid danger zones)
# --------------------------------------------------------------------------- #
def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two lat/long points, in kilometers."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def point_in_circle(point: tuple[float, float], center: tuple[float, float], radius_km: float) -> bool:
    return haversine_km(point, center) <= radius_km
