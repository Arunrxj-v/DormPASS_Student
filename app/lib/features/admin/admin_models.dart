/// Administrator data contracts — mirror `server/app/schemas/admin.py`.
library;

/// One warden account exactly as `GET /api/v1/admin/wardens` returns it.
///
/// There is deliberately no `role` writer anywhere in the app: a warden's
/// role is set once at creation by an administrator and the PATCH schema
/// simply has no `role` field, so nothing here could escalate it even if a
/// caller crafted the request by hand.
class AdminWarden {
  const AdminWarden({
    required this.id,
    required this.username,
    required this.role,
    required this.accountStatus,
    required this.hostelIds,
    required this.hostelNames,
    this.createdAt,
  });

  final String id;
  final String username;
  final String role;
  final String accountStatus;
  final List<String> hostelIds;
  final List<String> hostelNames;
  final String? createdAt;

  bool get isActive => accountStatus == 'active';

  /// An active warden with no hostel grant can sign in but is shown an empty
  /// roster by the backend — worth calling out rather than rendering as if
  /// they were fully provisioned.
  bool get hasHostelAssignment => hostelIds.isNotEmpty;

  /// Monogram letters for the identity tile (usernames have no spaces).
  List<String> get initials {
    final parts = username
        .split(RegExp(r'[\s._-]+'))
        .where((p) => p.isNotEmpty)
        .toList();
    if (parts.isEmpty) return const ['?'];
    if (parts.length == 1) {
      final one = parts.first;
      return [one.substring(0, 1).toUpperCase()];
    }
    return [
      parts.first.substring(0, 1).toUpperCase(),
      parts[1].substring(0, 1).toUpperCase(),
    ];
  }

  factory AdminWarden.fromJson(Map<String, dynamic> j) => AdminWarden(
    id: j['id'] as String? ?? '',
    username: j['username'] as String? ?? '',
    role: j['role'] as String? ?? 'warden',
    accountStatus: j['account_status'] as String? ?? 'inactive',
    hostelIds: [
      for (final v in (j['hostel_ids'] as List? ?? const [])) v.toString(),
    ],
    hostelNames: [
      for (final v in (j['hostel_names'] as List? ?? const [])) v.toString(),
    ],
    createdAt: j['created_at'] as String?,
  );
}
