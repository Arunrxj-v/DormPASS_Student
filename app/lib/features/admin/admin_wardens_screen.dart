import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../warden/enrollment_status_ui.dart' show formatActivityTime;
import '../warden/warden_models.dart';
import '../warden/warden_providers.dart';
import 'admin_models.dart';
import 'admin_providers.dart';

/// Admin console — warden provisioning and hostel assignment.
///
/// This is the top of the provisioning hierarchy: wardens exist only because
/// an administrator created them here, and the hostel grants chosen on this
/// screen are exactly what `GET /warden/students` scopes a warden's roster to.
///
/// The client-side role check in the router only decides whether this screen
/// is reachable in the UI. Every request below is still authorized by FastAPI's
/// router-level `require_admin` — a warden session calling these endpoints
/// receives 403 whether or not the button exists.
class AdminWardensScreen extends ConsumerStatefulWidget {
  const AdminWardensScreen({super.key});

  @override
  ConsumerState<AdminWardensScreen> createState() =>
      _AdminWardensScreenState();
}

class _AdminWardensScreenState extends ConsumerState<AdminWardensScreen> {
  /// Serializes mutations so two taps cannot race a PATCH against a DELETE.
  bool _busy = false;

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  String _describe(Object error) => error is AppException
      ? error.displayMessage
      : 'The request could not be completed. Check your connection and try again.';

  /// Runs one server mutation, surfacing a failure as a snackbar.
  Future<void> _mutate(
    Future<void> Function() body, {
    String? genericFailure,
  }) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await body();
    } on AppException catch (e) {
      _snack(e.displayMessage);
    } catch (_) {
      _snack(genericFailure ?? _describe(Object()));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _refresh() => ref.invalidate(adminWardensProvider);

  // ------------------------------------------------------------- actions

  Future<void> _toggleStatus(AdminWarden w) async {
    final deactivating = w.isActive;
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: AppColors.card,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            title: Text(deactivating ? 'Deactivate warden?' : 'Activate warden?'),
            content: Text(
              deactivating
                  ? '${w.username} will be signed out and unable to sign in. '
                      'Their hostel grants are kept, so they can be reactivated '
                      'at any time. Student records are not affected.'
                  : '${w.username} will be able to sign in and manage '
                      'the hostels currently assigned to them.',
              style: AppTextStyles.bodyMd.copyWith(
                color: AppColors.textSecondary,
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(ctx).pop(true),
                child: Text(deactivating ? 'Deactivate' : 'Activate'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed) return;

    await _mutate(() async {
      await ref
          .read(adminRepositoryProvider)
          .patchWarden(
            w.username,
            accountStatus: deactivating ? 'inactive' : 'active',
          );
      _refresh();
      _snack(
        deactivating
            ? '${w.username} deactivated — they can no longer sign in.'
            : '${w.username} activated.',
      );
    }, genericFailure: 'Could not change the account status.');
  }

  Future<void> _assignHostels(
    AdminWarden w,
    List<WardenHostel> hostels,
  ) async {
    if (hostels.isEmpty) {
      _snack('No hostels are configured yet, so no assignment can be made.');
      return;
    }
    final selected = Set<String>.from(w.hostelIds);

    final saved =
        await showModalBottomSheet<bool>(
          context: context,
          backgroundColor: AppColors.card,
          isScrollControlled: true,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
          ),
          builder: (ctx) => StatefulBuilder(
            builder: (ctx, setSheet) => SafeArea(
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(ctx).size.height * 0.75,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 18, 8, 4),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Hostel assignment',
                                  style: AppTextStyles.headlineSm,
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Which hostels may ${w.username} manage?',
                                  style: AppTextStyles.bodySm.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            tooltip: 'Close',
                            onPressed: () => Navigator.of(ctx).pop(false),
                            icon: const Icon(Icons.close, size: 22),
                          ),
                        ],
                      ),
                    ),
                    Flexible(
                      child: ListView(
                        shrinkWrap: true,
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        children: [
                          for (final h in hostels)
                            CheckboxListTile(
                              value: selected.contains(h.id),
                              controlAffinity:
                                  ListTileControlAffinity.leading,
                              activeColor: AppColors.primary,
                              title: Text(h.label, style: AppTextStyles.bodyMd),
                              subtitle: selected.contains(h.id)
                                  ? null
                                  : Text(
                                      'No access',
                                      style: AppTextStyles.bodySm.copyWith(
                                        color: AppColors.textDisabled,
                                      ),
                                    ),
                              onChanged: (v) => setSheet(() {
                                if (v == true) {
                                  selected.add(h.id);
                                } else {
                                  selected.remove(h.id);
                                }
                              }),
                            ),
                        ],
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                      child: FilledButton(
                        onPressed: () => Navigator.of(ctx).pop(true),
                        child: Text(
                          selected.isEmpty
                              ? 'Save (no hostels)'
                              : 'Save ${selected.length} assignment'
                                    '${selected.length == 1 ? '' : 's'}',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ) ??
        false;
    if (!saved) return;

    await _mutate(() async {
      await ref
          .read(adminRepositoryProvider)
          .patchWarden(w.username, hostelIds: selected.toList());
      _refresh();
      if (selected.isEmpty) {
        _snack(
          '${w.username} now has no hostel assignment — they will see an '
          'empty roster.',
        );
      } else {
        _snack('Hostel assignment updated for ${w.username}.');
      }
    }, genericFailure: 'Could not save the hostel assignment.');
  }

  Future<void> _resetPassword(AdminWarden w) async {
    final next = TextEditingController();
    final repeat = TextEditingController();
    try {
      final password =
          await showDialog<String>(
            context: context,
            builder: (ctx) => _PasswordDialog(
              title: 'Reset password',
              subtitle: 'Set a new sign-in password for ${w.username}. '
                  'The warden keeps their existing hostel grants.',
              next: next,
              repeat: repeat,
            ),
          ) ??
          '';
      if (password.isEmpty) return;

      await _mutate(() async {
        await ref
            .read(adminRepositoryProvider)
            .patchWarden(w.username, password: password);
        _refresh();
        _snack('Password reset for ${w.username}.');
      }, genericFailure: 'Could not reset the password.');
    } finally {
      next.dispose();
      repeat.dispose();
    }
  }

  Future<void> _removeWarden(AdminWarden w) async {
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: AppColors.card,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            title: const Text('Remove warden?'),
            content: Text(
              'Delete the ${w.username} account and its hostel grants. '
              'Students they created stay exactly as they are — only this '
              'staff account is removed. This is recorded in the audit log '
              'and cannot be undone from the app.',
              style: AppTextStyles.bodyMd.copyWith(
                color: AppColors.textSecondary,
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.dangerText,
                ),
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('Remove'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed) return;

    await _mutate(() async {
      await ref.read(adminRepositoryProvider).deleteWarden(w.username);
      _refresh();
      _snack('${w.username} removed.');
    }, genericFailure: 'Could not remove the warden.');
  }

  // --------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final wardensAsync = ref.watch(adminWardensProvider);
    final hostelsAsync = ref.watch(wardenHostelsProvider);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: const Text('Warden Management')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _busy
            ? null
            : () => context.push('/admin/wardens/new'),
        icon: const Icon(Icons.person_add_alt_1_outlined),
        label: const Text('Create warden'),
      ),
      body: SafeArea(
        top: false,
        child: wardensAsync.when(
          loading: () => const LoadingView(label: 'Loading warden accounts…'),
          error: (e, _) => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: ErrorBar(
                message: _describe(e),
                onRetry: _refresh,
              ),
            ),
          ),
          data: (paged) => RefreshIndicator(
            onRefresh: () async => _refresh(),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
              children: [
                // ---- What this console is for ----
                InfoBox(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.admin_panel_settings_outlined,
                        size: 18,
                        color: AppColors.textSecondary,
                      ),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Wardens are staff accounts — they are never '
                              'self-registered. Create one here, assign the '
                              'hostels they may manage, and they can then '
                              'create student records and enroll faces. Only '
                              'an administrator can open this section.',
                          style: AppTextStyles.bodySm.copyWith(
                            color: AppColors.textSecondary,
                            height: 16 / 12,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),

                if (paged.items.isEmpty) ...[
                  _EmptyState(hostelCount: hostelsAsync.valueOrNull?.length ?? 0),
                ] else ...[
                  _StatsCard(wardens: paged.items),
                  const SizedBox(height: 12),
                  for (final w in paged.items) ...[
                    _WardenCard(
                      warden: w,
                      busy: _busy,
                      onAssignHostels: () => _assignHostels(
                        w,
                        hostelsAsync.valueOrNull ?? const [],
                      ),
                      onToggleStatus: () => _toggleStatus(w),
                      onResetPassword: () => _resetPassword(w),
                      onRemove: () => _removeWarden(w),
                    ),
                    const SizedBox(height: 10),
                  ],
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

class _StatsCard extends StatelessWidget {
  const _StatsCard({required this.wardens});

  final List<AdminWarden> wardens;

  @override
  Widget build(BuildContext context) {
    final active = wardens.where((w) => w.isActive).length;
    final noGrant = wardens.where((w) => !w.hasHostelAssignment).length;
    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          StatTile(label: 'Wardens', value: '${wardens.length}'),
          StatTile(label: 'Active', value: '$active'),
          StatTile(label: 'Inactive', value: '${wardens.length - active}'),
          StatTile(label: 'No hostel', value: '$noGrant'),
        ],
      ),
    );
  }
}

class _WardenCard extends StatelessWidget {
  const _WardenCard({
    required this.warden,
    required this.busy,
    required this.onAssignHostels,
    required this.onToggleStatus,
    required this.onResetPassword,
    required this.onRemove,
  });

  final AdminWarden warden;
  final bool busy;
  final VoidCallback onAssignHostels;
  final VoidCallback onToggleStatus;
  final VoidCallback onResetPassword;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final hostels = warden.hostelNames.isEmpty
        ? null
        : warden.hostelNames.join(', ');
    return SectionCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              InitialsAvatar(initials: warden.initials, size: 36),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(warden.username, style: AppTextStyles.labelLg),
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        StatusBadge(
                          label: warden.isActive ? 'Active' : 'Inactive',
                          variant: warden.isActive
                              ? BadgeVariant.verified
                              : BadgeVariant.danger,
                          dense: true,
                        ),
                        if (!warden.hasHostelAssignment) ...[
                          const SizedBox(width: 6),
                          const StatusBadge(
                            label: 'No hostel',
                            variant: BadgeVariant.pending,
                            dense: true,
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              PopupMenuButton<String>(
                tooltip: 'Warden actions',
                enabled: !busy,
                onSelected: (action) => switch (action) {
                  'hostels' => onAssignHostels(),
                  'status' => onToggleStatus(),
                  'password' => onResetPassword(),
                  _ => onRemove(),
                },
                itemBuilder: (ctx) => [
                  const PopupMenuItem(
                    value: 'hostels',
                    child: ListTile(
                      leading: Icon(Icons.domain_outlined),
                      title: Text('Assign hostels'),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                  PopupMenuItem(
                    value: 'status',
                    child: ListTile(
                      leading: Icon(
                        warden.isActive
                            ? Icons.block_outlined
                            : Icons.check_circle_outline,
                      ),
                      title: Text(
                        warden.isActive ? 'Deactivate' : 'Activate',
                      ),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'password',
                    child: ListTile(
                      leading: Icon(Icons.lock_outline),
                      title: Text('Reset password'),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'remove',
                    child: ListTile(
                      leading: Icon(
                        Icons.delete_outline,
                        color: AppColors.dangerText,
                      ),
                      title: Text(
                        'Remove warden',
                        style: TextStyle(color: AppColors.dangerText),
                      ),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 10),
          _MetaRow(
            icon: Icons.domain_outlined,
            text: hostels ?? 'No hostels assigned — this warden sees an empty roster.',
            muted: hostels == null,
          ),
          if (warden.createdAt != null) ...[
            const SizedBox(height: 4),
            _MetaRow(
              icon: Icons.schedule,
              text: 'Created ${formatActivityTime(warden.createdAt)}',
              muted: true,
            ),
          ],
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.icon, required this.text, this.muted = false});

  final IconData icon;
  final String text;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 15, color: AppColors.textSecondary),
        const SizedBox(width: 7),
        Expanded(
          child: Text(
            text,
            style: AppTextStyles.bodySm.copyWith(
              color: muted ? AppColors.textSecondary : AppColors.textPrimary,
            ),
          ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.hostelCount});

  final int hostelCount;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.groups_outlined,
            size: 28,
            color: AppColors.textSecondary,
          ),
          const SizedBox(height: 10),
          Text('No warden accounts yet', style: AppTextStyles.headlineSm),
          const SizedBox(height: 6),
          Text(
            hostelCount == 0
                ? 'Create the first hostel under hostels, then come back and '
                      'create a warden account for it.'
                : 'Create a warden account and assign it a hostel. That '
                      'warden can then create student records and enroll '
                      'their faces.',
            style: AppTextStyles.bodyMd.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

/// Password + confirmation pair used by the reset dialog. Validation is
/// duplicated client-side for immediacy; the server enforces its own minimum.
class _PasswordDialog extends StatefulWidget {
  const _PasswordDialog({
    required this.title,
    required this.subtitle,
    required this.next,
    required this.repeat,
  });

  final String title;
  final String subtitle;
  final TextEditingController next;
  final TextEditingController repeat;

  @override
  State<_PasswordDialog> createState() => _PasswordDialogState();
}

class _PasswordDialogState extends State<_PasswordDialog> {
  final _formKey = GlobalKey<FormState>();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      title: Text(widget.title),
      content: Form(
        key: _formKey,
        autovalidateMode: AutovalidateMode.onUserInteraction,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.subtitle,
              style: AppTextStyles.bodySm.copyWith(
                color: AppColors.textSecondary,
              ),
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: widget.next,
              obscureText: true,
              autofocus: true,
              style: AppTextStyles.bodyLg,
              validator: (v) => (v ?? '').length < 10
                  ? 'Password must be at least 10 characters.'
                  : null,
              decoration: const InputDecoration(
                labelText: 'New password',
                prefixIcon: Icon(Icons.lock_outline, size: 20),
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: widget.repeat,
              obscureText: true,
              style: AppTextStyles.bodyLg,
              validator: (v) => v != widget.next.text
                  ? 'Passwords do not match.'
                  : null,
              decoration: const InputDecoration(
                labelText: 'Repeat password',
                prefixIcon: Icon(Icons.lock_outline, size: 20),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (!(_formKey.currentState?.validate() ?? false)) return;
            Navigator.of(context).pop(widget.next.text);
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
