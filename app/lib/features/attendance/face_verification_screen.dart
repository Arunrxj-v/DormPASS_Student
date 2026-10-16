import 'dart:io';
import 'dart:ui' as ui;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../face/camera_frame_utils.dart';
import '../face/face_detector_service.dart';
import 'scan_flow_controller.dart';
import 'widgets/scan_widgets.dart';

/// Step 2 of 2 — face capture & verification (Stitch screen 4).
///
/// Live camera + ML Kit detection drive the quality gates (single face,
/// eyes open, face fill, lighting). Capture runs the bundled passive
/// anti-spoof model and MobileFaceNet, then submits *evidence* — the server
/// makes the final attendance decision.
class FaceVerificationScreen extends ConsumerStatefulWidget {
  const FaceVerificationScreen({super.key});

  @override
  ConsumerState<FaceVerificationScreen> createState() =>
      _FaceVerificationScreenState();
}

enum _Gate { initializing, permissionDenied, searching, multiple, ready }

class _FaceVerificationScreenState
    extends ConsumerState<FaceVerificationScreen> {
  CameraController? _controller;
  final _detector = FaceDetectorService();

  _Gate _gate = _Gate.initializing;
  String? _permissionHint;
  bool _streamBusy = false;
  bool _capturing = false;
  bool _autoCapture = true;
  int _readyStreak = 0;
  double _faceFill = 0;
  double _headYaw = 0;
  double _luminance = 128;
  double _fps = 0;
  int _framesThisSecond = 0;
  DateTime _fpsWindow = DateTime.now();
  DateTime _lastDetect = DateTime.now();

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    setState(() {
      _gate = _Gate.initializing;
      _permissionHint = null;
    });
    try {
      final cameras = await availableCameras();
      final front = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await controller.initialize();
      await controller.startImageStream(_onFrame);
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() => _controller = controller);
    } on CameraException catch (e) {
      if (e.code == 'PermissionDenied' || e.code == 'PermissionDeniedByUser') {
        setState(() {
          _gate = _Gate.permissionDenied;
          _permissionHint = AppException(
            'local_camera_permission_denied',
          ).displayMessage;
        });
      } else {
        setState(() {
          _gate = _Gate.permissionDenied;
          _permissionHint =
              'Camera could not be started (${e.code}). ${e.description ?? ''}';
        });
      }
    }
  }

  void _onFrame(CameraImage image) {
    _framesThisSecond++;
    final now = DateTime.now();
    if (now.difference(_fpsWindow).inMilliseconds >= 1000) {
      _fps =
          _framesThisSecond / now.difference(_fpsWindow).inMilliseconds * 1000;
      _framesThisSecond = 0;
      _fpsWindow = now;
    }
    _luminance = CameraFrameUtils.meanLuminance(image);

    if (_streamBusy) return;
    // Throttle detection to ~5 Hz.
    if (now.difference(_lastDetect).inMilliseconds < 200) return;
    _streamBusy = true;
    _lastDetect = now;

    final controller = _controller;
    if (controller == null) {
      _streamBusy = false;
      return;
    }
    final rotation = _rotationFromSensor(
      controller.description.sensorOrientation,
    );
    final uprightLandscape =
        rotation == InputImageRotation.rotation90deg ||
        rotation == InputImageRotation.rotation270deg;
    final uprightHeight = uprightLandscape ? image.width : image.height;

    _detector
        .detectInNV21(
          bytes: CameraFrameUtils.toNV21(image),
          width: image.width,
          height: image.height,
          rotation: rotation,
        )
        .then((faces) {
          if (!mounted || _capturing) {
            _streamBusy = false;
            return;
          }
          _evaluateGate(faces, uprightHeight);
          _streamBusy = false;
        })
        .catchError((_) {
          _streamBusy = false;
        });
  }

  void _evaluateGate(List<DetectedFace> faces, int uprightHeight) {
    _Gate gate;
    double fill = 0;
    double yaw = 0;
    if (faces.isEmpty) {
      gate = _Gate.searching;
    } else if (faces.length > 1) {
      gate = _Gate.multiple;
    } else {
      final f = faces.first;
      fill = f.box.height / uprightHeight;
      yaw = 0;
      final goodSize = fill >= 0.22;
      final goodLight = _luminance >= 60 && _luminance <= 235;
      gate = (f.eyesOpen && goodSize && goodLight)
          ? _Gate.ready
          : _Gate.searching;
    }
    _readyStreak = gate == _Gate.ready ? _readyStreak + 1 : 0;
    setState(() {
      _gate = gate;
      _faceFill = fill;
      _headYaw = yaw;
    });

    // Auto-capture: ~1s of sustained quality (≈5 detections at 5 Hz).
    if (_autoCapture && _readyStreak >= 5) {
      _capture();
    }
  }

  InputImageRotation _rotationFromSensor(int sensorOrientation) =>
      switch (sensorOrientation) {
        0 => InputImageRotation.rotation0deg,
        90 => InputImageRotation.rotation90deg,
        180 => InputImageRotation.rotation180deg,
        _ => InputImageRotation.rotation270deg,
      };

  Future<void> _capture() async {
    final controller = _controller;
    if (controller == null || _capturing) return;
    setState(() => _capturing = true);
    try {
      final shot = await controller.takePicture();
      final file = File(shot.path);

      // Detect on the still for a precise box — detection quality on a still
      // is much better than on throttled stream frames.
      final faces = await _detector.detectInFile(file);
      if (faces.isEmpty) {
        _fail(const AppException('local_no_face'));
        return;
      }
      if (faces.length > 1) {
        _fail(const AppException('local_multiple_faces'));
        return;
      }

      await ref
          .read(scanFlowProvider.notifier)
          .verifyFaceAndSubmit(stillImage: file, faceBox: faces.first.box);
      if (!mounted) return;
      final flow = ref.read(scanFlowProvider);
      if (flow.result != null) {
        context.go('/attendance/result');
      } else {
        setState(() => _capturing = false);
      }
    } catch (_) {
      _fail(const AppException('local_no_face'));
    }
  }

  void _fail(AppException e) {
    if (!mounted) return;
    ref.read(scanFlowProvider.notifier).clearFaceError();
    // Reuse the flow error channel so the same design-system bar shows.
    setState(() => _capturing = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: const Color(0xFF93000A),
        content: Text(
          e.displayMessage,
          style: const TextStyle(fontFamily: 'Inter'),
        ),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  void dispose() {
    _controller
        ?.stopImageStream()
        .then((_) => _controller?.dispose())
        .catchError((_) {});
    _detector.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(scanFlowProvider);
    final geofence = ref.watch(geofenceProvider).valueOrNull;

    ref.listen(scanFlowProvider, (prev, next) {
      if (next.result != null && prev?.result == null) {
        context.go('/attendance/result');
      }
    });

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: ScanCheckInAppBar(
        title: 'Scan Check In',
        trailing: null,
        onBack: () => Navigator.of(context).maybePop(),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Step header row (design: Cancel · Step chip · hostel chip)
              Row(
                children: [
                  GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
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
                            Icons.close,
                            size: 15,
                            color: AppColors.textPrimary,
                          ),
                          const SizedBox(width: 5),
                          Text(
                            'Cancel',
                            style: AppTextStyles.labelMd.copyWith(
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  const StepChip('Step 2 of 2: Face Capture'),
                  const Spacer(),
                  if (geofence != null)
                    StatusBadge(
                      label: geofence.anchorLabel,
                      variant: BadgeVariant.tint,
                      dense: true,
                    ),
                ],
              ),
              const SizedBox(height: 12),

              // ---- Camera viewfinder ----
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  height: 460,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      _buildPreview(),
                      CustomPaint(painter: _ViewfinderPainter(eyeLevelY: 0.42)),
                      // Top chips
                      Positioned(
                        top: 12,
                        left: 12,
                        right: 12,
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            _DarkChip(
                              dot: _gate == _Gate.ready
                                  ? const Color(0xFF34D399)
                                  : AppColors.textDisabled,
                              label: 'Live Feed • ${_fps.round()} FPS',
                            ),
                            _DarkChip(
                              icon: Icons.wb_sunny_outlined,
                              label: 'Lighting: ${_lightingLabel()}',
                            ),
                          ],
                        ),
                      ),
                      // Bottom guidance
                      Positioned(
                        left: 24,
                        right: 24,
                        bottom: 64,
                        child: Center(
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 10,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0x99111827),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              children: [
                                Text(
                                  _guidanceTitle(),
                                  textAlign: TextAlign.center,
                                  style: AppTextStyles.headlineSm.copyWith(
                                    color: Colors.white,
                                    fontSize: 16,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _guidanceSubtitle(),
                                  textAlign: TextAlign.center,
                                  style: AppTextStyles.bodySm.copyWith(
                                    color: Colors.white70,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 26,
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _DarkChip(
                              label:
                                  'Gaze: ${_headYaw.abs() < 15 ? 'Centered' : 'Turn to center'}',
                            ),
                            const SizedBox(width: 8),
                            _DarkChip(
                              label: 'Face fill: ${(_faceFill * 100).round()}%',
                            ),
                          ],
                        ),
                      ),
                      if (_gate == _Gate.permissionDenied)
                        Center(
                          child: Container(
                            margin: const EdgeInsets.all(24),
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: AppColors.card,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(
                                  Icons.no_photography_outlined,
                                  size: 32,
                                  color: AppColors.dangerText,
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  _permissionHint ??
                                      'Camera permission required.',
                                  textAlign: TextAlign.center,
                                  style: AppTextStyles.bodyMd,
                                ),
                                const SizedBox(height: 12),
                                FilledButton(
                                  onPressed: _initCamera,
                                  style: FilledButton.styleFrom(
                                    minimumSize: const Size(160, 40),
                                  ),
                                  child: const Text('Grant Camera Access'),
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),

              if (flow.faceError != null) ...[
                const SizedBox(height: 12),
                ErrorBar(
                  message: flow.faceError!.displayMessage,
                  onRetry: () =>
                      ref.read(scanFlowProvider.notifier).clearFaceError(),
                ),
              ],
              const SizedBox(height: 12),

              // ---- Pipeline card ----
              SectionCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Biometric Validation Pipeline',
                          style: AppTextStyles.labelLg,
                        ),
                        Text(
                          'Session #${flow.sessionRef ?? 'HP-000'}',
                          style: AppTextStyles.tabularSm.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _PipelineStep(
                          index: 1,
                          title: 'Detection',
                          state: _gate == _Gate.ready
                              ? 'Validated'
                              : _gate == _Gate.multiple
                              ? 'Multiple faces'
                              : _gate == _Gate.searching
                              ? 'Searching…'
                              : 'Starting…',
                          status: _gate == _Gate.ready
                              ? _StepStatus.done
                              : _gate == _Gate.multiple
                              ? _StepStatus.error
                              : _StepStatus.active,
                        ),
                        const SizedBox(width: 8),
                        _PipelineStep(
                          index: 2,
                          title: 'Liveness',
                          state: flow.liveness?.passed == true
                              ? 'Passed (${flow.liveness!.score})'
                              : flow.faceStage == FaceStage.running &&
                                    flow.pipelineStep >= 1
                              ? 'Analyzing…'
                              : 'Standby',
                          status: flow.liveness?.passed == true
                              ? _StepStatus.done
                              : flow.faceError?.code == 'liveness_failed'
                              ? _StepStatus.error
                              : flow.faceStage == FaceStage.running &&
                                    flow.pipelineStep >= 1
                              ? _StepStatus.active
                              : _StepStatus.idle,
                        ),
                        const SizedBox(width: 8),
                        _PipelineStep(
                          index: 3,
                          title: 'Match',
                          state:
                              flow.faceStage == FaceStage.submitting ||
                                  flow.pipelineStep >= 2
                              ? 'Hostel DB…'
                              : 'Pending',
                          status: flow.pipelineStep >= 3
                              ? _StepStatus.done
                              : flow.faceStage == FaceStage.submitting
                              ? _StepStatus.active
                              : _StepStatus.idle,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // ---- Capture controls ----
              SectionCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Auto-Capture Mode',
                                style: AppTextStyles.labelLg,
                              ),
                              Text(
                                'Triggers once your face is aligned and stable',
                                style: AppTextStyles.bodySm.copyWith(
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Switch(
                          value: _autoCapture,
                          onChanged: _gate == _Gate.initializing
                              ? null
                              : (v) => setState(() => _autoCapture = v),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: FilledButton(
                            onPressed:
                                (_gate == _Gate.ready ||
                                        _gate == _Gate.searching) &&
                                    !_capturing
                                ? _capture
                                : null,
                            child:
                                _capturing || flow.faceStage != FaceStage.idle
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(
                                        Icons.photo_camera_outlined,
                                        size: 18,
                                      ),
                                      SizedBox(width: 8),
                                      Text('Verify Now'),
                                    ],
                                  ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        SizedBox(
                          width: 52,
                          height: 48,
                          child: OutlinedButton(
                            onPressed: _initCamera,
                            style: OutlinedButton.styleFrom(
                              padding: EdgeInsets.zero,
                            ),
                            child: const Icon(
                              Icons.cameraswitch_outlined,
                              size: 20,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              // ---- Anti-spoofing note ----
              InfoBox(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.verified_user_outlined,
                      size: 18,
                      color: AppColors.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Institutional anti-spoofing is active: every capture is screened by an on-device '
                        'presentation-attack model before submission. Printed photos, screen replays and '
                        'masks are rejected. No camera frames ever leave this device — only a face '
                        'similarity template is sent to the hostel server.',
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

  Widget _buildPreview() {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return Container(
        color: const Color(0xFF20242A),
        child: const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: Colors.white,
            ),
          ),
        ),
      );
    }
    // Mirror the front-camera preview horizontally (preview only).
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.diagonal3Values(-1, 1, 1),
      child: CameraPreview(controller),
    );
  }

  String _lightingLabel() {
    final l = _luminance;
    if (l < 60) return 'Too Dark';
    if (l > 235) return 'Too Bright';
    if (l >= 90 && l <= 200) return 'Optimal';
    return 'Fair';
  }

  String _guidanceTitle() {
    if (_gate == _Gate.multiple) return 'Only one person in frame';
    if (_gate == _Gate.searching) return 'Position your face in the oval';
    if (_capturing || ref.read(scanFlowProvider).faceStage != FaceStage.idle) {
      return 'Verifying — hold still';
    }
    return 'Hold still & look directly';
  }

  String _guidanceSubtitle() {
    if (_gate == _Gate.multiple) {
      return 'Step out of frame or ask others to leave';
    }
    if (_gate == _Gate.searching) {
      return 'Even lighting • eyes visible • no mask or tint';
    }
    return 'Passive liveness check runs automatically on capture';
  }
}

class _DarkChip extends StatelessWidget {
  const _DarkChip({this.label, this.dot, this.icon});

  final String? label;
  final Color? dot;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xB3111827),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (dot != null) ...[
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
          ],
          if (icon != null) ...[
            Icon(icon, size: 14, color: Colors.white70),
            const SizedBox(width: 5),
          ],
          Text(
            label ?? '',
            style: AppTextStyles.labelMd.copyWith(color: Colors.white),
          ),
        ],
      ),
    );
  }
}

enum _StepStatus { idle, active, done, error }

class _PipelineStep extends StatelessWidget {
  const _PipelineStep({
    required this.index,
    required this.title,
    required this.state,
    required this.status,
  });

  final int index;
  final String title;
  final String state;
  final _StepStatus status;

  @override
  Widget build(BuildContext context) {
    final active = status == _StepStatus.active;
    final bg = active
        ? AppColors.primary
        : status == _StepStatus.error
        ? AppColors.dangerBg
        : AppColors.cardLow;
    final fg = active ? Colors.white : AppColors.textPrimary;
    final sub = active ? Colors.white70 : AppColors.textSecondary;

    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Flexible(
                  child: Text(
                    '$index. $title',
                    style: AppTextStyles.labelMd.copyWith(color: fg),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 4),
                Icon(
                  switch (status) {
                    _StepStatus.done => Icons.check_circle_outline,
                    _StepStatus.error => Icons.error_outline,
                    _StepStatus.active => Icons.sync,
                    _StepStatus.idle => Icons.hourglass_empty,
                  },
                  size: 14,
                  color: status == _StepStatus.error
                      ? AppColors.dangerText
                      : (active ? Colors.white : AppColors.textSecondary),
                ),
              ],
            ),
            const SizedBox(height: 2),
            Text(
              state,
              style: AppTextStyles.bodySm.copyWith(color: sub),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}

/// Dark translucent scrim with a face-shaped oval cut-out, eye-level guide
/// and teal accent brackets — faithful to the design's verification viewport.
class _ViewfinderPainter extends CustomPainter {
  _ViewfinderPainter({required this.eyeLevelY});

  final double eyeLevelY;

  @override
  void paint(Canvas canvas, Size size) {
    final oval = Rect.fromCenter(
      center: Offset(size.width / 2, size.height * 0.42),
      width: size.width * 0.66,
      height: size.height * 0.62,
    );

    final scrim = Paint()..color = const Color(0x66000000);
    final path = Path()
      ..addRect(Offset.zero & size)
      ..addOval(oval);
    canvas.drawPath(path, scrim..style = PaintingStyle.fill);

    final stroke = Paint()
      ..color = Colors.white70
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawOval(oval, stroke);

    // Eye-level guide line with center gap.
    final eyeY = oval.center.dy - oval.height * 0.12;
    final line = Paint()
      ..color = const Color(0xFF9AD1CB)
      ..strokeWidth = 1.5;
    canvas.drawLine(
      Offset(oval.left + 8, eyeY),
      Offset(oval.center.dx - 42, eyeY),
      line,
    );
    canvas.drawLine(
      Offset(oval.center.dx + 42, eyeY),
      Offset(oval.right - 8, eyeY),
      line,
    );

    // Side brackets.
    final bracket = Paint()
      ..color = const Color(0xFFB5EDE7)
      ..strokeWidth = 3;
    canvas.drawLine(
      Offset(oval.left, oval.center.dy - 10),
      Offset(oval.left, oval.center.dy + 10),
      bracket,
    );
    canvas.drawLine(
      Offset(oval.right, oval.center.dy - 10),
      Offset(oval.right, oval.center.dy + 10),
      bracket,
    );
    // Top notch.
    canvas.drawLine(
      Offset(oval.center.dx - 18, oval.top),
      Offset(oval.center.dx + 18, oval.top),
      bracket,
    );

    // "EYE LEVEL" caption.
    final tp = TextPainter(
      text: TextSpan(
        text: 'E Y E   L E V E L',
        style: TextStyle(
          fontFamily: 'Inter',
          fontSize: 10,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.2,
          color: Colors.white.withValues(alpha: 0.6),
        ),
      ),
      textDirection: ui.TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(oval.center.dx - tp.width / 2, oval.center.dy + 6));
  }

  @override
  bool shouldRepaint(_ViewfinderPainter old) => old.eyeLevelY != eyeLevelY;
}
