/// Server-provided geofence configuration. Coordinates & radius are
/// server-controlled; the client can never widen them.
class GeofenceConfig {
  const GeofenceConfig({
    required this.hostelId,
    required this.name,
    this.block,
    required this.anchorLabel,
    required this.latitude,
    required this.longitude,
    required this.permittedRadiusM,
    required this.maxLocationAccuracyM,
    required this.timezone,
    required this.windowStart,
    required this.windowEnd,
    required this.requireLiveness,
    required this.faceMatchThreshold,
    this.wardenName,
    this.wardenExtension,
  });

  final String hostelId;
  final String name;
  final String? block;
  final String anchorLabel;
  final double latitude;
  final double longitude;
  final double permittedRadiusM;
  final double maxLocationAccuracyM;
  final String timezone;
  final String windowStart;
  final String windowEnd;
  final bool requireLiveness;
  final double faceMatchThreshold;
  final String? wardenName;
  final String? wardenExtension;

  factory GeofenceConfig.fromJson(Map<String, dynamic> j) => GeofenceConfig(
    hostelId: j['hostel_id'] as String,
    name: j['name'] as String,
    block: j['block'] as String?,
    anchorLabel: (j['anchor_label'] as String?) ?? (j['name'] as String),
    latitude: (j['latitude'] as num).toDouble(),
    longitude: (j['longitude'] as num).toDouble(),
    permittedRadiusM: (j['permitted_radius_m'] as num).toDouble(),
    maxLocationAccuracyM: (j['max_location_accuracy_m'] as num).toDouble(),
    timezone: j['timezone'] as String,
    windowStart: j['window_start'] as String,
    windowEnd: j['window_end'] as String,
    requireLiveness: j['require_liveness'] as bool? ?? true,
    faceMatchThreshold: (j['face_match_threshold'] as num?)?.toDouble() ?? 0.75,
    wardenName: j['warden_name'] as String?,
    wardenExtension: j['warden_extension'] as String?,
  );
}

/// Attendance record as returned by the API (docs/API.md).
class AttendanceRecord {
  const AttendanceRecord({
    this.id,
    required this.reference,
    required this.date,
    this.recordedAt,
    this.recordedAtLocal,
    required this.status,
    required this.outcome,
    this.distanceM,
    this.accuracyM,
    this.faceSimilarity,
    this.livenessMethod,
    this.livenessScore,
    this.reason,
  });

  final String? id;
  final String reference;
  final String date;
  final DateTime? recordedAt;
  final String? recordedAtLocal;

  /// present | pending | absent
  final String status;

  /// verified | pending_review (absences synthesized by the server have none)
  final String? outcome;

  final double? distanceM;
  final double? accuracyM;
  final double? faceSimilarity;
  final String? livenessMethod;
  final double? livenessScore;
  final String? reason;

  bool get isAbsent => status == 'absent';
  bool get isPending => status == 'pending';
  bool get isPresent => status == 'present';

  /// "08:42 PM" in hostel-local time.
  String get timeLabel {
    final local = recordedAtLocal;
    if (local == null) return '—';
    final t = RegExp(r'T(\d{2}):(\d{2})').firstMatch(local);
    if (t == null) return '—';
    var h = int.parse(t.group(1)!);
    final m = t.group(2)!;
    final suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12 == 0 ? 12 : h % 12;
    return '${h.toString().padLeft(2, '0')}:$m $suffix';
  }

  factory AttendanceRecord.fromJson(Map<String, dynamic> j) => AttendanceRecord(
    id: j['id'] as String?,
    reference: j['reference'] as String? ?? '—',
    date: j['date'] as String,
    recordedAt: j['recorded_at'] != null
        ? DateTime.tryParse(j['recorded_at'] as String)?.toUtc()
        : null,
    recordedAtLocal: j['recorded_at_local'] as String?,
    status: j['status'] as String,
    outcome: j['outcome'] as String?,
    distanceM: (j['distance_m'] as num?)?.toDouble(),
    accuracyM: (j['accuracy_m'] as num?)?.toDouble(),
    faceSimilarity: (j['face_similarity'] as num?)?.toDouble(),
    livenessMethod: j['liveness_method'] as String?,
    livenessScore: (j['liveness_score'] as num?)?.toDouble(),
    reason: j['reason'] as String?,
  );
}

class AttendanceWindow {
  const AttendanceWindow({
    required this.open,
    required this.opensAt,
    required this.closesAt,
    this.minutesRemaining,
    required this.timezone,
  });

  final bool open;
  final String opensAt;
  final String closesAt;
  final int? minutesRemaining;
  final String timezone;

  factory AttendanceWindow.fromJson(Map<String, dynamic> j) => AttendanceWindow(
    open: j['open'] as bool? ?? false,
    opensAt: j['opens_at'] as String? ?? '--:--',
    closesAt: j['closes_at'] as String? ?? '--:--',
    minutesRemaining: (j['minutes_remaining'] as num?)?.toInt(),
    timezone: j['timezone'] as String? ?? '',
  );
}

class AttendanceStatusResponse {
  const AttendanceStatusResponse({
    required this.date,
    required this.marked,
    this.outcome,
    this.record,
    required this.window,
    required this.canMark,
    required this.faceEnrolled,
  });

  final String date;
  final bool marked;
  final String? outcome;
  final AttendanceRecord? record;
  final AttendanceWindow window;
  final bool canMark;
  final bool faceEnrolled;

  factory AttendanceStatusResponse.fromJson(Map<String, dynamic> j) =>
      AttendanceStatusResponse(
        date: j['date'] as String,
        marked: j['marked'] as bool? ?? false,
        outcome: j['outcome'] as String?,
        record: j['record'] is Map
            ? AttendanceRecord.fromJson(j['record'] as Map<String, dynamic>)
            : null,
        window: AttendanceWindow.fromJson(
          (j['window'] as Map?)?.cast<String, dynamic>() ?? const {},
        ),
        canMark: j['can_mark'] as bool? ?? false,
        faceEnrolled: j['face_enrolled'] as bool? ?? false,
      );
}

class AttendanceSummary {
  const AttendanceSummary({
    required this.month,
    required this.present,
    required this.absent,
    required this.outpass,
    required this.ratePercent,
    required this.daysAccounted,
    required this.totalDays,
    required this.passThresholdPercent,
    required this.eligibilitySafe,
  });

  final String month;
  final int present;
  final int absent;
  final int outpass;
  final double ratePercent;
  final int daysAccounted;
  final int totalDays;
  final double passThresholdPercent;
  final bool eligibilitySafe;

  factory AttendanceSummary.fromJson(Map<String, dynamic> j) =>
      AttendanceSummary(
        month: j['month'] as String,
        present: j['present'] as int? ?? 0,
        absent: j['absent'] as int? ?? 0,
        outpass: j['outpass'] as int? ?? 0,
        ratePercent: (j['rate_percent'] as num?)?.toDouble() ?? 0,
        daysAccounted: j['days_accounted'] as int? ?? 0,
        totalDays: j['total_days'] as int? ?? 0,
        passThresholdPercent:
            (j['pass_threshold_percent'] as num?)?.toDouble() ?? 85,
        eligibilitySafe: j['eligibility_safe'] as bool? ?? false,
      );
}

class PagedRecords {
  const PagedRecords({
    required this.items,
    required this.page,
    required this.totalPages,
    required this.hasMore,
  });

  final List<AttendanceRecord> items;
  final int page;
  final int totalPages;
  final bool hasMore;

  factory PagedRecords.fromJson(Map<String, dynamic> j) => PagedRecords(
    items: ((j['items'] as List?) ?? const [])
        .map((e) => AttendanceRecord.fromJson(e as Map<String, dynamic>))
        .toList(),
    page: j['page'] as int? ?? 1,
    totalPages: j['total_pages'] as int? ?? 1,
    hasMore: j['has_more'] as bool? ?? false,
  );
}

class FaceEnrollmentStatus {
  const FaceEnrollmentStatus({
    required this.enrolled,
    this.modelVersion,
    this.updatedAt,
  });

  final bool enrolled;
  final String? modelVersion;
  final String? updatedAt;

  factory FaceEnrollmentStatus.fromJson(Map<String, dynamic> j) =>
      FaceEnrollmentStatus(
        enrolled: j['enrolled'] as bool? ?? false,
        modelVersion: j['model_version'] as String?,
        updatedAt: j['updated_at'] as String?,
      );
}
