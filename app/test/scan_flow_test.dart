import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/core/errors/app_exception.dart';
import 'package:hostelpass/features/attendance/attendance_models.dart';
import 'package:hostelpass/features/attendance/scan_flow_controller.dart';
import 'package:hostelpass/features/location/location_service.dart';

class _FakeLocationService implements LocationService {
  _FakeLocationService({this.fix, this.error});

  final LocationFix? fix;
  final AppException? error;

  @override
  Future<LocationFix> getCurrentFix({Duration timeout = const Duration(seconds: 20)}) async {
    if (error != null) throw error!;
    return fix!;
  }
}

const _geofence = GeofenceConfig(
  hostelId: 'h1',
  name: 'Hostel A',
  anchorLabel: 'Hostel A Gate',
  latitude: 12.9716,
  longitude: 77.5946,
  permittedRadiusM: 100,
  maxLocationAccuracyM: 50,
  timezone: 'Asia/Kolkata',
  windowStart: '21:00',
  windowEnd: '23:00',
  requireLiveness: true,
  faceMatchThreshold: 0.75,
);

LocationFix _fixAt(double lat, double lon, {double accuracy = 10}) =>
    LocationFix(latitude: lat, longitude: lon, accuracyMeters: accuracy, timestamp: DateTime.now());

Future<ProviderContainer> _containerWith(_FakeLocationService location) async {
  final container = ProviderContainer(
    overrides: [
      geofenceProvider.overrideWith((ref) async => _geofence),
      locationServiceProvider.overrideWithValue(location),
    ],
  );
  addTearDown(container.dispose);
  // Resolve the geofence future so ScanFlowController's requireValue works.
  await container.read(geofenceProvider.future);
  return container;
}

void main() {
  group('ScanFlowController location stage', () {
    test('inside geofence → ready + canProceedToFace', () async {
      // ~11 m north of the anchor.
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.97161, 77.5946)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.ready);
      expect(state.inside, isTrue);
      expect(state.distanceM, isNotNull);
      expect(state.distanceM!, lessThan(100));
      expect(state.locationError, isNull);
      expect(state.canProceedToFace, isTrue);
    });

    test('outside geofence → ready but not inside, cannot proceed', () async {
      // ~1.1 km north — far outside the 100 m radius.
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.9816, 77.5946)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.ready);
      expect(state.inside, isFalse);
      expect(state.canProceedToFace, isFalse);
    });

    test('accuracy worse than server max → failed with local error', () async {
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.9716, 77.5946, accuracy: 120)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.failed);
      expect(state.locationError?.code, 'local_location_unusable');
      expect(state.canProceedToFace, isFalse);
    });

    test('accuracy above server max fails even at the anchor point', () async {
      // The controller rejects fixes with accuracy > max_location_accuracy_m
      // outright — a 90 m fix is unusable regardless of distance. (The server
      // applies the same conservative uncertainty rule independently.)
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.9716, 77.5946, accuracy: 90)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.failed);
      expect(state.locationError?.code, 'local_location_unusable');
    });

    test('location service error → failed, error code preserved', () async {
      final container = await _containerWith(
        _FakeLocationService(error: const AppException('local_location_permission_denied')),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.failed);
      expect(state.locationError?.code, 'local_location_permission_denied');
    });

    test('simulateOutside only fakes the local pre-check display', () async {
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.97161, 77.5946)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      expect(container.read(scanFlowProvider).inside, isTrue);

      flow.setSimulateOutside(true);
      expect(container.read(scanFlowProvider).inside, isFalse);
      // Still holds the real fix and distance — server remains authoritative.
      expect(container.read(scanFlowProvider).fix, isNotNull);
      expect(container.read(scanFlowProvider).distanceM, lessThan(100));

      // Toggling back restores the real evaluation.
      flow.setSimulateOutside(false);
      expect(container.read(scanFlowProvider).inside, isTrue);
    });

    test('reset returns to idle with a fresh session ref', () async {
      final container = await _containerWith(
        _FakeLocationService(fix: _fixAt(12.9716, 77.5946)),
      );
      final flow = container.read(scanFlowProvider.notifier);
      await flow.acquireLocation();
      flow.reset();
      final state = container.read(scanFlowProvider);

      expect(state.locationStage, LocationStage.idle);
      expect(state.inside, isNull);
      expect(state.fix, isNull);
      expect(state.sessionRef, isNotNull);
    });
  });
}
