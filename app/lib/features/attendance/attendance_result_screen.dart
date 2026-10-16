import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../auth/auth_providers.dart';
import 'scan_flow_controller.dart';
import 'widgets/scan_widgets.dart';

/// Success state of design screen 5 — shown ONLY from a real server response.
class AttendanceResultScreen extends ConsumerWidget {
  const AttendanceResultScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(scanFlowProvider);
    final geofence = ref.watch(geofenceProvider).valueOrNull;
    final student = ref.read(authControllerProvider).student;
    final record = flow.result;

    if (record == null) {
      // Someone landed here without a server-confirmed record.
      return Scaffold(
        appBar: const ScanCheckInAppBar(title: 'Scan Check In'),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  'No verified attendance to show.',
                  style: AppTextStyles.bodyLg,
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () => context.go('/home'),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(200, 48),
                  ),
                  child: const Text('Return Home'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final dateLabel = DateFormat(
      'EEEE, d MMM yyyy',
    ).format(record.recordedAt!.toLocal());

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: const ScanCheckInAppBar(title: 'Scan Check In'),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          child: Column(
            children: [
              // Success mark
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppColors.primaryTint, width: 4),
                ),
                child: const Icon(Icons.check, color: Colors.white, size: 38),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: AppColors.cardHigh,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.textSecondary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'SERVER CONFIRMED',
                      style: AppTextStyles.labelSm.copyWith(
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Attendance Recorded',
                style: AppTextStyles.headlineLg,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 6),
              Text(
                'Your roll call attendance has been verified and recorded on the hostel attendance server.',
                textAlign: TextAlign.center,
                style: AppTextStyles.bodyLg.copyWith(
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 16),

              // Reference card
              SectionCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        MicroLabel('Verification Reference'),
                        StatusBadge(
                          label: record.outcome == 'pending_review'
                              ? 'Pending Review'
                              : 'Recorded',
                          variant: record.outcome == 'pending_review'
                              ? BadgeVariant.pending
                              : BadgeVariant.verified,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      record.reference,
                      style: AppTextStyles.headlineMd.copyWith(
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Student strip
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.cardLow,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          if (student != null)
                            InitialsAvatar(
                              initials: student.initials,
                              size: 44,
                            ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  student?.name ?? '—',
                                  style: AppTextStyles.labelLg,
                                ),
                                Text(
                                  '${student?.studentId ?? ''}'
                                  '${student?.hostel != null ? ' • ${student!.hostel!.label}${student.hostel!.room != null ? ', Room ${student.hostel!.room}' : ''}' : ''}',
                                  style: AppTextStyles.bodySm.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Date / time tiles
                    Row(
                      children: [
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.cardLow,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Date',
                                  style: AppTextStyles.labelMd.copyWith(
                                    color: AppColors.textSecondary,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(dateLabel, style: AppTextStyles.labelLg),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.cardLow,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Time of Check-In',
                                  style: AppTextStyles.labelMd.copyWith(
                                    color: AppColors.textSecondary,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Row(
                                  children: [
                                    Flexible(
                                      child: Text(
                                        record.timeLabel,
                                        style: AppTextStyles.labelLg,
                                      ),
                                    ),
                                    if (record.outcome == 'verified') ...[
                                      const SizedBox(width: 6),
                                      Text(
                                        '(On Time)',
                                        style: AppTextStyles.bodySm.copyWith(
                                          color: AppColors.successText,
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    MicroLabel('Verification Telemetry'),
                    const SizedBox(height: 8),
                    _TelemetryRow(
                      icon: Icons.location_on_outlined,
                      title: 'Campus Geofence',
                      subtitle: record.distanceM != null
                          ? '${record.distanceM!.round()}m inside bounds • GPS ±${record.accuracyM?.round() ?? '?'}m'
                          : 'Verified by server',
                    ),
                    _TelemetryRow(
                      icon: Icons.face_outlined,
                      title: 'Biometric Validation',
                      subtitle:
                          'Face Match ${record.faceSimilarity != null ? '${(record.faceSimilarity! * 100).toStringAsFixed(1)}%' : 'verified'}'
                          '${record.livenessMethod != null ? ' • Liveness ${record.livenessScore != null && record.livenessScore! <= 0.2 ? 'Passed' : 'Passed'}' : ''}',
                    ),
                    _TelemetryRow(
                      icon: Icons.dns_outlined,
                      title: 'Hostel Server Ledger',
                      subtitle:
                          'Recorded ${record.timeLabel} • Ref ${record.reference}',
                      last: true,
                    ),

                    const SizedBox(height: 12),
                    InfoBox(
                      child: Row(
                        children: [
                          const Icon(
                            Icons.qr_code_2,
                            size: 18,
                            color: AppColors.textSecondary,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Security gate QR passes are not enabled for your hostel yet. '
                              'Show your roll number at the gate if needed.',
                              style: AppTextStyles.bodySm.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              FilledButton(
                onPressed: () {
                  ref.read(scanFlowProvider.notifier).reset();
                  ref.invalidate(attendanceStatusProvider);
                  context.go('/home');
                },
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.home_outlined, size: 18),
                    SizedBox(width: 8),
                    Text('Done (Return to Home)'),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () {
                  ref.read(scanFlowProvider.notifier).reset();
                  ref.invalidate(attendanceStatusProvider);
                  context.go('/attendance');
                },
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.history, size: 18),
                    SizedBox(width: 8),
                    Text('View Attendance History'),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              if (geofence?.wardenName != null)
                InfoBox(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.support_agent_outlined,
                        size: 18,
                        color: AppColors.textSecondary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Attendance questions? Contact ${geofence!.wardenName}'
                          '${geofence.wardenExtension != null ? ' at extension #${geofence.wardenExtension}' : ''} '
                          'or visit the warden desk before the curfew window closes.',
                          style: AppTextStyles.bodySm.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TelemetryRow extends StatelessWidget {
  const _TelemetryRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.last = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 10),
      margin: EdgeInsets.only(bottom: last ? 0 : 8),
      decoration: BoxDecoration(
        color: AppColors.cardLow,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: AppColors.primaryTint,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, size: 18, color: AppColors.primaryTintText),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppTextStyles.labelLg),
                Text(
                  subtitle,
                  style: AppTextStyles.bodySm.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const Icon(
            Icons.check_circle_outline,
            size: 20,
            color: AppColors.successText,
          ),
        ],
      ),
    );
  }
}

/// Failure state of design screen 6 — attendance locked outside the zone.
class OutsideZoneScreen extends ConsumerWidget {
  const OutsideZoneScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(scanFlowProvider);
    final geofence = ref.watch(geofenceProvider).valueOrNull;
    final fix = flow.fix;
    final distance = flow.distanceM ?? 0;
    final radius = geofence?.permittedRadiusM ?? 0;
    final deviation = distance > radius ? distance - radius : 0.0;

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: const ScanCheckInAppBar(
        title: 'Scan Check In',
        trailing: SizedBox(width: 32, height: 32),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: AppColors.dangerText,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'ATTENDANCE LOCKOUT',
                        style: AppTextStyles.microLabel(
                          color: AppColors.dangerText,
                        ).copyWith(fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                  GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: AppColors.cardHigh,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.close,
                        size: 20,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: AppColors.dangerBg,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.location_off_outlined,
                  color: AppColors.dangerText,
                  size: 30,
                ),
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  'Outside Hostel Zone',
                  style: AppTextStyles.headlineLg,
                ),
              ),
              const SizedBox(height: 8),
              Text.rich(
                TextSpan(
                  style: AppTextStyles.bodyLg.copyWith(
                    color: AppColors.textSecondary,
                  ),
                  children: [
                    const TextSpan(text: 'You are currently '),
                    TextSpan(
                      text: '${deviation.round()} meters outside',
                      style: const TextStyle(
                        color: AppColors.dangerText,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    TextSpan(
                      text:
                          ' the allowed perimeter for ${geofence?.name ?? 'your hostel'}. '
                          'Attendance can only be recorded while physically present within the block boundary.',
                    ),
                  ],
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),

              // Schematic strip (no third-party map service).
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  height: 150,
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: CustomPaint(
                          painter: GeofenceMapPainter(
                            inside: false,
                            fraction: radius == 0 ? 1 : distance / radius,
                            accuracyFraction:
                                (fix?.accuracyMeters ?? 5) /
                                (radius == 0 ? 120 : radius),
                          ),
                        ),
                      ),
                      Positioned(
                        left: 10,
                        bottom: 10,
                        child: InfoChip(
                          label:
                              'Deviation: +${deviation.round()}m beyond radius',
                          dotColor: AppColors.dangerText,
                        ),
                      ),
                      Positioned(
                        right: 10,
                        bottom: 10,
                        child: InfoChip(
                          label: fix == null ? 'GPS: acquiring' : 'GPS Fix OK',
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Telemetry diagnostics
              SectionCard(
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.podcasts_outlined,
                              size: 16,
                              color: AppColors.textPrimary,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'Telemetry Diagnostics',
                              style: AppTextStyles.labelLg,
                            ),
                          ],
                        ),
                        Text(
                          'LIVE',
                          style: AppTextStyles.labelSm.copyWith(
                            fontWeight: FontWeight.w700,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    const Divider(),
                    _DiagRow(
                      icon: Icons.my_location,
                      label: 'Current Location',
                      value: fix == null
                          ? '—'
                          : '${fix.latitude.toStringAsFixed(4)}° N, ${fix.longitude.toStringAsFixed(4)}° E',
                      sub: fix == null ? null : 'GPS acquired',
                    ),
                    _DiagRow(
                      icon: Icons.apartment_outlined,
                      label: 'Assigned Zone',
                      value: geofence == null
                          ? '—'
                          : '${geofence.name}${geofence.block != null ? ', Block ${geofence.block}' : ''}',
                      sub: geofence == null
                          ? null
                          : 'Curfew: ${geofence.windowEnd}',
                    ),
                    _DiagRow(
                      icon: Icons.straighten,
                      label: 'Boundary Offset',
                      value: '${deviation.round()}m away',
                      valueColor: AppColors.dangerText,
                      sub: 'Max allowed: ${radius.round()}m',
                    ),
                    _DiagRow(
                      icon: Icons.shield_outlined,
                      label: 'Hardware Status',
                      customValue: const StatusBadge(
                        label: 'Camera Locked',
                        variant: BadgeVariant.danger,
                      ),
                    ),
                    _DiagRow(
                      icon: Icons.satellite_alt_outlined,
                      label: 'GPS Accuracy',
                      value: fix == null
                          ? '—'
                          : '±${fix.accuracyMeters.round()}m',
                      sub: fix == null ? null : 'Fix confirmed',
                      last: true,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              InfoBox(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.info_outline,
                      size: 18,
                      color: AppColors.textSecondary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Please return to your hostel block or quadrangle and tap '
                        '“Retry Location Check”. If you hold an approved official outpass or '
                        'hospital emergency slip, submit it to the night warden roll desk.',
                        style: AppTextStyles.bodySm.copyWith(
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              FilledButton(
                onPressed: () {
                  ref.read(scanFlowProvider.notifier).reset();
                  context.pop();
                },
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.refresh, size: 18),
                    SizedBox(width: 8),
                    Text('Retry Location Check'),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => showDialog<void>(
                  context: context,
                  builder: (context) => AlertDialog(
                    backgroundColor: AppColors.card,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    title: Text(
                      'Outpass requests',
                      style: AppTextStyles.headlineSm,
                    ),
                    content: Text(
                      'Online outpass and emergency-slip submission is not available in this version '
                      'of HostelPass yet. Please submit your approved slip to the night warden roll '
                      'desk in person.',
                      style: AppTextStyles.bodyMd.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('Close'),
                      ),
                    ],
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.description_outlined, size: 18),
                    SizedBox(width: 8),
                    Text('Submit Outpass / Emergency Slip'),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DiagRow extends StatelessWidget {
  const _DiagRow({
    required this.icon,
    required this.label,
    this.value,
    this.valueColor,
    this.sub,
    this.customValue,
    this.last = false,
  });

  final IconData icon;
  final String label;
  final String? value;
  final Color? valueColor;
  final String? sub;
  final Widget? customValue;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: last
            ? null
            : const Border(bottom: BorderSide(color: AppColors.hairline)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 17, color: AppColors.textSecondary),
          const SizedBox(width: 10),
          Expanded(child: Text(label, style: AppTextStyles.bodyMd)),
          if (customValue != null)
            customValue!
          else
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  value ?? '—',
                  style: AppTextStyles.labelLg.copyWith(
                    color: valueColor ?? AppColors.textPrimary,
                    fontFeatures: const [ui.FontFeature.tabularFigures()],
                  ),
                ),
                if (sub != null)
                  Text(
                    sub!,
                    style: AppTextStyles.bodySm.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}
