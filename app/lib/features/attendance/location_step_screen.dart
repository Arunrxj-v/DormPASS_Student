import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../location/geofence_math.dart';
import '../location/location_service.dart';
import 'attendance_models.dart';
import 'scan_flow_controller.dart';
import 'widgets/scan_widgets.dart';

/// Step 1 of 2 — location verification (Stitch screen 3).
class LocationStepScreen extends ConsumerStatefulWidget {
  const LocationStepScreen({super.key});

  @override
  ConsumerState<LocationStepScreen> createState() => _LocationStepScreenState();
}

class _LocationStepScreenState extends ConsumerState<LocationStepScreen> {
  @override
  void initState() {
    super.initState();
    // Acquire on entry if we don't have a fresh fix yet.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final flow = ref.read(scanFlowProvider);
      if (flow.locationStage == LocationStage.idle) {
        ref.read(scanFlowProvider.notifier).acquireLocation();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final geofenceAsync = ref.watch(geofenceProvider);
    final flow = ref.watch(scanFlowProvider);

    return geofenceAsync.when(
      loading: () =>
          const Scaffold(body: LoadingView(label: 'Loading hostel zone…')),
      error: (e, _) => Scaffold(
        appBar: const ScanCheckInAppBar(title: 'Scan Check In'),
        body: ErrorBar(
          message: e is AppException
              ? e.displayMessage
              : 'Could not load hostel configuration.',
          onRetry: () => ref.invalidate(geofenceProvider),
        ),
      ),
      data: (geofence) {
        return Scaffold(
          backgroundColor: AppColors.surface,
          appBar: const ScanCheckInAppBar(title: 'Scan Check In'),
          body: SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'VERIFICATION STEP',
                        style: AppTextStyles.microLabel(
                          color: AppColors.primary,
                        ),
                      ),
                      const StepChip('Step 1 of 2'),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Location Verification',
                    style: AppTextStyles.headlineLg,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Confirming you are physically within your assigned hostel boundary before face capture.',
                    style: AppTextStyles.bodyLg.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ---- Geofence map card ----
                  SectionCard(
                    padding: const EdgeInsets.all(12),
                    color: AppColors.cardLow,
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            InfoChip(
                              label: _accuracyLabel(flow.fix, geofence),
                              dotColor: flow.fix == null
                                  ? AppColors.textDisabled
                                  : (flow.fix!.accuracyMeters <= 10
                                        ? AppColors.successText
                                        : AppColors.pendingText),
                            ),
                            InfoChip(
                              label: flow.fix == null
                                  ? 'Acquiring GPS…'
                                  : 'GPS fix ${flow.fix!.timestamp.toLocal().hour.toString().padLeft(2, '0')}:${flow.fix!.timestamp.toLocal().minute.toString().padLeft(2, '0')}',
                              icon: Icons.satellite_alt_outlined,
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 240,
                          child: Stack(
                            clipBehavior: Clip.none,
                            children: [
                              Positioned.fill(
                                child: CustomPaint(
                                  painter: GeofenceMapPainter(
                                    inside: flow.inside ?? false,
                                    fraction:
                                        (flow.distanceM ?? 0) /
                                        geofence.permittedRadiusM,
                                    accuracyFraction:
                                        (flow.fix?.accuracyMeters ?? 5) /
                                        geofence.permittedRadiusM,
                                  ),
                                ),
                              ),
                              Positioned(
                                top: 34,
                                left: 0,
                                right: 0,
                                child: Center(
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 4,
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.cardHigh,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      'Anchor: ${geofence.anchorLabel} '
                                      '(${geofence.latitude.toStringAsFixed(4)}° N, ${geofence.longitude.toStringAsFixed(4)}° E)',
                                      style: AppTextStyles.tabularSm.copyWith(
                                        color: AppColors.textPrimary,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                              Positioned(
                                bottom: 6,
                                left: 0,
                                child: InfoChip(
                                  label:
                                      'Permitted Radius: ${geofence.permittedRadiusM.round()} m',
                                ),
                              ),
                              Positioned(
                                bottom: 6,
                                right: 0,
                                child: Container(
                                  width: 38,
                                  height: 38,
                                  decoration: BoxDecoration(
                                    color: AppColors.card,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(
                                      color: AppColors.hairline,
                                    ),
                                  ),
                                  child: IconButton(
                                    padding: EdgeInsets.zero,
                                    iconSize: 19,
                                    icon: const Icon(
                                      Icons.my_location,
                                      color: AppColors.textPrimary,
                                    ),
                                    onPressed: () => ref
                                        .read(scanFlowProvider.notifier)
                                        .acquireLocation(),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  if (flow.locationStage == LocationStage.acquiring) ...[
                    SectionCard(
                      child: Row(
                        children: [
                          const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              'Acquiring GPS fix — hold still for a moment…',
                              style: AppTextStyles.bodyMd,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ] else if (flow.locationStage == LocationStage.failed &&
                      flow.locationError != null) ...[
                    ErrorBar(
                      message: flow.locationError!.displayMessage,
                      onRetry: () =>
                          ref.read(scanFlowProvider.notifier).acquireLocation(),
                    ),
                    const SizedBox(height: 12),
                  ] else if (flow.locationStage == LocationStage.ready &&
                      flow.inside == true) ...[
                    _InsideCard(flow: flow, geofence: geofence),
                    const SizedBox(height: 12),
                  ] else if (flow.locationStage == LocationStage.ready) ...[
                    _OutsideInlineCard(flow: flow, geofence: geofence),
                    const SizedBox(height: 12),
                  ],

                  // ---- Boundary policy card ----
                  InfoBox(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(
                              Icons.info_outline,
                              size: 18,
                              color: AppColors.textSecondary,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'Attendance Boundary Policy',
                                    style: AppTextStyles.labelLg,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    'Outside the ${geofence.permittedRadiusM.round()}m perimeter, the facial scanner '
                                    'remains locked. You must be physically present at the block entry or dorm. '
                                    'Your GPS reading must also be accurate to ${geofence.maxLocationAccuracyM.round()}m or better.',
                                    style: AppTextStyles.bodySm.copyWith(
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                'Test Outside-Zone Rule (demo)',
                                style: AppTextStyles.bodyMd.copyWith(
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ),
                            Switch(
                              value: flow.simulateOutside,
                              onChanged: (v) => ref
                                  .read(scanFlowProvider.notifier)
                                  .setSimulateOutside(v),
                            ),
                          ],
                        ),
                        Text(
                          'Simulates the local pre-check only — the server geofence still applies to every real check-in.',
                          style: AppTextStyles.bodySm.copyWith(
                            color: AppColors.textDisabled,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ---- Actions ----
                  FilledButton(
                    onPressed: flow.canProceedToFace
                        ? () => context.push('/attendance/face')
                        : null,
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Proceed to Face Verification'),
                        SizedBox(width: 8),
                        Icon(Icons.arrow_forward, size: 18),
                      ],
                    ),
                  ),
                  if (flow.locationStage == LocationStage.ready &&
                      flow.inside == false) ...[
                    const SizedBox(height: 8),
                    OutlinedButton(
                      onPressed: () => context.push('/attendance/outside'),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.lock_outline, size: 18),
                          SizedBox(width: 8),
                          Text('View Lockout Details'),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: flow.locationStage == LocationStage.acquiring
                        ? null
                        : () => ref
                              .read(scanFlowProvider.notifier)
                              .acquireLocation(),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.sync, size: 18),
                        SizedBox(width: 8),
                        Text('Calibrate GPS / Refresh Location'),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  String _accuracyLabel(LocationFix? fix, GeofenceConfig geofence) {
    if (fix == null) return 'GPS Accuracy: acquiring';
    final quality = fix.accuracyMeters <= 10
        ? 'High'
        : fix.accuracyMeters <= geofence.maxLocationAccuracyM
        ? 'Moderate'
        : 'Low';
    return 'GPS Accuracy: $quality (±${fix.accuracyMeters.round()}m)';
  }
}

class _InsideCard extends StatelessWidget {
  const _InsideCard({required this.flow, required this.geofence});

  final ScanFlowState flow;
  final GeofenceConfig geofence;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.primaryTint,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.shield_outlined,
                  color: AppColors.primary,
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Inside Hostel Zone',
                  style: AppTextStyles.headlineSm,
                ),
              ),
              const StatusBadge(
                label: 'Verified',
                variant: BadgeVariant.verified,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Your location is verified inside ${geofence.name}${geofence.block != null ? ' Block ${geofence.block}' : ''} '
            'perimeter. You are eligible to record attendance.',
            style: AppTextStyles.bodyMd.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          InfoBox(
            child: Row(
              children: [
                StatTile(
                  label: 'Current Distance',
                  value: '${flow.distanceM!.round()} m',
                ),
                Container(width: 1, height: 34, color: AppColors.hairline),
                const SizedBox(width: 12),
                StatTile(
                  label: 'Threshold Limit',
                  value: '${geofence.permittedRadiusM.round()} m max',
                ),
                Container(width: 1, height: 34, color: AppColors.hairline),
                const SizedBox(width: 12),
                StatTile(
                  label: 'Signal Lock',
                  value: 'Secured',
                  trailing: const Icon(
                    Icons.lock,
                    size: 14,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _OutsideInlineCard extends StatelessWidget {
  const _OutsideInlineCard({required this.flow, required this.geofence});

  final ScanFlowState flow;
  final GeofenceConfig geofence;

  @override
  Widget build(BuildContext context) {
    final distance = flow.distanceM ?? 0;
    final deviation = GeofenceMath.deviationMeters(
      distanceMeters: distance,
      permittedRadiusMeters: geofence.permittedRadiusM,
    );
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.dangerBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.location_off_outlined,
                  color: AppColors.dangerText,
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Outside Hostel Zone',
                  style: AppTextStyles.headlineSm,
                ),
              ),
              const StatusBadge(label: 'Locked', variant: BadgeVariant.danger),
            ],
          ),
          const SizedBox(height: 10),
          Text.rich(
            TextSpan(
              style: AppTextStyles.bodyMd.copyWith(
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
                const TextSpan(
                  text:
                      ' the allowed perimeter. Attendance can only be recorded inside the block boundary.',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
