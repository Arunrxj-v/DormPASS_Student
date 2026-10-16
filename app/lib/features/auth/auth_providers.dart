import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import 'auth_repository.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(apiClientProvider)),
);

enum AuthStatus { unknown, unauthenticated, authenticated }

class AuthState {
  const AuthState(this.status, [this.student]);
  final AuthStatus status;
  final Student? student;

  bool get isAuthenticated =>
      status == AuthStatus.authenticated && student != null;

  /// Role-based shell selection — students and staff get different navigation.
  bool get isStaff => student?.isWarden ?? false;
}

/// Holds the session. Restores on app start by validating the stored JWT
/// against /auth/me — a stored-but-expired token lands in `unauthenticated`.
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthState(AuthStatus.unknown);

  Future<void> restoreSession() async {
    final api = ref.read(apiClientProvider);
    final token = await api.tokenStore.read();
    if (token == null) {
      state = const AuthState(AuthStatus.unauthenticated);
      return;
    }
    try {
      final student = await ref.read(authRepositoryProvider).me();
      state = AuthState(AuthStatus.authenticated, student);
    } catch (_) {
      // Expired / revoked / server unreachable with no session to trust.
      await api.tokenStore.clear();
      state = const AuthState(AuthStatus.unauthenticated);
    }
  }

  /// Email (or legacy roll number) + password.
  Future<void> login({
    required String identifier,
    required String password,
  }) async {
    final api = ref.read(apiClientProvider);
    final result = await ref
        .read(authRepositoryProvider)
        .login(identifier: identifier, password: password);
    await api.tokenStore.write(result.accessToken);
    state = AuthState(AuthStatus.authenticated, result.student);
  }

  /// Google ID token -> server-verified sign-in for an EXISTING account.
  Future<void> loginWithGoogle(String idToken) async {
    final api = ref.read(apiClientProvider);
    final result = await ref
        .read(authRepositoryProvider)
        .loginWithGoogle(idToken);
    await api.tokenStore.write(result.accessToken);
    state = AuthState(AuthStatus.authenticated, result.student);
  }

  /// Redeem a warden-issued activation token and establish a password.
  Future<void> activate({
    required String token,
    required String password,
  }) async {
    final api = ref.read(apiClientProvider);
    final result = await ref
        .read(authRepositoryProvider)
        .activate(token: token, password: password);
    await api.tokenStore.write(result.accessToken);
    state = AuthState(AuthStatus.authenticated, result.student);
  }

  /// Replaces the cached student (e.g. after profile refresh).
  void setStudent(Student student) {
    state = AuthState(AuthStatus.authenticated, student);
  }

  Future<void> signOut() async {
    final api = ref.read(apiClientProvider);
    try {
      await ref.read(authRepositoryProvider).logout();
    } catch (_) {
      // Best effort — local sign-out must always succeed.
    }
    await api.tokenStore.clear();
    state = const AuthState(AuthStatus.unauthenticated);
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(
  AuthController.new,
);

/// Convenience selector used by the router redirect.
final isAuthenticatedProvider = Provider<bool>(
  (ref) => ref.watch(authControllerProvider).isAuthenticated,
);

/// True when the signed-in user is a warden or administrator.
final isStaffProvider = Provider<bool>(
  (ref) => ref.watch(authControllerProvider).isStaff,
);
