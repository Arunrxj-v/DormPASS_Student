import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../auth/auth_providers.dart';
import '../attendance/attendance_models.dart';
import '../attendance/scan_flow_controller.dart';

final _historyControllerProvider =
    NotifierProvider<HistoryController, HistoryState>(HistoryController.new);

class HistoryState {
  const HistoryState({
    required this.month,
    this.filter,
    this.items = const [],
    this.summary,
    this.page = 1,
    this.hasMore = false,
    this.loading = true,
    this.loadingMore = false,
    this.error,
  });

  final DateTime month;
  final String? filter;
  final List<AttendanceRecord> items;
  final AttendanceSummary? summary;
  final int page;
  final bool hasMore;
  final bool loading;
  final bool loadingMore;
  final AppException? error;

  HistoryState copy({
    DateTime? month,
    String? Function()? filter,
    List<AttendanceRecord>? items,
    AttendanceSummary? Function()? summary,
    int? page,
    bool? hasMore,
    bool? loading,
    bool? loadingMore,
    AppException? Function()? error,
  }) => HistoryState(
    month: month ?? this.month,
    filter: filter != null ? filter() : this.filter,
    items: items ?? this.items,
    summary: summary != null ? summary() : this.summary,
    page: page ?? this.page,
    hasMore: hasMore ?? this.hasMore,
    loading: loading ?? this.loading,
    loadingMore: loadingMore ?? this.loadingMore,
    error: error != null ? error() : this.error,
  );
}

class HistoryController extends Notifier<HistoryState> {
  @override
  HistoryState build() => HistoryState(month: DateTime.now());

  String get _monthKey => DateFormat('yyyy-MM').format(state.month);

  Future<void> reload() async {
    state = state.copy(loading: true, error: () => null, items: []);
    try {
      final repo = ref.read(attendanceRepositoryProvider);
      final page1 = await repo.history(
        month: _monthKey,
        status: state.filter,
        page: 1,
      );
      final summary = await repo.summary(month: _monthKey);
      state = state.copy(
        loading: false,
        items: page1.items,
        page: 1,
        hasMore: page1.hasMore,
        summary: () => summary,
      );
    } on AppException catch (e) {
      state = state.copy(loading: false, error: () => e);
    }
  }

  Future<void> loadMore() async {
    if (state.loadingMore || !state.hasMore) return;
    state = state.copy(loadingMore: true);
    try {
      final next = await ref
          .read(attendanceRepositoryProvider)
          .history(
            month: _monthKey,
            status: state.filter,
            page: state.page + 1,
          );
      state = state.copy(
        items: [...state.items, ...next.items],
        page: state.page + 1,
        hasMore: next.hasMore,
        loadingMore: false,
      );
    } on AppException catch (e) {
      state = state.copy(loadingMore: false, error: () => e);
    }
  }

  void setMonth(DateTime month) {
    state = state.copy(month: month);
    reload();
  }

  void setFilter(String? filter) {
    state = state.copy(filter: () => filter);
    reload();
  }
}

/// Attendance history & performance (Stitch screen 7) — the "Attendance" tab.
class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 400) {
        ref.read(_historyControllerProvider.notifier).loadMore();
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(_historyControllerProvider.notifier).reload();
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(_historyControllerProvider);
    final student = ref.watch(authControllerProvider).student;

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          onRefresh: () =>
              ref.read(_historyControllerProvider.notifier).reload(),
          child: ListView(
            controller: _scroll,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
            children: [
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
                      InitialsAvatar(initials: student.initials, size: 40),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            student?.name ?? '—',
                            style: AppTextStyles.labelLg,
                          ),
                          Text(
                            '${student?.studentId ?? ''}${student?.hostel != null ? ' • ${student!.hostel!.label}' : ''}',
                            style: AppTextStyles.bodySm.copyWith(
                              color: AppColors.textSecondary,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    if (student?.cohort != null)
                      StatusBadge(
                        label: student!.cohort!.split(' ').first,
                        variant: BadgeVariant.neutral,
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Performance card
              SectionCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Flexible(child: MicroLabel('Attendance Performance')),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.primaryTint,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.verified_outlined,
                                size: 14,
                                color: AppColors.primaryTintText,
                              ),
                              const SizedBox(width: 5),
                              Text(
                                'Pass threshold > ${(state.summary?.passThresholdPercent ?? 85).round()}%',
                                style: AppTextStyles.labelSm.copyWith(
                                  color: AppColors.primaryTintText,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (state.loading && state.summary == null)
                      const Center(
                        child: Padding(
                          padding: EdgeInsets.all(12),
                          child: SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                      )
                    else if (state.summary != null) ...[
                      Row(
                        children: [
                          _Metric(
                            label: 'Present',
                            value: '${state.summary!.present}',
                            color: AppColors.successText,
                          ),
                          _Metric(
                            label: 'Absent',
                            value: '${state.summary!.absent}',
                            color: AppColors.dangerText,
                          ),
                          _Metric(
                            label: 'Outpass',
                            value: '${state.summary!.outpass}',
                            color: AppColors.textPrimary,
                          ),
                          _Metric(
                            label: 'Rate',
                            value:
                                '${state.summary!.ratePercent.toStringAsFixed(1)}%',
                            color: AppColors.primary,
                            flex: 2,
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 8,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.cardLow,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            StatusBadge(
                              label: state.summary!.eligibilitySafe
                                  ? 'Eligibility Safe'
                                  : 'Below Threshold',
                              variant: state.summary!.eligibilitySafe
                                  ? BadgeVariant.verified
                                  : BadgeVariant.danger,
                            ),
                            Text(
                              '${state.summary!.daysAccounted} of ${state.summary!.totalDays} Days Accounted',
                              style: AppTextStyles.tabularSm.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Month selector
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _MonthBtn(
                        icon: Icons.chevron_left,
                        onTap: () => ref
                            .read(_historyControllerProvider.notifier)
                            .setMonth(
                              DateTime(
                                state.month.year,
                                state.month.month - 1,
                                1,
                              ),
                            ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 7,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.card,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppColors.hairline),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.calendar_month_outlined,
                              size: 16,
                              color: AppColors.textPrimary,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              DateFormat('MMMM yyyy').format(state.month),
                              style: AppTextStyles.labelLg,
                            ),
                          ],
                        ),
                      ),
                      _MonthBtn(
                        icon: Icons.chevron_right,
                        onTap: () => ref
                            .read(_historyControllerProvider.notifier)
                            .setMonth(
                              DateTime(
                                state.month.year,
                                state.month.month + 1,
                                1,
                              ),
                            ),
                      ),
                    ],
                  ),
                  Text(
                    '${state.summary == null ? '—' : state.summary!.present + state.summary!.absent + state.summary!.outpass} entries',
                    style: AppTextStyles.bodySm.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),

              // Filter chips
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    _FilterChip(
                      label: 'All Records',
                      selected: state.filter == null,
                      onTap: () => ref
                          .read(_historyControllerProvider.notifier)
                          .setFilter(null),
                    ),
                    const SizedBox(width: 8),
                    _FilterChip(
                      label: 'Present (${state.summary?.present ?? 0})',
                      selected: state.filter == 'present',
                      onTap: () => ref
                          .read(_historyControllerProvider.notifier)
                          .setFilter('present'),
                    ),
                    const SizedBox(width: 8),
                    _FilterChip(
                      label:
                          'Pending (${state.items.where((r) => r.isPending).length})',
                      selected: state.filter == 'pending',
                      onTap: () => ref
                          .read(_historyControllerProvider.notifier)
                          .setFilter('pending'),
                    ),
                    const SizedBox(width: 8),
                    _FilterChip(
                      label: 'Absent (${state.summary?.absent ?? 0})',
                      selected: state.filter == 'absent',
                      onTap: () => ref
                          .read(_historyControllerProvider.notifier)
                          .setFilter('absent'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Log records
              SectionCard(
                padding: const EdgeInsets.all(0),
                child: Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          MicroLabel('Log Records'),
                          Text(
                            'Biometric & Roll Calls',
                            style: AppTextStyles.bodySm.copyWith(
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (state.loading)
                      const Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(
                          child: SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                      )
                    else if (state.error != null)
                      Padding(
                        padding: const EdgeInsets.all(14),
                        child: ErrorBar(
                          message: state.error!.displayMessage,
                          onRetry: () => ref
                              .read(_historyControllerProvider.notifier)
                              .reload(),
                        ),
                      )
                    else if (state.items.isEmpty)
                      Padding(
                        padding: const EdgeInsets.all(20),
                        child: Column(
                          children: [
                            const Icon(
                              Icons.event_note_outlined,
                              size: 28,
                              color: AppColors.textDisabled,
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'No records for ${DateFormat('MMMM yyyy').format(state.month)}.',
                              style: AppTextStyles.bodyMd.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      ...state.items.asMap().entries.map(
                        (e) => _LogRow(
                          record: e.value,
                          last:
                              e.key == state.items.length - 1 && !state.hasMore,
                          hostelLabel: ref
                              .read(authControllerProvider)
                              .student
                              ?.hostel
                              ?.label,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // Grievance card
              InfoBox(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.help_outline,
                      size: 18,
                      color: AppColors.textSecondary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Discrepancy in records?',
                            style: AppTextStyles.labelLg,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'File an attendance grievance within 48 hours with the Warden Office. '
                            'Include the biometric gate timestamp from your record.',
                            style: AppTextStyles.bodySm.copyWith(
                              color: AppColors.textSecondary,
                            ),
                          ),
                          const SizedBox(height: 6),
                          GestureDetector(
                            onTap: () => showDialog<void>(
                              context: context,
                              builder: (context) => AlertDialog(
                                backgroundColor: AppColors.card,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                title: Text(
                                  'Raise a grievance',
                                  style: AppTextStyles.headlineSm,
                                ),
                                content: Text(
                                  'Online grievance filing is not available in this version of HostelPass yet. '
                                  'Please submit your grievance in person at the Warden Office (Block C) within '
                                  '48 hours of the disputed roll call.',
                                  style: AppTextStyles.bodyMd.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                                actions: [
                                  TextButton(
                                    onPressed: () =>
                                        Navigator.of(context).pop(),
                                    child: const Text('Close'),
                                  ),
                                ],
                              ),
                            ),
                            child: Text(
                              'Raise Grievance →',
                              style: AppTextStyles.labelLg.copyWith(
                                color: AppColors.primary,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                          ),
                        ],
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

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.color,
    this.flex = 1,
  });

  final String label;
  final String value;
  final Color color;
  final int flex;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      flex: flex,
      child: Column(
        children: [
          Text(
            value,
            style: AppTextStyles.headlineMd.copyWith(
              color: color,
              fontFeatures: const [ui.FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: AppTextStyles.bodySm.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _MonthBtn extends StatelessWidget {
  const _MonthBtn({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(8),
    child: Container(
      width: 34,
      height: 36,
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Icon(icon, size: 20, color: AppColors.textPrimary),
    ),
  );
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: selected ? AppColors.primary : AppColors.card,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: selected ? AppColors.primary : AppColors.hairline,
        ),
      ),
      child: Text(
        label,
        style: AppTextStyles.labelLg.copyWith(
          color: selected ? Colors.white : AppColors.textPrimary,
        ),
      ),
    ),
  );
}

class _LogRow extends StatelessWidget {
  const _LogRow({required this.record, required this.last, this.hostelLabel});

  final AttendanceRecord record;
  final bool last;
  final String? hostelLabel;

  @override
  Widget build(BuildContext context) {
    final (label, variant) = record.isPresent
        ? ('Present', BadgeVariant.verified)
        : record.isPending
        ? ('Pending Review', BadgeVariant.pending)
        : ('Absent', BadgeVariant.danger);

    final dayLabel = _dayLabel(record);

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        border: last
            ? null
            : const Border(bottom: BorderSide(color: AppColors.hairline)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(dayLabel, style: AppTextStyles.labelLg)),
              StatusBadge(label: label, variant: variant, dense: true),
              const SizedBox(width: 10),
              Text(
                record.isAbsent ? '—' : record.timeLabel,
                style: AppTextStyles.tabularSm.copyWith(
                  color: record.isAbsent
                      ? AppColors.dangerText
                      : AppColors.textPrimary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Icon(
                record.isAbsent ? Icons.error_outline : Icons.verified_outlined,
                size: 15,
                color: record.isAbsent
                    ? AppColors.dangerText
                    : AppColors.textSecondary,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  record.isAbsent
                      ? 'Curfew window missed — no check-in recorded'
                      : 'Face ID + GPS verified${hostelLabel != null ? ' • $hostelLabel' : ''}',
                  style: AppTextStyles.bodySm.copyWith(
                    color: AppColors.textSecondary,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (!record.isAbsent)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.cardHigh,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    record.reference.length > 8
                        ? record.reference.substring(
                            record.reference.length - 4,
                          )
                        : record.reference,
                    style: AppTextStyles.labelSm.copyWith(
                      color: AppColors.textSecondary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  String _dayLabel(AttendanceRecord record) {
    final d = DateTime.tryParse(record.date);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    if (d == null) return record.date;
    final day = DateTime(d.year, d.month, d.day);
    if (day == today) return 'Today, ${DateFormat('d MMM').format(day)}';
    if (day == today.subtract(const Duration(days: 1))) {
      return 'Yesterday, ${DateFormat('d MMM').format(day)}';
    }
    return DateFormat('EEEE, d MMM').format(day);
  }
}
