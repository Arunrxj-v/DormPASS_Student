import '../../core/network/api_client.dart';
import '../warden/warden_models.dart' show Paged;
import 'admin_models.dart';

/// Administrator-only operations: warden account provisioning, hostel
/// assignment and account status.
///
/// Every call targets `/api/v1/admin/*`, which FastAPI guards with a
/// router-level `Depends(require_admin)`. Reaching this class from the client
/// is NOT what authorizes any of it — a warden or student session receives
/// 403 from the server regardless of what this code sends.
///
/// There is no method that changes a role: `POST /admin/wardens` creates a
/// warden outright and `PATCH` accepts only password, hostel grants and
/// account status, so no call path here can mint an administrator.
class AdminRepository {
  AdminRepository(this._api);

  final ApiClient _api;

  static const _base = '/api/v1/admin';

  // ---------------------------------------------------------------- read

  Future<Paged<AdminWarden>> wardens({int page = 1, int pageSize = 50}) async {
    final data = await _api.get(
      '$_base/wardens',
      query: {'page': page, 'page_size': pageSize},
    );
    return Paged.fromJson(data as Map<String, dynamic>, AdminWarden.fromJson);
  }

  // --------------------------------------------------------------- write

  /// Create a warden account and grant it the listed hostels in one call.
  ///
  /// The password is chosen by the administrator here (staff have no
  /// activation-token flow) — minimum 10 characters is enforced server-side.
  Future<AdminWarden> createWarden({
    required String username,
    required String password,
    required List<String> hostelIds,
  }) async {
    final data = await _api.post(
      '$_base/wardens',
      body: {
        'username': username.trim(),
        'password': password,
        'hostel_ids': hostelIds,
      },
    );
    return AdminWarden.fromJson(data as Map<String, dynamic>);
  }

  /// Partial update — only the supplied fields are sent, matching the
  /// `WardenPatch` schema (password | hostel_ids | account_status).
  Future<AdminWarden> patchWarden(
    String username, {
    String? password,
    List<String>? hostelIds,
    String? accountStatus,
  }) async {
    final data = await _api.patch(
      '$_base/wardens/$username',
      body: {
        if (password != null && password.isNotEmpty) 'password': password,
        if (hostelIds != null) 'hostel_ids': hostelIds,
        if (accountStatus != null) 'account_status': accountStatus,
      },
    );
    return AdminWarden.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteWarden(String username) =>
      _api.delete('$_base/wardens/$username');
}
