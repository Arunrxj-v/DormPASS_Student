import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/features/location/geofence_math.dart';

void main() {
  group('GeofenceMath.haversineMeters', () {
    test('zero distance for identical points', () {
      expect(
        GeofenceMath.haversineMeters(
          lat1: 12.9716,
          lon1: 79.1585,
          lat2: 12.9716,
          lon2: 79.1585,
        ),
        0,
      );
    });

    test('known short distance (~1112 m per 0.01° latitude)', () {
      final d = GeofenceMath.haversineMeters(
        lat1: 12.9716,
        lon1: 79.1585,
        lat2: 12.9816,
        lon2: 79.1585,
      );
      expect(d, closeTo(1112, 5));
    });

    test('is symmetric', () {
      final a = GeofenceMath.haversineMeters(
        lat1: 12.9716,
        lon1: 79.1585,
        lat2: 12.99,
        lon2: 79.18,
      );
      final b = GeofenceMath.haversineMeters(
        lat1: 12.99,
        lon1: 79.18,
        lat2: 12.9716,
        lon2: 79.1585,
      );
      expect(a, closeTo(b, 0.001));
    });
  });

  group('GeofenceMath.isInside (conservative uncertainty policy)', () {
    test('well inside with good accuracy', () {
      expect(
        GeofenceMath.isInside(
          distanceMeters: 30,
          accuracyMeters: 5,
          permittedRadiusMeters: 120,
        ),
        isTrue,
      );
    });

    test('boundary: uncertainty circle exactly touching radius passes', () {
      expect(
        GeofenceMath.isInside(
          distanceMeters: 115,
          accuracyMeters: 5,
          permittedRadiusMeters: 120,
        ),
        isTrue,
      );
    });

    test('boundary: uncertainty crossing radius fails', () {
      expect(
        GeofenceMath.isInside(
          distanceMeters: 116,
          accuracyMeters: 5,
          permittedRadiusMeters: 120,
        ),
        isFalse,
      );
    });

    test('center with bad accuracy fails (uncertain reading)', () {
      expect(
        GeofenceMath.isInside(
          distanceMeters: 0,
          accuracyMeters: 200,
          permittedRadiusMeters: 120,
        ),
        isFalse,
      );
    });
  });

  test('deviationMeters is zero inside and positive outside', () {
    expect(
      GeofenceMath.deviationMeters(
        distanceMeters: 50,
        permittedRadiusMeters: 120,
      ),
      0,
    );
    expect(
      GeofenceMath.deviationMeters(
        distanceMeters: 240,
        permittedRadiusMeters: 120,
      ),
      120,
    );
  });
}
