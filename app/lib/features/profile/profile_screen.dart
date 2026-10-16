import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config/env.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../attendance/scan_flow_controller.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart' show Student;
import '../warden/warden_providers.dart';

/// Profile & settings (Stitch screen 8) — the "Profile" tab.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  void _dialog(BuildContext context, String title, String body) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        title: Text(title, style: AppTextStyles.headlineSm),
        content: Text(
          body,
          style: AppTextStyles.bodyMd.copyWith(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  /// Warden/admin profile — no student attendance, biometrics or curfew rows.
  Widget _buildStaff(BuildContext context, WidgetRef ref, Student staff) {
    final hostelsAsync = ref.watch(wardenHostelsProvider);

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            SectionCard(
              child: Column(
                children: [
                  InitialsAvatar(initials: staff.initials, size: 84, radius: 12),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(staff.name, style: AppTextStyles.headlineMd),
                      const SizedBox(width: 8),
                      StatusBadge(
                        label: staff.role == 'admin'
                            ? 'Administrator'
                            : 'Warden',
                        variant: BadgeVariant.tint,
                        dense: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'ACCOUNT: ${staff.studentId.toUpperCase()}',
                    style: AppTextStyles.labelSm.copyWith(
                      color: AppColors.textSecondary,
                      letterSpacing: 1,
                    ),
                  ),
                  const SizedBox(height: 12),
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
                        _InfoLine(label: 'Role', value: staff.role.toUpperCase()),
                        _InfoLine(
                          label: 'Account status',
                          value: staff.accountStatus,
                        ),
                        if (staff.email != null)
                          _InfoLine(label: 'Email', value: staff.email!),
                        const SizedBox(height: 6),
                        Text(
                          'Access scope',
                          style: AppTextStyles.labelMd.copyWith(
                            color: AppColors.textSecondary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        hostelsAsync.when(
                          loading: () => Text(
                            'Loading assigned hostels…',
                            style: AppTextStyles.labelLg,
                          ),
                          error: (e, _) => Text(
                            'Could not load hostel assignments.',
                            style: AppTextStyles.labelLg,
                          ),
                          data: (hostels) => Text(
                            staff.role == 'admin'
                                ? 'All hostels (administrator)'
                                : hostels.isEmpty
                                ? 'No hostels assigned — ask an administrator'
                                : hostels.map((h) => h.label).join('\n'),
                            style: AppTextStyles.labelLg,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            MicroLabel('Your Work'),
            const SizedBox(height: 8),
            SectionCard(
              padding: const EdgeInsets.all(0),
              child: Column(
                children: [
                  _LinkRow(
                    icon: Icons.dashboard_outlined,
                    title: 'Dashboard',
                    subtitle: 'Roster counts, enrollment activity, tonight\'s attendance',
                    onTap: () => context.go('/warden/dashboard'),
                  ),
                  _LinkRow(
                    icon: Icons.groups_outlined,
                    title: 'Students',
                    subtitle: 'Search, create, enroll faces, issue activation links',
                    onTap: () => context.go('/warden/students'),
                  ),
                  // Administrators only: the tier above wardens, where the
                  // accounts this screen's users come from are created.
                  if (staff.isAdmin)
                    _LinkRow(
                      icon: Icons.admin_panel_settings_outlined,
                      title: 'Admin Console',
                      subtitle: 'Create warden accounts, assign hostels, '
                          'activate or deactivate wardens',
                      onTap: () => context.push('/admin/wardens'),
                    ),
                  _LinkRow(
                    icon: Icons.face_retouching_natural_outlined,
                    title: 'Face Enrollment',
                    subtitle: 'Performed here, on the student\'s record — '
                        'students cannot enroll themselves',
                    onTap: () => context.go('/warden/students'),
                  ),
                  _LinkRow(
                    icon: Icons.privacy_tip_outlined,
                    title: 'Privacy & Audit',
                    subtitle: 'What staff actions are recorded',
                    onTap: () => _dialog(
                      context,
                      'Privacy & Audit',
                      'Every sensitive staff action — creating or editing a '
                          'student, enrolling or deleting a face template, '
                          'issuing an activation link, suspending or restoring '
                          'an account — is written to the audit log with your '
                          'account and the affected student.\n\n'
                          'Passwords, activation tokens and biometric templates '
                          'are never recorded there, and raw camera frames are '
                          'never stored on either side.',
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            OutlinedButton(
              onPressed: () async {
                await ref.read(authControllerProvider.notifier).signOut();
                if (context.mounted) context.go('/signin');
              },
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.dangerText,
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.logout, size: 18),
                  SizedBox(width: 8),
                  Text('Sign Out of Device'),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(
                'HostelPass v${Env.appVersion}',
                style: AppTextStyles.bodySm.copyWith(
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final student = ref.watch(authControllerProvider).student;

    // Staff get a different profile: attendance stats, the biometric card and
    // the student's curfew/outpass rows all describe a student account. Only
    // the auth state is read before this branch, so a warden never fires the
    // student-only /hostels/me/geofence or /face-enrollment calls either.
    if (student != null && student.isWarden) {
      return _buildStaff(context, ref, student);
    }

    final geofence = ref.watch(geofenceProvider).valueOrNull;
    final enrollmentAsync = ref.watch(faceEnrollmentProvider);
    final enrollment = enrollmentAsync.valueOrNull;

    final warden = geofence?.wardenName;
    final wardenExt = geofence?.wardenExtension;
    final wardenSubtitle = warden == null
        ? 'Block Warden & Hostel Office lines'
        : 'Block Warden: $warden';
    final wardenBody = warden == null
        ? 'Directory unavailable.'
        : 'Night Warden: $warden${wardenExt != null ? ' (Ext. $wardenExt)' : ''}\n'
              'Hostel Office: visit Block C during working hours.';

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            // ---- Identity card ----
            SectionCard(
              child: Column(
                children: [
                  if (student != null)
                    InitialsAvatar(
                      initials: student.initials,
                      size: 84,
                      radius: 12,
                    ),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        student?.name ?? '—',
                        style: AppTextStyles.headlineMd,
                      ),
                      const SizedBox(width: 8),
                      StatusBadge(
                        label: student?.accountStatus == 'active'
                            ? 'Verified'
                            : student?.accountStatus ?? 'Unknown',
                        variant: student?.accountStatus == 'active'
                            ? BadgeVariant.tint
                            : BadgeVariant.pending,
                        dense: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'ROLL NO: ${student?.studentId ?? '—'}',
                    style: AppTextStyles.labelSm.copyWith(
                      color: AppColors.textSecondary,
                      letterSpacing: 1,
                    ),
                  ),
                  const SizedBox(height: 12),
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
                        _InfoLine(
                          label: 'Department',
                          value: student?.department ?? '—',
                        ),
                        _InfoLine(
                          label: 'Cohort',
                          value: student?.cohort ?? '—',
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Hostel Residence',
                          style: AppTextStyles.labelMd.copyWith(
                            color: AppColors.textSecondary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        Text(
                          student?.hostel == null
                              ? 'Not assigned'
                              : '${student!.hostel!.label}${student.hostel!.room != null ? ' • Room ${student.hostel!.room}' : ''}',
                          style: AppTextStyles.labelLg,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // ---- Device & biometric compliance ----
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                MicroLabel('Device & Biometric Compliance'),
                const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.verified_user_outlined,
                      size: 14,
                      color: AppColors.primary,
                    ),
                    SizedBox(width: 4),
                    Text(
                      'SECURE',
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: AppColors.primary,
                        letterSpacing: 0.8,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 8),
            SectionCard(
              child: Column(
                children: [
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: AppColors.cardLow,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.face_outlined,
                          size: 20,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Biometric Registration',
                              style: AppTextStyles.labelLg,
                            ),
                            Text(
                              enrollment == null
                                  ? 'Checking enrollment…'
                                  : enrollment.enrolled
                                  ? 'Face template active • updated ${enrollment.updatedAt?.substring(0, 10) ?? ''}'
                                  : 'Not enrolled yet',
                              style: AppTextStyles.bodySm.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (enrollment?.enrolled == true)
                        const StatusBadge(
                          label: 'Active',
                          variant: BadgeVariant.verified,
                        )
                      else if (enrollment != null)
                        const StatusBadge(
                          label: 'Required',
                          variant: BadgeVariant.pending,
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Divider(),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: AppColors.cardLow,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.smartphone,
                          size: 20,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('This Device', style: AppTextStyles.labelLg),
                            Text(
                              'Attendance is bound to your account, not this handset — '
                              'signing in elsewhere re-verifies your identity.',
                              style: AppTextStyles.bodySm.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // ---- Institutional controls ----
            MicroLabel('Institutional Controls & Records'),
            const SizedBox(height: 8),
            SectionCard(
              padding: const EdgeInsets.all(0),
              child: Column(
                children: [
                  _LinkRow(
                    icon: Icons.schedule_outlined,
                    title: 'Night Curfew & Roll Call',
                    subtitle: geofence == null
                        ? 'Loading schedule…'
                        : 'Attendance window: ${geofence.windowStart} – ${geofence.windowEnd} ${geofence.timezone}',
                    onTap: () => _dialog(
                      context,
                      'Night Curfew & Roll Call',
                      geofence == null
                          ? 'Schedule unavailable right now.'
                          : 'Attendance window: ${geofence.windowStart} – ${geofence.windowEnd} (${geofence.timezone}).\n\n'
                                'Mark attendance from the Home tab while inside ${geofence.anchorLabel}.',
                    ),
                  ),
                  _LinkRow(
                    icon: Icons.logout,
                    title: 'Hostel Outpass & Leave',
                    subtitle: 'Submit overnight gate pass requests',
                    onTap: () => _dialog(
                      context,
                      'Outpass & Leave',
                      'Online outpass requests are not available in this version yet. '
                          'Submit overnight gate pass requests at the warden office, Block C.',
                    ),
                  ),
                  _LinkRow(
                    icon: Icons.contact_page_outlined,
                    title: 'Emergency Directory',
                    subtitle: wardenSubtitle,
                    onTap: () =>
                        _dialog(context, 'Emergency Directory', wardenBody),
                  ),
                  _LinkRow(
                    icon: Icons.face_retouching_natural_outlined,
                    title: 'Face Template Status',
                    subtitle: enrollment?.enrolled == true
                        ? 'Enrolled — managed by your hostel warden'
                        : 'Not enrolled yet — ask your warden',
                    onTap: () => _dialog(
                      context,
                      'Face Template Status',
                      enrollment?.enrolled == true
                          ? 'Your face template is enrolled and was last updated '
                              '${enrollment!.updatedAt ?? 'earlier'}.\n\n'
                              'Only your hostel warden can replace or delete it. '
                              'Ask the hostel office if your appearance has changed '
                              'markedly (haircut, new glasses, facial hair) so they '
                              'can re-enroll you.'
                          : 'You do not have a face template on file yet, so '
                              'attendance cannot be verified.\n\n'
                              'Visit the hostel office — your warden submits your '
                              'details and enrolls your face. This cannot be done '
                              'from the app.',
                    ),
                  ),
                  _LinkRow(
                    icon: Icons.privacy_tip_outlined,
                    title: 'Privacy & Data Retention',
                    subtitle: 'What HostelPass stores — and what it does not',
                    onTap: () => _dialog(
                      context,
                      'Privacy & Data Retention',
                      'HostelPass stores your name, roll number, hostel assignment, attendance '
                          'records and an encrypted face template used only for check-in verification.\n\n'
                          'Raw camera photos are never uploaded or stored. Location is requested only '
                          'during check-in — never in the background. You cannot delete your own face '
                          'template from the app: ask the hostel office and your warden will delete or '
                          'replace it, which is recorded in the audit log.',
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            OutlinedButton(
              onPressed: () async {
                await ref.read(authControllerProvider.notifier).signOut();
                if (context.mounted) context.go('/signin');
              },
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.dangerText,
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.logout, size: 18),
                  SizedBox(width: 8),
                  Text('Sign Out of Device'),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Column(
                children: [
                  Text(
                    'HostelPass v${Env.appVersion}',
                    style: AppTextStyles.bodySm.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                  Text(
                    'Developed for institutional hostel administration',
                    style: AppTextStyles.bodySm.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.lock_outline,
                        size: 12,
                        color: AppColors.textDisabled,
                      ),
                      SizedBox(width: 4),
                      Text(
                        'Institutional Security Level 3',
                        style: TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 11,
                          color: AppColors.textDisabled,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 110,
          child: Text(
            label,
            style: AppTextStyles.labelMd.copyWith(
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        Expanded(child: Text(value, style: AppTextStyles.labelLg)),
      ],
    ),
  );
}

class _LinkRow extends StatelessWidget {
  const _LinkRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: AppColors.hairline)),
        ),
        child: Row(
          children: [
            Icon(icon, size: 20, color: AppColors.primary),
            const SizedBox(width: 12),
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
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right,
              size: 20,
              color: AppColors.textSecondary,
            ),
          ],
        ),
      ),
    );
  }
}
