import 'dart:io';
import 'dart:ui';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image/image.dart' as img;

import '../../core/errors/app_exception.dart';
import '../auth/auth_providers.dart';
import '../face/face_embedder.dart';
import '../face/liveness/liveness_verifier.dart';
import '../location/geofence_math.dart';
import '../location/location_service.dart';
import 'attendance_models.dart';
import 'attendance_repository.dart';

final attendanceRepositoryProvider = Provider<AttendanceRepository>(
  (ref) => AttendanceRepository(ref.watch(apiClientProvider)),
);

final geofenceProvider = FutureProvider<GeofenceConfig>(
  (ref) => ref.watch(attendanceRepositoryProvider).geofence(),
);

final attendanceStatusProvider = FutureProvider<AttendanceStatusResponse>(
  (ref) => ref.watch(attendanceRepositoryProvider).status(),
);

final faceEnrollmentProvider = FutureProvider<FaceEnrollmentStatus>(
  (ref) => ref.watch(attendanceRepositoryProvider).faceEnrollmentStatus(),
);

final locationServiceProvider = Provider<LocationService>(
  (ref) => const LocationService(),
);

final deviceModelProvider = FutureProvider<String?>((ref) async {
  try {
    final info = await DeviceInfoPlugin().androidInfo;
    return info.model;
  } catch (_) {
    return null;
  }
});

final faceEmbedderProvider = FutureProvider<FaceEmbedder>(
  (ref) => FaceEmbedder.load(),
);

final livenessProvider = FutureProvider<LivenessVerifier>(
  (ref) => PassiveAntiSpoofVerifier.load(),
);

enum LocationStage { idle, acquiring, ready, failed }

enum FaceStage { idle, running, submitting }

/// State machine behind the two-step "Scan Check In" flow.
/// The ONLY success source is the server response from `POST /attendance/verify`.
class ScanFlowState {
  const ScanFlowState({
    this.locationStage = LocationStage.idle,
    this.fix,
    this.distanceM,
    this.inside,
    this.locationError,
    this.simulateOutside = false,
    this.faceStage = FaceStage.idle,
    this.faceError,
    this.liveness,
    this.pipelineStep = 0,
    this.result,
    this.sessionRef,
  });

  final LocationStage locationStage;
  final LocationFix? fix;
  final double? distanceM;
  final bool? inside;
  final AppException? locationError;
  final bool simulateOutside;

  final FaceStage faceStage;
  final AppException? faceError;
  final LivenessResult? liveness;

  /// 0 = detection, 1 = liveness, 2 = match (server).
  final int pipelineStep;

  final AttendanceRecord? result;
  final String? sessionRef;

  bool get canProceedToFace =>
      locationStage == LocationStage.ready &&
      inside == true &&
      faceStage == FaceStage.idle;

  ScanFlowState copy({
    LocationStage? locationStage,
    LocationFix? fix,
    double? distanceM,
    bool? inside,
    AppException? locationError,
    bool? simulateOutside,
    FaceStage? faceStage,
    AppException? faceError,
    LivenessResult? liveness,
    int? pipelineStep,
    AttendanceRecord? result,
    String? sessionRef,
  }) => ScanFlowState(
    locationStage: locationStage ?? this.locationStage,
    fix: fix ?? this.fix,
    distanceM: distanceM ?? this.distanceM,
    inside: inside ?? this.inside,
    locationError: locationError,
    simulateOutside: simulateOutside ?? this.simulateOutside,
    faceStage: faceStage ?? this.faceStage,
    faceError: faceError,
    liveness: liveness ?? this.liveness,
    pipelineStep: pipelineStep ?? this.pipelineStep,
    result: result ?? this.result,
    sessionRef: sessionRef ?? this.sessionRef,
  );
}

class ScanFlowController extends Notifier<ScanFlowState> {
  @override
  ScanFlowState build() => ScanFlowState(
    sessionRef: 'HP-${DateTime.now().millisecondsSinceEpoch % 100000}',
  );

  GeofenceConfig get _geofence => ref.read(geofenceProvider).requireValue;

  /// Step 1: acquire a fix and run the local geofence pre-check.
  /// UX-only — the server re-checks every constraint independently.
  Future<void> acquireLocation() async {
    if (state.locationStage == LocationStage.acquiring) return;
    state = state.copy(
      locationStage: LocationStage.acquiring,
      locationError: null,
    );
    try {
      final fix = await ref.read(locationServiceProvider).getCurrentFix();
      final distance = GeofenceMath.haversineMeters(
        lat1: fix.latitude,
        lon1: fix.longitude,
        lat2: _geofence.latitude,
        lon2: _geofence.longitude,
      );
      final inside = GeofenceMath.isInside(
        distanceMeters: distance,
        accuracyMeters: fix.accuracyMeters,
        permittedRadiusMeters: _geofence.permittedRadiusM,
      );
      if (fix.accuracyMeters > _geofence.maxLocationAccuracyM) {
        state = state.copy(
          locationStage: LocationStage.failed,
          locationError: const AppException('local_location_unusable'),
        );
        return;
      }
      state = state.copy(
        locationStage: LocationStage.ready,
        fix: fix,
        distanceM: distance,
        inside: state.simulateOutside ? false : inside,
        locationError: null,
      );
    } on AppException catch (e) {
      state = state.copy(locationStage: LocationStage.failed, locationError: e);
    }
  }

  /// Demo affordance from the design ("Test Outside-Zone Rule"): affects the
  /// local pre-check display ONLY. The server geofence is untouched.
  void setSimulateOutside(bool value) {
    if (state.fix == null || state.distanceM == null) {
      state = state.copy(simulateOutside: value);
      return;
    }
    final realInside = GeofenceMath.isInside(
      distanceMeters: state.distanceM!,
      accuracyMeters: state.fix!.accuracyMeters,
      permittedRadiusMeters: _geofence.permittedRadiusM,
    );
    state = state.copy(
      simulateOutside: value,
      inside: value ? false : realInside,
    );
  }

  /// Step 2: crop → liveness → embedding → submit evidence to the server.
  Future<void> verifyFaceAndSubmit({
    required File stillImage,
    required Rect faceBox,
  }) async {
    state = state.copy(
      faceStage: FaceStage.running,
      faceError: null,
      pipelineStep: 0,
    );
    try {
      final upright = FaceEmbedder.decodeUprightJpeg(stillImage);
      if (upright == null) {
        state = state.copy(
          faceStage: FaceStage.idle,
          faceError: const AppException('local_no_face'),
        );
        return;
      }

      // Tight crop for both models (margin is applied by the embedder path;
      // here we crop tightly ourselves so liveness and embedding share it).
      final crop = _tightCrop(upright, faceBox);

      // --- Liveness (passive PAD) ---
      state = state.copy(pipelineStep: 1);
      final verifier = await ref.read(livenessProvider.future);
      final liveness = verifier.verify(crop);
      state = state.copy(liveness: liveness);
      if (!liveness.passed) {
        state = state.copy(
          faceStage: FaceStage.idle,
          faceError: const AppException('liveness_failed'),
        );
        return;
      }

      // --- Embedding ---
      final embedder = await ref.read(faceEmbedderProvider.future);
      final embedding = embedder.embed(crop);

      // --- Submit (server decides) ---
      state = state.copy(faceStage: FaceStage.submitting, pipelineStep: 2);
      final deviceModel = await ref.read(deviceModelProvider.future);
      final record = await ref
          .read(attendanceRepositoryProvider)
          .verify(
            VerifyEvidence(
              fix: state.fix!,
              embedding: embedding,
              modelVersion: FaceEmbedder.modelVersion,
              livenessMethod: liveness.method,
              livenessScore: liveness.score,
              livenessPassed: liveness.passed,
              capturedAt: DateTime.now(),
              deviceModel: deviceModel,
            ),
          );
      state = state.copy(
        faceStage: FaceStage.idle,
        result: record,
        pipelineStep: 3,
      );
    } on AppException catch (e) {
      state = state.copy(faceStage: FaceStage.idle, faceError: e);
    } catch (_) {
      state = state.copy(
        faceStage: FaceStage.idle,
        faceError: const AppException('local_server_unreachable'),
      );
    }
  }

  /// Clears a face-stage error so the camera can retry.
  void clearFaceError() => state = state.copy(faceError: null);

  void reset() => state = ScanFlowState(
    sessionRef: 'HP-${DateTime.now().millisecondsSinceEpoch % 100000}',
  );

  static img.Image _tightCrop(img.Image upright, Rect box) {
    final left = box.left.round().clamp(0, upright.width - 1);
    final top = box.top.round().clamp(0, upright.height - 1);
    final right = box.right.round().clamp(left + 1, upright.width);
    final bottom = box.bottom.round().clamp(top + 1, upright.height);
    return img.copyCrop(
      upright,
      x: left,
      y: top,
      width: right - left,
      height: bottom - top,
    );
  }
}

final scanFlowProvider = NotifierProvider<ScanFlowController, ScanFlowState>(
  ScanFlowController.new,
);
