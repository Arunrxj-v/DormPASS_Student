import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../attendance/attendance_models.dart';
import '../attendance/scan_flow_controller.dart';
import '../auth/auth_providers.dart';

/// Small header lockup + bell + avatar shared by the three main tabs.
class AppHeader extends ConsumerWidget {
  const AppHeader({super.key, required this.title});

  final String title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final student = ref.watch(authControllerProvider).student;
    // The shell places this header at the very top of its Column, above the
    // screen's own SafeArea, so it has to claim the status-bar inset itself —
    // otherwise the initials avatar renders underneath the system clock.
    return SafeArea(
      bottom: false,
      child: Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.hairline)),
      ),
      child: Row(
        children: [
          const HostelPassLogo(height: 26),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'HOSTELPASS',
                  style: AppTextStyles.labelSm.copyWith(
                    color: AppColors.textSecondary,
                    letterSpacing: 1,
                  ),
                ),
                Text(
                  title,
                  style: AppTextStyles.headlineSm.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Notifications',
            onPressed: () => showDialog<void>(
              context: context,
              builder: (context) => AlertDialog(
                backgroundColor: AppColors.card,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                title: Text('Notifications', style: AppTextStyles.headlineSm),
                content: Text(
                  'No new alerts.\n\nPush notifications are not enabled in this version of '
                  'HostelPass — check your home screen for tonight’s roll-call status.',
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
            icon: const Icon(
              Icons.notifications_outlined,
              size: 22,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(width: 4),
          if (student != null)
            GestureDetector(
              onTap: () => context.go('/profile'),
              child: InitialsAvatar(initials: student.initials, size: 32),
            ),
        ],
      ),
      ),
    );
  }
}

final _recentRecordsProvider = FutureProvider<PagedRecords>(
  (ref) => ref.watch(attendanceRepositoryProvider).history(pageSize: 3),
);

/// Home / attendance status (Stitch screen 2).
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(attendanceStatusProvider);
    final geofenceAsync = ref.watch(geofenceProvider);
    final enrollmentAsync = ref.watch(faceEnrollmentProvider);
    final recentAsync = ref.watch(_recentRecordsProvider);
    final student = ref.watch(authControllerProvider).student;

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        bottom: false,
        child: statusAsync.when(
          loading: () => const LoadingView(label: 'Loading attendance status…'),
          error: (e, _) => _ErrorBody(
            error: e,
            onRetry: () => ref.invalidate(attendanceStatusProvider),
          ),
          data: (status) {
            final geofence = geofenceAsync.valueOrNull;
            final enrollment = enrollmentAsync.valueOrNull;
            final records =
                recentAsync.valueOrNull?.items ?? const <AttendanceRecord>[];

            return RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(attendanceStatusProvider);
                ref.invalidate(geofenceProvider);
                ref.invalidate(faceEnrollmentProvider);
                ref.invalidate(_recentRecordsProvider);
              },
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
                children: [
                  // ---- Student strip ----
                  SectionCard(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        if (student != null)
                          InitialsAvatar(initials: student.initials, size: 48),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${_greeting()}, ${student?.name ?? ''}',
                                style: AppTextStyles.headlineSm,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 2),
                              Text.rich(
                                TextSpan(
                                  style: AppTextStyles.labelSm.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
                                  children: [
                                    const TextSpan(text: 'Roll No: '),
                                    TextSpan(
                                      text: student?.studentId ?? '—',
                                      style: const TextStyle(
                                        color: AppColors.textPrimary,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              if (student?.hostel != null)
                                Text(
                                  '${student!.hostel!.label}${student.hostel!.room != null ? ' • Room ${student.hostel!.room}' : ''}',
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

                  // ---- Curfew window banner ----
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.bannerBg,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.timer_outlined,
                          size: 22,
                          color: AppColors.bannerText,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Flexible(
                                    child: Text(
                                      'EVENING ROLL CALL WINDOW',
                                      style: AppTextStyles.labelMd.copyWith(
                                        color: AppColors.bannerTextStrong,
                                        letterSpacing: 0.5,
                                      ),
                                    ),
                                  ),
                                  if (status.window.open &&
                                      status.window.minutesRemaining != null)
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 6,
                                        vertical: 2,
                                      ),
                                      decoration: BoxDecoration(
                                        color: AppColors.bannerText.withValues(
                                          alpha: 0.1,
                                        ),
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: Text(
                                        '${status.window.minutesRemaining} mins left',
                                        style: AppTextStyles.labelSm.copyWith(
                                          color: AppColors.bannerText,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${_fmt12(status.window.opensAt)} – ${_fmt12(status.window.closesAt)} • '
                                'Attendance gate is currently ${status.window.open ? 'open' : 'closed'}',
                                style: AppTextStyles.bodySm.copyWith(
                                  color: AppColors.bannerText,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // ---- Today's attendance card ----
                  SectionCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                "TODAY'S ATTENDANCE • ${DateFormat('EEE, d MMM yyyy').format(DateTime.now()).toUpperCase()}",
                                style: AppTextStyles.microLabel(),
                              ),
                            ),
                            if (status.marked)
                              StatusBadge(
                                label: status.outcome == 'pending_review'
                                    ? 'Pending'
                                    : 'Verified',
                                variant: status.outcome == 'pending_review'
                                    ? BadgeVariant.pending
                                    : BadgeVariant.verified,
                              )
                            else
                              const StatusBadge(
                                label: 'Not Marked',
                                variant: BadgeVariant.danger,
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          status.marked
                              ? (status.outcome == 'pending_review'
                                    ? 'Attendance Pending Review'
                                    : 'Attendance Marked')
                              : (status.window.open
                                    ? 'Night Roll Call Pending'
                                    : 'Roll Call Window Closed'),
                          style: AppTextStyles.headlineMd,
                        ),
                        const SizedBox(height: 6),
                        Text(
                          status.marked
                              ? (status.outcome == 'pending_review'
                                    ? 'Your check-in was recorded and is awaiting warden confirmation.'
                                    : 'You are marked present for tonight’s roll call. Reference ${status.record?.reference ?? ''}.')
                              : (status.window.open
                                    ? 'Attendance hasn’t been recorded yet for tonight’s roll call. Verify your identity within the designated zone.'
                                    : 'The attendance window (${status.window.opensAt}–${status.window.closesAt} ${status.window.timezone}) is closed. '
                                          'Contact the night warden if you have an approved late pass.'),
                          style: AppTextStyles.bodyMd.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 14),
                        FilledButton(
                          onPressed: status.canMark
                              ? () {
                                  ref.read(scanFlowProvider.notifier).reset();
                                  context.push('/attendance/location');
                                }
                              : null,
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.badge_outlined, size: 20),
                              SizedBox(width: 8),
                              Text('Mark Attendance Now'),
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),

                        // Pre-check diagnostics
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.cardLow,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  MicroLabel('Pre-check system diagnostics'),
                                  Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const Icon(
                                        Icons.sync,
                                        size: 13,
                                        color: AppColors.textSecondary,
                                      ),
                                      const SizedBox(width: 4),
                                      Text(
                                        'Live',
                                        style: AppTextStyles.labelSm.copyWith(
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              _DiagTile(
                                icon: Icons.location_searching_outlined,
                                title: 'Hostel Geofence',
                                subtitle: geofence == null
                                    ? 'Loading zone configuration…'
                                    : status.marked &&
                                          status.record?.distanceM != null
                                    ? 'Inside radius (${status.record!.distanceM!.round()}m from anchor)'
                                    : 'Zone: ${geofence.anchorLabel} • Radius ${geofence.permittedRadiusM.round()}m — verified at check-in',
                              ),
                              _DiagTile(
                                icon: Icons.face_outlined,
                                title: 'Face Biometrics',
                                subtitle: enrollment == null
                                    ? 'Checking enrollment…'
                                    : enrollment.enrolled
                                    ? 'Face template active (${enrollment.modelVersion ?? 'v1'})'
                                    : 'Not enrolled yet — ask your hostel warden to enroll you',
                              ),
                              _DiagTile(
                                icon: Icons.cloud_upload_outlined,
                                title: 'Record Transmission',
                                subtitle: status.marked
                                    ? 'Attendance recorded on server (${status.record?.reference ?? ''})'
                                    : 'Pending — the hostel server confirms every submission',
                                last: true,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),

                        Row(
                          children: [
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: AppColors.cardLow,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(
                                          Icons.outlined_flag,
                                          size: 13,
                                          color: AppColors.textSecondary,
                                        ),
                                        const SizedBox(width: 4),
                                        Text(
                                          'Allowed Zone',
                                          style: AppTextStyles.labelSm.copyWith(
                                            color: AppColors.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      geofence?.anchorLabel ?? '—',
                                      style: AppTextStyles.labelLg,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    Text(
                                      'Radius: ${geofence?.permittedRadiusM.round() ?? '—'}m',
                                      style: AppTextStyles.bodySm.copyWith(
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: AppColors.cardLow,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(
                                          Icons.shield_outlined,
                                          size: 13,
                                          color: AppColors.textSecondary,
                                        ),
                                        const SizedBox(width: 4),
                                        Text(
                                          'Method',
                                          style: AppTextStyles.labelSm.copyWith(
                                            color: AppColors.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      'Dual Biometric',
                                      style: AppTextStyles.labelLg,
                                    ),
                                    Text(
                                      'GPS + Face Match',
                                      style: AppTextStyles.bodySm.copyWith(
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // ---- Recent roll calls ----
                  SectionCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Recent Roll Calls',
                              style: AppTextStyles.headlineSm,
                            ),
                            GestureDetector(
                              onTap: () => context.go('/attendance'),
                              child: Text(
                                'View Log History',
                                style: AppTextStyles.labelLg.copyWith(
                                  color: AppColors.primary,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        if (recentAsync.isLoading)
                          const Center(
                            child: Padding(
                              padding: EdgeInsets.all(8),
                              child: SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              ),
                            ),
                          )
                        else if (records.isEmpty)
                          Text(
                            'No roll calls recorded yet.',
                            style: AppTextStyles.bodySm.copyWith(
                              color: AppColors.textSecondary,
                            ),
                          )
                        else
                          ...records.take(2).map((r) => _RecentRow(record: r)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // ---- Warden contact ----
                  if (geofence != null && geofence.wardenName != null)
                    InfoBox(
                      child: Row(
                        children: [
                          const Icon(
                            Icons.support_agent_outlined,
                            size: 20,
                            color: AppColors.textPrimary,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Need an exception or leave pass?',
                                  style: AppTextStyles.labelLg,
                                ),
                                Text(
                                  'Night Warden: ${geofence.wardenName}${geofence.wardenExtension != null ? ' (Ext. ${geofence.wardenExtension})' : ''}',
                                  style: AppTextStyles.bodySm.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.card,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: AppColors.hairline),
                            ),
                            child: Text(
                              'Contact',
                              style: AppTextStyles.labelLg,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static String _fmt12(String hhmm) {
    final m = RegExp(r'^(\d{2}):(\d{2})').firstMatch(hhmm);
    if (m == null) return hhmm;
    var h = int.parse(m.group(1)!);
    final suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12 == 0 ? 12 : h % 12;
    return '${h.toString().padLeft(2, '0')}:${m.group(2)!} $suffix';
  }
}

class _DiagTile extends StatelessWidget {
  const _DiagTile({
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
      margin: EdgeInsets.only(bottom: last ? 0 : 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: AppColors.textSecondary),
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
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RecentRow extends StatelessWidget {
  const _RecentRow({required this.record});

  final AttendanceRecord record;

  @override
  Widget build(BuildContext context) {
    final day = record.recordedAt != null
        ? DateFormat('EEE, d MMM').format(record.recordedAt!.toLocal())
        : record.date;
    final (badge, variant) = record.isPresent
        ? ('Verified', BadgeVariant.verified)
        : record.isPending
        ? ('Pending', BadgeVariant.pending)
        : ('Missed', BadgeVariant.danger);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
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
              color: AppColors.cardHighest,
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(
              Icons.calendar_month_outlined,
              size: 17,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(day, style: AppTextStyles.labelLg),
                Text(
                  record.isPresent || record.isPending
                      ? 'Marked at ${record.timeLabel} • ${record.isPending ? 'Awaiting review' : 'On-Time'}'
                      : (record.reason == 'curfew_window_missed'
                            ? 'Curfew window missed'
                            : 'No record'),
                  style: AppTextStyles.bodySm.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          StatusBadge(label: badge, variant: variant, dense: true),
        ],
      ),
    );
  }
}

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final message = error is AppException
        ? (error as AppException).displayMessage
        : 'Could not load your attendance status.';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [ErrorBar(message: message, onRetry: onRetry)],
        ),
      ),
    );
  }
}
