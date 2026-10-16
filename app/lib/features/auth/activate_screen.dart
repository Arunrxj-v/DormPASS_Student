import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import 'auth_providers.dart';

/// Password setup — the final step of account provisioning.
///
/// The student opens a single-use, time-limited link issued by their warden
/// (`POST /warden/students/{id}/activate`) and chooses their own password.
/// The token, not this form, determines which account is activated.
///
/// Reached either via the `hostelpass://activate?token=…` deep link (token
/// pre-filled) or by pasting the token from the email/warden hand-off.
class ActivateScreen extends ConsumerStatefulWidget {
  const ActivateScreen({super.key, this.initialToken});

  final String? initialToken;

  @override
  ConsumerState<ActivateScreen> createState() => _ActivateScreenState();
}

class _ActivateScreenState extends ConsumerState<ActivateScreen> {
  final _formKey = GlobalKey<FormState>();
  final _token = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();

  bool _obscure = true;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.initialToken != null && widget.initialToken!.isNotEmpty) {
      _token.text = widget.initialToken!;
    }
  }

  @override
  void dispose() {
    _token.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  String? _validatePassword(String? value) {
    final v = value ?? '';
    if (v.isEmpty) return 'Choose a password.';
    if (v.length < 8) return 'Use at least 8 characters.';
    if (v.length > 128) return 'Password is too long.';
    return null;
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _loading = true);
    try {
      await ref
          .read(authControllerProvider.notifier)
          .activate(
            token: resolveActivationInput(_token.text),
            password: _password.text,
          );
      // The router redirects to the role-appropriate home on auth change.
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.displayMessage);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Activation failed. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go('/signin'),
        ),
        title: Text('Activate your account', style: AppTextStyles.headlineSm),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SectionCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(
                            Icons.key_outlined,
                            color: AppColors.primary,
                          ),
                          SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Activation key from your warden',
                              style: AppTextStyles.headlineSm,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 8),
                      Text(
                        'Your warden created your HostelPass record and enrolled '
                        'your face. The key is single-use and expires. '
                        'Redeeming it sets your own password and activates '
                        'your account — no one else, including your warden, '
                        'ever sees or chooses your password.',
                        style: AppTextStyles.bodyMd,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // ---- Activation token ----
                Text('Activation key or link', style: AppTextStyles.labelLg),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _token,
                  minLines: 1,
                  maxLines: 3,
                  autocorrect: false,
                  enableSuggestions: false,
                  keyboardType: TextInputType.multiline,
                  style: AppTextStyles.bodyMd,
                  decoration: const InputDecoration(
                    hintText: 'Paste the key your warden sent you',
                    prefixIcon: Padding(
                      padding: EdgeInsets.only(left: 12, right: 10),
                      child: Icon(
                        Icons.vpn_key_outlined,
                        size: 22,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    prefixIconConstraints: BoxConstraints(
                      minWidth: 0,
                      minHeight: 0,
                    ),
                  ),
                  validator: (v) => (v == null || v.trim().length < 20)
                      ? 'Paste the full activation key or link.'
                      : null,
                ),
                const SizedBox(height: 16),

                // ---- Password ----
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('New password', style: AppTextStyles.labelLg),
                    GestureDetector(
                      onTap: () => showDialog<void>(
                        context: context,
                        builder: (context) => AlertDialog(
                          backgroundColor: AppColors.card,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          title: const Text('Password requirements'),
                          content: const Text(
                            '• At least 8 characters\n'
                            '• Something you will remember\n'
                            '• Never share it — wardens cannot reset it for you, '
                            'but they can issue a fresh activation key',
                          ),
                          actions: [
                            TextButton(
                              onPressed: () => Navigator.of(context).pop(),
                              child: const Text('Close'),
                            ),
                          ],
                        ),
                      ),
                      child: Text(
                        'Requirements',
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
                TextFormField(
                  controller: _password,
                  obscureText: _obscure,
                  style: AppTextStyles.bodyLg,
                  validator: _validatePassword,
                  decoration: InputDecoration(
                    hintText: 'At least 8 characters',
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
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                Text('Confirm password', style: AppTextStyles.labelLg),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _confirm,
                  obscureText: _obscure,
                  style: AppTextStyles.bodyLg,
                  validator: (v) => v != _password.text
                      ? 'Passwords do not match.'
                      : null,
                  decoration: const InputDecoration(
                    hintText: 'Repeat the password',
                    prefixIcon: Padding(
                      padding: EdgeInsets.only(left: 12, right: 10),
                      child: Icon(
                        Icons.lock_reset_outlined,
                        size: 22,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    prefixIconConstraints: BoxConstraints(
                      minWidth: 0,
                      minHeight: 0,
                    ),
                  ),
                ),
                const SizedBox(height: 20),

                if (_error != null) ...[
                  ErrorBar(message: _error!),
                  const SizedBox(height: 14),
                ],

                FilledButton(
                  onPressed: _loading ? null : _submit,
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
                            Icon(Icons.verified_user_outlined, size: 20),
                            SizedBox(width: 8),
                            Text('Activate account'),
                          ],
                        ),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => context.go('/signin'),
                  child: const Text('Back to sign in'),
                ),

                const SizedBox(height: 8),
                InfoBox(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Link expired or already used?',
                        style: AppTextStyles.labelLg,
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Ask your hostel warden to issue a new activation link '
                        'from the warden console. Only the most recent link works.',
                        style: AppTextStyles.bodySm,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Resolves whatever the student pasted or typed into the raw activation key
/// the backend expects: a bare key (the normal WhatsApp hand-off), a
/// `hostelpass://activate?token=…` deep link, or a hosted link in either
/// `…/activate#token=…` (fragment — never sent to server logs) or the old
/// `…?token=` query form. Whitespace from WhatsApp line wrapping is removed;
/// dashes and underscores are KEPT — they are valid characters inside the key.
String resolveActivationInput(String raw) {
  final cleaned = raw.replaceAll(RegExp(r'\s'), '');
  if (cleaned.isEmpty) return cleaned;
  final looksLikeUri =
      cleaned.startsWith('hostelpass://') ||
      cleaned.startsWith('http://') ||
      cleaned.startsWith('https://');
  if (!looksLikeUri) return cleaned; // bare key (pasted or hand-typed)
  final uri = Uri.tryParse(cleaned);
  if (uri == null) return cleaned;
  final fromQuery = tokenFromActivationUri(uri);
  if (fromQuery != null) return fromQuery;
  // Web links carry the key in the FRAGMENT (#token=…) so it never reaches
  // server logs — Uri.queryParameters does not see fragments.
  final fromFragment = Uri.splitQueryString(uri.fragment)['token'];
  if (fromFragment != null && fromFragment.isNotEmpty) return fromFragment;
  return cleaned;
}

/// Copies the raw activation URI's token out for the [ActivateScreen].
String? tokenFromActivationUri(Uri uri) {
  final fromQuery = uri.queryParameters['token'];
  if (fromQuery != null && fromQuery.isNotEmpty) return fromQuery;
  // hostelpass://activate?token=… is the primary form; also accept the
  // path form hostelpass://activate/<token> for hand-typed links.
  final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
  if (segments.isNotEmpty && segments.last.length >= 20) return segments.last;
  return null;
}

/// Utility used by the settings screen when a warden hands over a code.
Future<void> copyTextToClipboard(String value) =>
    Clipboard.setData(ClipboardData(text: value));
