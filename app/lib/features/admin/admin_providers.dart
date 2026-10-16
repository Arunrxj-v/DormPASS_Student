import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import '../warden/warden_models.dart' show Paged;
import 'admin_models.dart';
import 'admin_repository.dart';

/// Administrator-only repository.
///
/// The server is what enforces the role (router-level `require_admin`); this
/// provider is watched only by admin screens so an accidental fetch never
/// fires from a warden or student session. Hiding a control is not
/// authorization — it just keeps the logs free of doomed requests.
///
/// Hostel data is deliberately NOT re-provided here: admin screens read the
/// same `wardenHostelsProvider` the warden screens use, so there is one
/// source of truth for what a hostel is.
final adminRepositoryProvider = Provider<AdminRepository>((ref) {
  return AdminRepository(ref.watch(apiClientProvider));
});

/// Every warden account with its hostel grants.
final adminWardensProvider = FutureProvider<Paged<AdminWarden>>((ref) {
  return ref.watch(adminRepositoryProvider).wardens(pageSize: 200);
});
