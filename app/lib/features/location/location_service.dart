import 'package:geolocator/geolocator.dart';

import '../../core/errors/app_exception.dart';

/// A single usable GPS reading.
class LocationFix {
  const LocationFix({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
    required this.timestamp,
  });

  final double latitude;
  final double longitude;
  final double accuracyMeters;
  final DateTime timestamp;

  factory LocationFix.fromPosition(Position p) => LocationFix(
    latitude: p.latitude,
    longitude: p.longitude,
    accuracyMeters: p.accuracy,
    timestamp: p.timestamp.toUtc(),
  );
}

/// Wraps geolocator with the permission / service / timeout error taxonomy the
/// app must present. Location is requested only during an explicit check-in —
/// never continuously, never in the background.
class LocationService {
  const LocationService();

  Future<LocationFix> getCurrentFix({
    Duration timeout = const Duration(seconds: 20),
  }) async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw const AppException('local_location_services_disabled');
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied) {
      throw const AppException('local_location_permission_denied');
    }
    if (permission == LocationPermission.deniedForever) {
      throw const AppException('local_location_permission_denied_forever');
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      ).timeout(timeout);
      return LocationFix.fromPosition(position);
    } on Exception {
      throw const AppException('local_location_timeout');
    }
  }
}
