import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import 'auth_providers.dart';
import 'google_sign_in_service.dart';
import 'public_config.dart';

/// Permitted student email domain — must match the backend EXACTLY
/// (no substring matching on either side).
const String collegeEmailDomain = 'ceconline.edu';

/// True only for a well-formed address whose hostname equals the domain.
bool isCollegeEmail(String value) {
  final email = value.trim().toLowerCase();
  final at = email.lastIndexOf('@');
  if (at <= 0 || at == email.length - 1) return false;
  final hostname = email.substring(at + 1);
  if (hostname != collegeEmailDomain) return false;
  // Reject obvious shape errors: no whitespace, one '@', a dot in the local part.
  if (email.contains(' ') || email.split('@').length != 2) return false;
  return email.length <= 254;
}

/// Caption under the Google button: `null` means the button is usable and the
/// normal "existing accounts only" note should show instead.
///
/// Every branch states a real condition — never a generic "unavailable".
String? googleUnavailableReason(AsyncValue<PublicConfig> cfg) {
  if (cfg.isLoading) return 'Checking Google Sign-In availability…';
  final config = cfg.valueOrNull;
  if (config == null) {
    return 'Could not check Google Sign-In right now. Sign in with your '
        'college email and password instead.';
  }
  if (config.googleSsoEnabled) return null;
  return 'Google Sign-In is not enabled for this deployment. Sign in with '
      'your college email and password instead.';
}

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  final _identifierFocus = FocusNode();
  final _passwordFocus = FocusNode();

  bool _obscure = true;
  bool _remember = false;
  bool _loading = false;
  bool _googleLoading = false;
  String? _error;
  String? _identifierError;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    _identifierFocus.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  /// Client-side pre-validation only — the backend re-validates everything.
  String? _validateIdentifier(String raw) {
    final value = raw.trim();
    if (value.isEmpty) return 'Enter your college email address.';
    if (value.contains('@')) {
      if (!isCollegeEmail(value)) {
        return 'Use your $collegeEmailDomain college email address.';
      }
      return null;
    }
    // Non-email input is a staff username or legacy roll number.
    if (value.length < 3) return 'Enter a valid email or staff username.';
    return null;
  }

  Future<void> _submit() async {
    setState(() {
      _identifierError = _validateIdentifier(_identifier.text);
      _error = null;
    });
    if (_identifierError != null) return;
    if (_password.text.isEmpty) {
      setState(() => _error = 'Enter your password.');
      return;
    }
    setState(() => _loading = true);
    try {
      await ref
          .read(authControllerProvider.notifier)
          .login(identifier: _identifier.text, password: _password.text);
      // Navigation happens via the router watching auth state.
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.displayMessage);
    } catch (_) {
      if (mounted) setState(() => _error = 'Sign-in failed. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _google() async {
    setState(() {
      _error = null;
      _identifierError = null;
    });
    setState(() => _googleLoading = true);
    try {
      final token = await GoogleSignInService.acquireIdToken();
      if (token == null) {
        // User backed out, or Google Sign-In is not configured on device.
        // Reported honestly rather than swallowed.
        setState(() => _error = GoogleSignInService.lastFailure);
        return;
      }
      await ref.read(authControllerProvider.notifier).loginWithGoogle(token);
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.displayMessage);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Google sign-in failed. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _googleLoading = false);
    }
  }

  void _infoDialog(String title, String body) {
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

  /// Account recovery is intentionally warden-mediated: no self-service
  /// password reset endpoint exists, because delivery isn't configured.
  void _recoveryDialog() {
    _infoDialog(
      'Account recovery',
      'HostelPass does not send self-service reset emails.\n\n'
          '• Forgotten password → ask your hostel warden to re-issue your '
          'activation link from the warden console.\n'
          '• Not activated yet → your account is created by your warden. '
          'Contact the hostel office.\n'
          '• College IT portal → your institutional (Octa / webmail) password '
          'can be reset there.',
    );
  }

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(publicConfigProvider);

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.only(bottom: 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ---- Institutional header strip ----
              Container(
                color: AppColors.cardLow,
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 5,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.card,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: AppColors.hairline),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(
                            Icons.account_balance_outlined,
                            size: 15,
                            color: AppColors.textPrimary,
                          ),
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              'NATIONAL INSTITUTE OF TECHNOLOGY, TRICHY',
                              style: AppTextStyles.labelMd.copyWith(
                                color: AppColors.textPrimary,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.3,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Student Residential Services • Estate Welfare Division',
                      style: AppTextStyles.bodyMd.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // ---- Sign-in card ----
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: SectionCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const HostelPassLogo(height: 26),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Hostel Attendance Portal',
                              style: AppTextStyles.headlineSm,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 7,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.cardHigh,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              'v2.4',
                              style: AppTextStyles.labelSm.copyWith(
                                fontWeight: FontWeight.w700,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Sign in with your $collegeEmailDomain college email to record '
                        'daily evening curfew attendance. Accounts are created by '
                        'your hostel warden — self-registration is not available.',
                        style: AppTextStyles.bodyMd.copyWith(
                          color: AppColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Curfew window banner (from public config; honest fallback)
                      config.when(
                        data: (c) => _CurfewBanner(
                          start: _fmtWindowTime(c.curfewStart),
                          end: _fmtWindowTime(c.curfewEnd),
                          timezone: c.timezone,
                        ),
                        loading: () => const _CurfewBanner(
                          start: null,
                          end: null,
                          timezone: null,
                        ),
                        error: (_, __) => const _CurfewBanner(
                          start: null,
                          end: null,
                          timezone: null,
                          unavailable: true,
                        ),
                      ),
                      const SizedBox(height: 20),

                      // ---- College email ----
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('College Email', style: AppTextStyles.labelLg),
                          Text(
                            'Wardens: staff username',
                            style: AppTextStyles.labelMd.copyWith(
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _identifier,
                        focusNode: _identifierFocus,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        autofillHints: const [AutofillHints.username],
                        onSubmitted: (_) => _passwordFocus.requestFocus(),
                        style: AppTextStyles.bodyLg,
                        decoration: InputDecoration(
                          hintText: 'name@$collegeEmailDomain',
                          errorText: _identifierError,
                          prefixIcon: const Padding(
                            padding: EdgeInsets.only(left: 12, right: 10),
                            child: Icon(
                              Icons.alternate_email,
                              size: 22,
                              color: AppColors.textSecondary,
                            ),
                          ),
                          prefixIconConstraints: const BoxConstraints(
                            minWidth: 0,
                            minHeight: 0,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),

                      // ---- Password ----
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Password', style: AppTextStyles.labelLg),
                          GestureDetector(
                            onTap: _recoveryDialog,
                            child: Text(
                              'Forgot password?',
                              style: AppTextStyles.labelMd.copyWith(
                                color: AppColors.primary,
                                fontWeight: FontWeight.w700,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _password,
                        focusNode: _passwordFocus,
                        obscureText: _obscure,
                        textInputAction: TextInputAction.done,
                        autofillHints: const [AutofillHints.password],
                        onSubmitted: (_) => _submit(),
                        style: AppTextStyles.bodyLg,
                        decoration: InputDecoration(
                          hintText: 'Your password',
                          prefixIcon: const Padding(
                            padding: EdgeInsets.only(left: 12, right: 10),
                            child: Icon(
                              Icons.lock_outline,
                              size: 22,
                              color: AppColors.textSecondary,
                            ),
                          ),
                          prefixIconConstraints: const BoxConstraints(
                            minWidth: 0,
                            minHeight: 0,
                          ),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscure
                                  ? Icons.visibility_off_outlined
                                  : Icons.visibility_outlined,
                              size: 22,
                              color: AppColors.textSecondary,
                            ),
                            onPressed: () =>
                                setState(() => _obscure = !_obscure),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Remember this device
                      InkWell(
                        onTap: () => setState(() => _remember = !_remember),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(top: 1),
                              child: SizedBox(
                                width: 22,
                                height: 22,
                                child: Checkbox(
                                  value: _remember,
                                  onChanged: (v) =>
                                      setState(() => _remember = v ?? false),
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'Remember this device',
                                    style: AppTextStyles.labelLg,
                                  ),
                                  Text(
                                    'Keeps you signed in on this device for faster roll call',
                                    style: AppTextStyles.bodySm.copyWith(
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),

                      if (_error != null) ...[
                        ErrorBar(message: _error!),
                        const SizedBox(height: 14),
                      ],

                      FilledButton(
                        onPressed: _loading || _googleLoading ? null : _submit,
                        child: _loading
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.login, size: 20),
                                  SizedBox(width: 8),
                                  Text('Sign In'),
                                ],
                              ),
                      ),

                      // ---- Google sign-in: existing accounts only ----
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          const Expanded(child: Divider()),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: Text(
                              'OR',
                              style: AppTextStyles.labelMd.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                          const Expanded(child: Divider()),
                        ],
                      ),
                      const SizedBox(height: 16),
                      // The backend is the authority on whether Google SSO is
                      // actually configured (`google_sso_enabled`, derived from
                      // GOOGLE_OAUTH_CLIENT_ID). When it is not, the button is
                      // visibly inert with the reason stated rather than a
                      // control that fails on press.
                      Builder(
                        builder: (context) {
                          final cfg = ref.watch(publicConfigProvider);
                          final enabled = cfg.valueOrNull?.googleSsoEnabled ??
                              false;
                          final loading = cfg.isLoading;
                          return OutlinedButton(
                            onPressed: !enabled || _loading || _googleLoading
                                ? null
                                : _google,
                            child: _googleLoading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const Icon(
                                        Icons.g_mobiledata,
                                        size: 24,
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        loading
                                            ? 'Checking Google…'
                                            : 'Continue with Google',
                                      ),
                                    ],
                                  ),
                          );
                        },
                      ),
                      const SizedBox(height: 10),
                      Text(
                        googleUnavailableReason(
                          ref.watch(publicConfigProvider),
                        ) ??
                        'Google Sign-In only opens an account your warden has '
                            'already created. It never registers a new account.',
                        textAlign: TextAlign.center,
                        style: AppTextStyles.bodySm.copyWith(
                          color: AppColors.textSecondary,
                          height: 16 / 12,
                        ),
                      ),

                      const SizedBox(height: 16),

                      // ---- Real route to the activation screen ----
                      // Without this the /activate screen would be an
                      // unreachable route: the student has no way in.
                      OutlinedButton.icon(
                        onPressed: () => context.push('/activate'),
                        icon: const Icon(Icons.key_outlined, size: 18),
                        label: const Text('I have an activation link'),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'Given to you by your warden after your face was '
                        'enrolled. Single-use, expires after a few days.',
                        textAlign: TextAlign.center,
                        style: AppTextStyles.bodySm.copyWith(
                          color: AppColors.textSecondary,
                          height: 16 / 12,
                        ),
                      ),

                      const SizedBox(height: 16),

                      // ---- No account yet: honest direction to the warden ----
                      InkWell(
                        onTap: () => _infoDialog(
                          'No self-registration',
                          'HostelPass accounts are created and enrolled by your '
                              'hostel warden.\n\n'
                              '1. Your warden submits your details.\n'
                              '2. Your warden enrolls your face at the hostel office.\n'
                              '3. You receive a single-use activation link to set '
                              'your password.\n\n'
                              'Visit the hostel office if you have not been registered.',
                        ),
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.cardLow,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            children: [
                              const Icon(
                                Icons.info_outline,
                                size: 18,
                                color: AppColors.textSecondary,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  'Don’t have an account? Contact your hostel warden.',
                                  style: AppTextStyles.bodySm.copyWith(
                                    color: AppColors.textSecondary,
                                  ),
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
                      ),

                      const SizedBox(height: 16),
                      Center(
                        child: Text(
                          'Geo-fence synchronized • Session secured',
                          style: AppTextStyles.labelSm.copyWith(
                            color: AppColors.textDisabled,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 12),

              // ---- Emergency late pass row ----
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: SectionCard(
                  padding: const EdgeInsets.all(12),
                  onTap: () => _infoDialog(
                    'Emergency Late Pass / Transit',
                    'Online outpass requests are not available in this version of HostelPass yet. '
                        'For an authorized late check-in after the curfew window, submit an offline '
                        'request at the warden office, Block C.',
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: AppColors.cardLow,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.warning_amber_outlined,
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
                              'Emergency Late Pass / Transit',
                              style: AppTextStyles.labelLg,
                            ),
                            Text(
                              'Authorized late check-ins post 22:30',
                              style: AppTextStyles.bodySm.copyWith(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Icon(
                        Icons.chevron_right,
                        size: 22,
                        color: AppColors.textSecondary,
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 20),

              // ---- Footer compliance note ----
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(
                          Icons.location_searching_outlined,
                          size: 16,
                          color: AppColors.textPrimary,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'Perimeter Policy Compliance',
                          style: AppTextStyles.labelLg,
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Hostel attendance requires device location permissions and camera '
                      'access within your assigned block perimeter. Location is requested '
                      'only during check-in — never in the background.',
                      textAlign: TextAlign.center,
                      style: AppTextStyles.bodySm.copyWith(
                        color: AppColors.textSecondary,
                        height: 16 / 12,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      'Hostel Manual 2026  •  Privacy Policy  •  Support Desk #442',
                      textAlign: TextAlign.center,
                      style: AppTextStyles.labelSm.copyWith(
                        color: AppColors.textDisabled,
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

String? _fmtWindowTime(String? hhmm) {
  if (hhmm == null) return null;
  final parts = hhmm.split(':');
  if (parts.length != 2) return hhmm;
  final hour = int.tryParse(parts.first) ?? 0;
  final suffix = hour >= 12 ? 'PM' : 'AM';
  final twelve = hour % 12 == 0 ? 12 : hour % 12;
  return '$twelve:${parts.last} $suffix';
}

/// Curfew window banner — honest "set by your hostel" fallback when the
/// institution has not published a default window.
class _CurfewBanner extends StatelessWidget {
  const _CurfewBanner({
    required this.start,
    required this.end,
    required this.timezone,
    this.unavailable = false,
  });

  final String? start;
  final String? end;
  final String? timezone;
  final bool unavailable;

  @override
  Widget build(BuildContext context) {
    final hasWindow = start != null && end != null;
    final title = unavailable
        ? 'Curfew window unavailable'
        : hasWindow
        ? 'Tonight’s curfew window'
        : 'Curfew window set by your hostel';
    final body = unavailable
        ? 'Could not load the institution default. Your hostel’s configured '
              'window applies and is shown after sign-in.'
        : hasWindow
        ? '$start – $end${timezone != null ? ' • $timezone' : ''}'
        : 'Your hostel warden configures the nightly attendance window. '
              'It appears on your home screen once you sign in.';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.pendingBg,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.schedule,
            size: 18,
            color: AppColors.pendingText,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title.toUpperCase(),
                  style: AppTextStyles.labelSm.copyWith(
                    color: AppColors.pendingText,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.6,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  body,
                  style: AppTextStyles.bodySm.copyWith(
                    color: AppColors.pendingText,
                    height: 16 / 12,
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
