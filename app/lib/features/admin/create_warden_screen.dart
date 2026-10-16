import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../warden/warden_models.dart';
import '../warden/warden_providers.dart';
import 'admin_providers.dart';

/// Admin console — create a warden account and choose its hostel grants.
///
/// Staff are never self-registered: this form is the only place a warden
/// comes into existence, and it is reachable only for an administrator
/// session (server-side `require_admin` decides that, not this widget).
class CreateWardenScreen extends ConsumerStatefulWidget {
  const CreateWardenScreen({super.key});

  @override
  ConsumerState<CreateWardenScreen> createState() =>
      _CreateWardenScreenState();
}

class _CreateWardenScreenState extends ConsumerState<CreateWardenScreen> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();

  /// Hostels the new warden will be allowed to manage. May legitimately be
  /// empty (the admin can assign later) — the UI says so honestly instead of
  /// pretending the account is fully provisioned.
  final Set<String> _hostelIds = <String>{};

  bool _obscure = true;
  bool _submitting = false;
  bool _created = false;
  String? _error;
  String? _usernameServerError;

  /// Server rule: no whitespace, 3–64 characters.
  static final _usernamePattern = RegExp(r'^[A-Za-z0-9._\-]{3,64}$');

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  String? _validateUsername(String? raw) {
    if (_usernameServerError != null) return _usernameServerError;
    final v = (raw ?? '').trim();
    if (v.isEmpty) return 'Enter a login name for the warden.';
    if (!_usernamePattern.hasMatch(v)) {
      return '3–64 characters: letters, digits, dot, dash or underscore — '
          'no spaces.';
    }
    return null;
  }

  String? _validatePassword(String? raw) {
    if ((raw ?? '').length < 10) return 'Password must be at least 10 characters.';
    return null;
  }

  String? _validateConfirm(String? raw) {
    if (raw != _password.text) return 'Passwords do not match.';
    return null;
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _submitting = true);
    try {
      final created = await ref
          .read(adminRepositoryProvider)
          .createWarden(
            username: _username.text.trim(),
            password: _password.text,
            hostelIds: _hostelIds.toList(),
          );
      ref.invalidate(adminWardensProvider);
      if (!mounted) return;
      setState(() => _created = true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            created.hostelIds.isEmpty
                ? '${created.username} created with no hostel assignment yet.'
                : 'Warden ${created.username} created for '
                      '${created.hostelNames.length} hostel'
                      '${created.hostelNames.length == 1 ? '' : 's'}.',
          ),
          behavior: SnackBarBehavior.floating,
        ),
      );
      context.pop();
    } on AppException catch (e) {
      if (!mounted) return;
      setState(() {
        if (e.code == 'conflict') {
          // Duplicate username — the only natural key this form submits.
          _usernameServerError =
              'That username is already taken. Choose another, or open the '
              'existing account from the warden list.';
        } else if (e.code == 'invalid_payload') {
          _error =
              'The server rejected one of the entered values. Check each '
              'field and try again. (${e.displayMessage})';
        } else {
          _error = e.displayMessage;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not create the warden. Try again.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hostelsAsync = ref.watch(wardenHostelsProvider);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: const Text('Create Warden')),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: hostelsAsync.when(
            loading: () => const LoadingView(label: 'Loading hostels…'),
            error: (e, _) => ErrorBar(
              message: e is AppException
                  ? e.displayMessage
                  : 'Could not load the hostel list.',
              onRetry: () => ref.invalidate(wardenHostelsProvider),
            ),
            data: (hostels) => _buildForm(context, hostels),
          ),
        ),
      ),
    );
  }

  Widget _buildForm(BuildContext context, List<WardenHostel> hostels) {
    return Form(
      key: _formKey,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ---- What this account is ----
          InfoBox(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.badge_outlined,
                  size: 18,
                  color: AppColors.textSecondary,
                ),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'This creates a staff account with the WARDEN role. The '
                        'administrator creating it keeps ADMIN — a warden can '
                        'never change their own role, and no one can be '
                        'promoted to administrator from this app.',
                    style: AppTextStyles.bodySm.copyWith(
                      color: AppColors.textSecondary,
                      height: 16 / 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ---- Username ----
          Text('Login username', style: AppTextStyles.labelLg),
          const SizedBox(height: 8),
          TextFormField(
            controller: _username,
            textInputAction: TextInputAction.next,
            autocorrect: false,
            validator: _validateUsername,
            onChanged: (_) => setState(() => _usernameServerError = null),
            style: AppTextStyles.bodyLg,
            decoration: const InputDecoration(
              hintText: 'e.g. warden.ganga',
              prefixIcon: Padding(
                padding: EdgeInsets.only(left: 12, right: 10),
                child: Icon(
                  Icons.alternate_email,
                  size: 22,
                  color: AppColors.textSecondary,
                ),
              ),
              prefixIconConstraints: BoxConstraints(minWidth: 0, minHeight: 0),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Wardens sign in with this username (students use their college '
            'email).',
            style: AppTextStyles.bodySm.copyWith(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 16),

          // ---- Password ----
          Text('Initial password', style: AppTextStyles.labelLg),
          const SizedBox(height: 8),
          TextFormField(
            controller: _password,
            obscureText: _obscure,
            textInputAction: TextInputAction.next,
            validator: _validatePassword,
            style: AppTextStyles.bodyLg,
            decoration: InputDecoration(
              hintText: 'At least 10 characters',
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
                tooltip: _obscure ? 'Show password' : 'Hide password',
                onPressed: () => setState(() => _obscure = !_obscure),
                icon: Icon(
                  _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                  size: 20,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _confirm,
            obscureText: _obscure,
            textInputAction: TextInputAction.done,
            validator: _validateConfirm,
            onFieldSubmitted: (_) => _submit(),
            style: AppTextStyles.bodyLg,
            decoration: const InputDecoration(
              hintText: 'Repeat the password',
              prefixIcon: Padding(
                padding: EdgeInsets.only(left: 12, right: 10),
                child: Icon(
                  Icons.lock_outline,
                  size: 22,
                  color: AppColors.textSecondary,
                ),
              ),
              prefixIconConstraints: BoxConstraints(minWidth: 0, minHeight: 0),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Shared with the warden out-of-band and changeable later from the '
            'warden list. Staff have no self-service password reset — an '
            'administrator resets it.',
            style: AppTextStyles.bodySm.copyWith(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 20),

          // ---- Hostels ----
          Text('Hostel assignments', style: AppTextStyles.labelLg),
          const SizedBox(height: 4),
          Text(
            'Only these hostels appear in the warden’s roster. A warden with '
            'no assignment can sign in but sees nothing to manage.',
            style: AppTextStyles.bodySm.copyWith(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 10),
          if (hostels.isEmpty)
            const ErrorBar(
              message:
                  'No hostels are configured yet. Create a hostel first, then '
                  'assign a warden to it.',
            )
          else
            Container(
              decoration: BoxDecoration(
                color: AppColors.card,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.hairline),
              ),
              child: Column(
                children: [
                  for (final h in hostels)
                    CheckboxListTile(
                      value: _hostelIds.contains(h.id),
                      controlAffinity: ListTileControlAffinity.leading,
                      activeColor: AppColors.primary,
                      dense: true,
                      title: Text(h.label, style: AppTextStyles.bodyMd),
                      onChanged: _submitting
                          ? null
                          : (v) => setState(() {
                              if (v == true) {
                                _hostelIds.add(h.id);
                              } else {
                                _hostelIds.remove(h.id);
                              }
                            }),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          if (_hostelIds.isEmpty && hostels.isNotEmpty)
            Text(
              'No hostel selected yet — this account will start with an '
              'empty roster.',
              style: AppTextStyles.bodySm.copyWith(
                color: AppColors.pendingText,
              ),
            ),
          const SizedBox(height: 16),

          if (_error != null) ...[
            ErrorBar(message: _error!),
            const SizedBox(height: 14),
          ],

          FilledButton(
            onPressed: _submitting || _created ? null : _submit,
            child: _submitting
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
                      Icon(Icons.person_add_alt_1_outlined, size: 20),
                      SizedBox(width: 8),
                      Text('Create warden account'),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
