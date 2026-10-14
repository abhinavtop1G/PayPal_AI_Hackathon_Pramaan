"""Locations and IP intelligence.

Geo: in production the cloud load balancer adds the client's location to every request (Google Cloud Load Balancing
custom header `X-Client-Geo-Location: {client_city},{client_city_lat_long}`); clients may also send coarse lat/lon.
IP kind: whether an address belongs to a hosting provider (datacenter) or a known anonymiser (VPN / Tor exit).
The ranges below are a small demo subset of public provider and Tor-exit ranges; production would load a maintained
feed (cloud providers publish their ranges; Tor publishes its exit list).
"""
from __future__ import annotations

import ipaddress
import math
from functools import lru_cache

# city -> (lat, lon)
CITIES = {
    "Mumbai": (19.076, 72.878), "Delhi": (28.614, 77.209), "Bengaluru": (12.972, 77.595), "Hyderabad": (17.385, 78.487),
    "Chennai": (13.083, 80.271), "Kolkata": (22.573, 88.364), "Pune": (18.520, 73.857), "Ahmedabad": (23.023, 72.571),
    "Jaipur": (26.912, 75.787), "Lucknow": (26.847, 80.947), "Chandigarh": (30.733, 76.779), "Patna": (25.594, 85.138),
    "Bhopal": (23.260, 77.413), "Guwahati": (26.144, 91.736), "Kochi": (9.931, 76.267), "Jamtara": (23.963, 86.803),
    "Ludhiana": (30.901, 75.857), "Indore": (22.720, 75.858),
}
FOREIGN = {"Dubai": (25.205, 55.271), "Singapore": (1.352, 103.820), "London": (51.507, -0.128),
           "Bangkok": (13.756, 100.502), "Phnom Penh": (11.556, 104.928)}
ALL_PLACES = {**CITIES, **FOREIGN}

# demo subset: hosting providers (AWS, Azure, Google Cloud, DigitalOcean, Linode/Akamai, OVH)
DATACENTER = ["3.0.0.0/9", "13.64.0.0/11", "34.64.0.0/10", "35.184.0.0/13", "104.131.0.0/16", "139.59.0.0/16",
              "159.89.0.0/16", "172.104.0.0/15", "51.68.0.0/16"]
# demo subset: anonymisers (Tor exits, commercial VPN egress)
ANONYMISER = ["185.220.100.0/22", "199.249.230.0/24", "45.83.64.0/22", "103.216.220.0/22"]


@lru_cache(maxsize=1)
def _nets():
    return ([ipaddress.ip_network(c) for c in DATACENTER], [ipaddress.ip_network(c) for c in ANONYMISER])


@lru_cache(maxsize=65536)
def ip_kind(ip: str | None) -> str:
    """'datacenter' | 'anonymiser' | 'residential' | 'unknown'."""
    if not ip:
        return "unknown"
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    dc, anon = _nets()
    if any(a in n for n in anon):
        return "anonymiser"
    if any(a in n for n in dc):
        return "datacenter"
    if a.is_private or a.is_loopback:
        return "unknown"
    return "residential"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def parse_geo_header(value: str | None) -> dict | None:
    """Parse the load balancer's `{client_city},{client_city_lat_long}` header, e.g. 'mumbai,19.0760,72.8777'."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 3:
        return None
    try:
        return {"city": parts[0].title() or None, "lat": float(parts[1]), "lon": float(parts[2])}
    except ValueError:
        return None
