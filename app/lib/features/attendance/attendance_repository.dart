import '../../core/network/api_client.dart';
import '../location/location_service.dart';
import 'attendance_models.dart';

/// Evidence submitted to the authoritative `POST /attendance/verify`.
/// The server re-derives every decision from this evidence.
class VerifyEvidence {
  const VerifyEvidence({
    required this.fix,
    required this.embedding,
    required this.modelVersion,
    required this.livenessMethod,
    required this.livenessScore,
    required this.livenessPassed,
    required this.capturedAt,
    this.appVersion = '1.0.0',
    this.deviceModel,
  });

  final LocationFix fix;
  final List<double> embedding;
  final String modelVersion;
  final String livenessMethod;
  final double livenessScore;
  final bool livenessPassed;
  final DateTime capturedAt;
  final String appVersion;
  final String? deviceModel;

  Map<String, dynamic> toJson() => {
    'location': {
      'latitude': fix.latitude,
      'longitude': fix.longitude,
      'accuracy_m': double.parse(fix.accuracyMeters.toStringAsFixed(1)),
      'timestamp_utc': fix.timestamp.toUtc().toIso8601String(),
    },
    'face': {
      'embedding': embedding,
      'embedding_dim': embedding.length,
      'model_version': modelVersion,
      'liveness': {
        'method': livenessMethod,
        'score': double.parse(livenessScore.toStringAsFixed(4)),
        'passed': livenessPassed,
      },
      'captured_at_utc': capturedAt.toUtc().toIso8601String(),
    },
    'device': {
      'app_version': appVersion,
      'platform': 'android',
      if (deviceModel != null) 'device_model': deviceModel,
    },
  };
}

class AttendanceRepository {
  AttendanceRepository(this._api);

  final ApiClient _api;

  Future<GeofenceConfig> geofence() async {
    final data = await _api.get('/v1/hostels/me/geofence');
    return GeofenceConfig.fromJson(data as Map<String, dynamic>);
  }

  Future<AttendanceStatusResponse> status({String? date}) async {
    final data = await _api.get(
      '/v1/attendance/status',
      query: {if (date != null) 'date': date},
    );
    return AttendanceStatusResponse.fromJson(data as Map<String, dynamic>);
  }

  Future<AttendanceRecord> verify(VerifyEvidence evidence) async {
    final data = await _api.post(
      '/v1/attendance/verify',
      body: evidence.toJson(),
    );
    return AttendanceRecord.fromJson(data as Map<String, dynamic>);
  }

  Future<PagedRecords> history({
    String? month,
    String? status,
    int page = 1,
    int pageSize = 20,
  }) async {
    final data = await _api.get(
      '/v1/attendance/history',
      query: {
        if (month != null) 'month': month,
        if (status != null) 'status': status,
        'page': page.toString(),
        'page_size': pageSize.toString(),
      },
    );
    return PagedRecords.fromJson(data as Map<String, dynamic>);
  }

  Future<AttendanceSummary> summary({String? month}) async {
    final data = await _api.get(
      '/v1/attendance/summary',
      query: {if (month != null) 'month': month},
    );
    return AttendanceSummary.fromJson(data as Map<String, dynamic>);
  }

  Future<FaceEnrollmentStatus> faceEnrollmentStatus() async {
    final data = await _api.get('/v1/face-enrollment');
    return FaceEnrollmentStatus.fromJson(data as Map<String, dynamic>);
  }

  // There is deliberately NO putFaceEnrollment / deleteFaceEnrollment here.
  // Face enrollment is a warden action (PUT /warden/students/{id}/face-enrollment);
  // the student-facing endpoints return 403 by design, so wiring a button to
  // them would only produce a control that always fails. The status read above
  // is the one thing a student is allowed to see about their own template.
}
