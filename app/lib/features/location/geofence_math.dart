import 'dart:math' as math;

/// Pure geofence math — kept dependency-free so it is trivially unit-testable.
abstract final class GeofenceMath {
  static const double earthRadiusMeters = 6371000.0;

  static double _rad(double degrees) => degrees * math.pi / 180.0;

  /// Great-circle (Haversine) distance in meters between two WGS-84 points.
  static double haversineMeters({
    required double lat1,
    required double lon1,
    required double lat2,
    required double lon2,
  }) {
    final p1 = _rad(lat1);
    final p2 = _rad(lat2);
    final dLat = _rad(lat2 - lat1);
    final dLon = _rad(lon2 - lon1);
    final a =
        math.pow(math.sin(dLat / 2), 2) +
        math.cos(p1) * math.cos(p2) * math.pow(math.sin(dLon / 2), 2);
    final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
    return earthRadiusMeters * c;
  }

  /// Conservative uncertainty policy: the *whole* GPS uncertainty circle must
  /// lie inside the permitted radius. Mirrors the server rule exactly.
  /// A boundary decision the client can make is UX-only — the server
  /// independently re-computes this.
  static bool isInside({
    required double distanceMeters,
    required double accuracyMeters,
    required double permittedRadiusMeters,
  }) => distanceMeters + accuracyMeters <= permittedRadiusMeters;

  /// Meters beyond the permitted radius (0 when inside).
  static double deviationMeters({
    required double distanceMeters,
    required double permittedRadiusMeters,
  }) => math.max(0, distanceMeters - permittedRadiusMeters);
}
