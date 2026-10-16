"""Geofence math: haversine distance + conservative boundary policy.

docs/ARCHITECTURE.md: inside ⇔ haversine(pos, anchor) + accuracy_m
<= permitted_radius_m — the whole uncertainty circle must fit inside the
permitted radius. Client coordinates can never widen this rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0

BOUNDARY_POLICY_CONSERVATIVE = "conservative"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points (R = 6 371 000 m)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def is_inside_conservative(distance_m: float, accuracy_m: float, permitted_radius_m: float) -> bool:
    """Conservative decision: the full accuracy circle must fit the radius."""
    return distance_m + accuracy_m <= permitted_radius_m


@dataclass(frozen=True)
class GeofenceDecision:
    """Result of evaluating a GPS fix against a hostel's geofence."""

    distance_m: float
    inside: bool


def evaluate(latitude: float, longitude: float, accuracy_m: float,
             anchor_lat: float, anchor_lon: float, permitted_radius_m: float) -> GeofenceDecision:
    """Evaluate one fix against an anchor using the conservative policy."""
    distance = haversine_m(latitude, longitude, anchor_lat, anchor_lon)
    return GeofenceDecision(
        distance_m=distance,
        inside=is_inside_conservative(distance, accuracy_m, permitted_radius_m),
    )
