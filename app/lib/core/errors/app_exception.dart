import 'package:flutter/material.dart';

/// Every failure the app can present, as a typed code + user message.
/// Codes 1:1 with the backend contract (docs/API.md); client-only codes are
/// prefixed `local_`.
class AppException implements Exception {
  const AppException(this.code, {this.message, this.details = const {}});

  /// Machine-readable code, e.g. `outside_geofence`.
  final String code;

  /// Server-provided message if available.
  final String? message;

  /// Extra structured data (distance_m, similarity, ...).
  final Map<String, dynamic> details;

  bool get isAuthExpired => code == 'token_invalid' || code == 'token_revoked';

  /// User-facing message.
  ///
  /// The server's message wins whenever one came back: it is written against
  /// the failure that actually happened (e.g. a Google sign-in rejection
  /// should not read like a password typo). The client table is the fallback
  /// for codes the server sent no text for — all `local_*` codes, plus any
  /// transport-level failure.
  String get displayMessage =>
      message ??
      localizedMessage(code) ??
      'Something went wrong. Please try again.';

  static String? localizedMessage(String code) {
    switch (code) {
      // --- Client-side (location) ---
      case 'local_location_permission_denied':
        return 'Location permission was denied. HostelPass needs your location once per check-in to confirm you are inside the hostel zone.';
      case 'local_location_permission_denied_forever':
        return 'Location access is blocked for HostelPass. Enable it in Android settings → Apps → HostelPass → Permissions → Location.';
      case 'local_location_services_disabled':
        return 'Location services (GPS) are turned off. Enable them in the quick settings panel and try again.';
      case 'local_location_timeout':
        return 'Could not get a GPS fix in time. Move away from buildings or step briefly outdoors, then retry.';
      case 'local_location_unusable':
        return 'The location reading is too imprecise to verify the hostel zone. Wait a moment for a stronger GPS lock and retry.';
      // --- Server-side (attendance) ---
      case 'location_stale':
        return 'Your location reading was taken too long ago. Tap retry to get a fresh GPS fix.';
      case 'location_unusable':
        return 'Your GPS accuracy is too low to verify the hostel zone. Retry with a clearer view of the sky.';
      case 'outside_geofence':
        return 'You are outside the permitted hostel zone. Attendance can only be marked inside your hostel boundary.';
      case 'attendance_window_closed':
        return 'The attendance window is closed right now. Check the roll-call times on your home screen.';
      case 'duplicate_attendance':
        return 'Attendance is already recorded for today. Nothing more to do — you are marked present.';
      case 'face_not_enrolled':
        return 'Your face is not enrolled yet. Ask your hostel warden to enroll you at the hostel office before marking attendance.';
      case 'face_mismatch':
        return 'Face did not match your enrolled identity. Retry with your face clearly visible and well lit.';
      case 'liveness_failed':
        return 'Liveness check failed. The camera must see you directly — photos, screens and masks are rejected.';
      // --- Auth ---
      case 'invalid_credentials':
        return 'Incorrect email or roll number, or password. Try again.';
      case 'token_invalid':
      case 'token_revoked':
        return 'Your session expired. Please sign in again.';
      case 'account_inactive':
        return 'Your hostel account is inactive. Contact the hostel office.';
      case 'hostel_not_configured':
        return 'Your hostel has no attendance zone configured yet. Contact the hostel office.';
      // --- Transport ---
      case 'local_network_unavailable':
        return 'No internet connection. Attendance cannot be recorded offline — it will work once you are back online.';
      case 'local_server_unreachable':
        return 'Cannot reach the hostel server right now. Attendance is NOT recorded until the server confirms it. Try again shortly.';
      case 'rate_limited':
        return 'Too many attempts. Please wait a minute before trying again.';
      case 'forbidden':
        return 'You do not have permission for this action.';
      case 'not_found':
        return 'That item could not be found.';
      // --- Camera (client) ---
      case 'local_camera_permission_denied':
        return 'Camera permission is required for face verification. Enable it in app settings.';
      case 'local_no_face':
        return 'No face detected. Position your face inside the oval.';
      case 'local_multiple_faces':
        return 'More than one face detected. Only the enrolled student may be in frame.';
      case 'local_face_occluded':
        return 'Face not clear enough. Remove obstructions, look straight at the camera.';
      case 'local_low_light':
        return 'Lighting is too poor for verification. Face a light source and retry.';
      default:
        return null;
    }
  }

  @override
  String toString() => 'AppException($code, $details)';
}

/// Shows a compact, design-system-styled error bar. Reused across screens.
class ErrorBar extends StatelessWidget {
  const ErrorBar({
    super.key,
    required this.message,
    this.onRetry,
    this.icon = Icons.error_outline,
  });

  final String message;
  final VoidCallback? onRetry;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFDAD6),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: const Color(0xFF93000A)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                fontFamily: 'Inter',
                fontSize: 13,
                height: 18 / 13,
                color: Color(0xFF93000A),
              ),
            ),
          ),
          if (onRetry != null)
            GestureDetector(
              onTap: onRetry,
              child: const Padding(
                padding: EdgeInsets.only(left: 8, top: 1),
                child: Text(
                  'Retry',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF93000A),
                    decoration: TextDecoration.underline,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
