import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../auth/auth_providers.dart';
import '../../auth/auth_repository.dart';

/// White pill chip used across the scan flow ("GPS Accuracy: High (±4m)").
class InfoChip extends StatelessWidget {
  const InfoChip({
    super.key,
    required this.label,
    this.dotColor,
    this.icon,
    this.trailing,
  });

  final String label;
  final Color? dotColor;
  final IconData? icon;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (dotColor != null) ...[
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(
                color: dotColor,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 6),
          ],
          if (icon != null) ...[
            Icon(icon, size: 14, color: AppColors.textSecondary),
            const SizedBox(width: 5),
          ],
          Text(
            label,
            style: AppTextStyles.labelMd.copyWith(color: AppColors.textPrimary),
          ),
          if (trailing != null) ...[const SizedBox(width: 6), trailing!],
        ],
      ),
    );
  }
}

/// Gray pill chip ("Step 1 of 2").
class StepChip extends StatelessWidget {
  const StepChip(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(
      color: AppColors.cardHigh,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      label,
      style: AppTextStyles.labelSm.copyWith(
        fontWeight: FontWeight.w700,
        color: AppColors.textSecondary,
      ),
    ),
  );
}

/// Top bar for the attendance flow: back, lockup, "Scan Check In", avatar.
class ScanCheckInAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ScanCheckInAppBar({
    super.key,
    required this.title,
    this.onBack,
    this.trailing,
  });

  final String title;
  final VoidCallback? onBack;
  final Widget? trailing;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context) {
    final student = refWatchOrNullStudent(context);
    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.hairline)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 40,
            height: 40,
            child: IconButton(
              padding: EdgeInsets.zero,
              icon: const Icon(
                Icons.arrow_back,
                size: 22,
                color: AppColors.textPrimary,
              ),
              onPressed: onBack ?? () => Navigator.of(context).maybePop(),
            ),
          ),
          const HostelPassLogo(height: 22),
          Expanded(
            child: Center(
              child: Text(
                title,
                style: AppTextStyles.headlineSm.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          trailing ??
              (student != null
                  ? InitialsAvatar(
                      initials: student.initials,
                      size: 32,
                      radius: 8,
                    )
                  : const SizedBox(width: 32, height: 32)),
        ],
      ),
    );
  }
}

/// Schematic geofence visualization (no external map service / API key).
/// Draws the permitted radius as a dashed circle, the hostel anchor, the
/// student position with an uncertainty disc, and a faint reference grid.
class GeofenceMapPainter extends CustomPainter {
  GeofenceMapPainter({
    required this.inside,
    required this.fraction,
    required this.accuracyFraction,
    this.outsideFraction,
  });

  /// 0..1 — distance / radius (clamped for drawing when far outside).
  final double fraction;
  final bool inside;

  /// accuracy / radius, for the uncertainty disc.
  final double accuracyFraction;

  /// true distance/radius (may exceed 1), used for the outside banner display.
  final double? outsideFraction;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2 - 24;

    // Faint grid.
    final grid = Paint()..color = AppColors.hairline.withValues(alpha: 0.6);
    for (var i = 1; i < 4; i++) {
      canvas.drawLine(
        Offset(size.width / 4 * i, 0),
        Offset(size.width / 4 * i, size.height),
        grid,
      );
      canvas.drawLine(
        Offset(0, size.height / 4 * i),
        Offset(size.width, size.height / 4 * i),
        grid,
      );
    }

    // Permitted radius — dashed teal circle.
    final circle = Paint()
      ..color = AppColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    _dashedCircle(canvas, center, radius, circle);

    // Hostel anchor.
    canvas.drawCircle(center, 5, Paint()..color = AppColors.primary);
    canvas.drawCircle(
      center,
      9,
      Paint()..color = AppColors.primary.withValues(alpha: 0.25),
    );

    // Student position at a stable pseudo-direction, scaled by distance.
    const angle = -0.9; // radians — deterministic placement for the schematic
    final d = (fraction.clamp(0.0, 1.35)) * radius;
    final you = center + Offset(math.cos(angle) * d, math.sin(angle) * d);

    // Uncertainty disc.
    final acc = (accuracyFraction.clamp(0.03, 0.6)) * radius;
    canvas.drawCircle(
      you,
      acc,
      Paint()..color = AppColors.primary.withValues(alpha: 0.14),
    );

    // Dashed line anchor → you.
    _dashedLine(
      canvas,
      center,
      you,
      Paint()
        ..color = AppColors.primary.withValues(alpha: 0.55)
        ..strokeWidth = 1,
    );

    // You marker.
    canvas.drawCircle(
      you,
      11,
      Paint()..color = AppColors.primary.withValues(alpha: 0.30),
    );
    canvas.drawCircle(you, 8, Paint()..color = AppColors.primary);
    canvas.drawCircle(you, 3.5, Paint()..color = Colors.white);
  }

  void _dashedCircle(Canvas canvas, Offset c, double r, Paint paint) {
    const dash = 6.0, gap = 5.0;
    final total = 2 * math.pi * r;
    var drawn = 0.0;
    while (drawn < total) {
      final a1 = drawn / r;
      final a2 = (drawn + dash) / r;
      final p1 = c + Offset(math.cos(a1) * r, math.sin(a1) * r);
      final p2 = c + Offset(math.cos(a2) * r, math.sin(a2) * r);
      canvas.drawLine(p1, p2, paint);
      drawn += dash + gap;
    }
  }

  void _dashedLine(Canvas canvas, Offset a, Offset b, Paint paint) {
    const dash = 5.0, gap = 4.0;
    final total = (b - a).distance;
    final dir = (b - a) / total;
    var drawn = 0.0;
    while (drawn < total) {
      final p1 = a + dir * drawn;
      final p2 = a + dir * math.min(drawn + dash, total);
      canvas.drawLine(p1, p2, paint);
      drawn += dash + gap;
    }
  }

  @override
  bool shouldRepaint(GeofenceMapPainter old) =>
      old.fraction != fraction ||
      old.inside != inside ||
      old.accuracyFraction != accuracyFraction;
}

/// Reads the authenticated student from context without owning a provider.
Student? refWatchOrNullStudent(BuildContext context) {
  final holder = ProviderScope.containerOf(context, listen: false);
  return holder.read(authControllerProvider).student;
}
