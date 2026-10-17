import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/core/network/api_client.dart';
import 'package:hostelpass/features/admin/admin_models.dart';
import 'package:hostelpass/features/admin/admin_repository.dart';

/// Records the last request so the tests can assert the exact payload the
/// admin console puts on the wire.
class _RecordingAdapter implements HttpClientAdapter {
  _RecordingAdapter(this.statusCode, this.body);

  final int statusCode;
  final String body;
  RequestOptions? last;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    last = options;
    return ResponseBody.fromString(
      body,
      statusCode,
      headers: {Headers.contentTypeHeader: [Headers.jsonContentType]},
    );
  }

  @override
  void close({bool force = false}) {}
}

(ApiClient, _RecordingAdapter) _client({int status = 200, String body = '{}'}) {
  final adapter = _RecordingAdapter(status, body);
  final dio = Dio(BaseOptions(baseUrl: 'http://test.local'));
  dio.httpClientAdapter = adapter;
  return (ApiClient(tokenStore: InMemoryTokenStore(), dio: dio), adapter);
}

Map<String, dynamic> _sentBody(RequestOptions options) {
  final data = options.data;
  if (data is Map<String, dynamic>) return data;
  if (data is String) return jsonDecode(data) as Map<String, dynamic>;
  fail('unexpected request payload type: ${data.runtimeType}');
}

List<String> _libSources() => Directory('lib')
    .listSync(recursive: true)
    .whereType<File>()
    .where((f) => f.path.endsWith('.dart'))
    .map((f) => f.readAsStringSync())
    .toList();

const _wardenOk = '''
{
  "id": "3f6c1c3e-0000-4000-8000-000000000001",
  "username": "warden.ganga",
  "role": "warden",
  "account_status": "active",
  "hostel_ids": ["95bb0f53-1423-4f15-b2f4-f0f916d761eb"],
  "hostel_names": ["Ganga Boys Hostel"],
  "created_at": "2026-10-13T18:00:00Z"
}
''';

void main() {
  // ---------------------------------------------------------------------
  // Requirement: an administrator creates and manages warden accounts.
  // ---------------------------------------------------------------------
  group('AdminWarden model', () {
    test('parses the real GET /admin/wardens payload', () {
      final w = AdminWarden.fromJson(jsonDecode(_wardenOk) as Map<String, dynamic>);
      expect(w.username, 'warden.ganga');
      expect(w.role, 'warden');
      expect(w.accountStatus, 'active');
      expect(w.isActive, isTrue);
      expect(w.hasHostelAssignment, isTrue);
      expect(w.hostelNames, ['Ganga Boys Hostel']);
      expect(w.createdAt, '2026-10-13T18:00:00Z');
    });

    test('an absent account_status defaults to inactive, never active', () {
      // Fail-closed: a malformed or partial response must not render an
      // account the console would then claim is usable.
      final w = AdminWarden.fromJson(const {
        'id': 'x',
        'username': 'w1',
        'role': 'warden',
      });
      expect(w.accountStatus, 'inactive');
      expect(w.isActive, isFalse);
      expect(w.hasHostelAssignment, isFalse);
      expect(w.hostelIds, isEmpty);
      expect(w.hostelNames, isEmpty);
    });

    test('hostel assignment reflects an empty grant honestly', () {
      final w = AdminWarden.fromJson(const {
        'id': 'x',
        'username': 'lonely',
        'role': 'warden',
        'account_status': 'active',
        'hostel_ids': <String>[],
        'hostel_names': <String>[],
      });
      expect(w.isActive, isTrue);
      expect(w.hasHostelAssignment, isFalse);
    });

    test('monogram initials handle single and compound usernames', () {
      AdminWarden of(String name) => AdminWarden.fromJson({
        'id': 'x',
        'username': name,
        'role': 'warden',
        'account_status': 'active',
      });
      expect(of('warden').initials, ['W']);
      expect(of('warden.ganga').initials, ['W', 'G']);
      expect(of('two_parts').initials, ['T', 'P']);
      expect(of('').initials, ['?']);
    });
  });

  // ---------------------------------------------------------------------
  // Requirement: never trust a client-supplied role; no role field exists.
  // ---------------------------------------------------------------------
  group('AdminRepository request contract', () {
    test('createWarden posts only username, password and hostel_ids', () async {
      final (client, adapter) = _client(body: _wardenOk);
      await AdminRepository(client).createWarden(
        username: 'warden.ganga',
        password: 'a-long-initial-password',
        hostelIds: ['95bb0f53-1423-4f15-b2f4-f0f916d761eb'],
      );

      expect(adapter.last!.path, endsWith('/v1/admin/wardens'));
      expect(adapter.last!.method, 'POST');
      final body = _sentBody(adapter.last!);
      expect(
        body.keys,
        unorderedEquals(['username', 'password', 'hostel_ids']),
      );
      // The role is decided server-side at creation; a client-supplied role
      // would be an escalation vector.
      expect(body.containsKey('role'), isFalse);
      expect(body.containsKey('account_status'), isFalse);
    });

    test('patchWarden sends only the fields the caller supplied', () async {
      final (client, adapter) = _client(body: _wardenOk);
      await AdminRepository(client).patchWarden(
        'warden.ganga',
        accountStatus: 'inactive',
      );

      expect(adapter.last!.method, 'PATCH');
      expect(adapter.last!.path, endsWith('/v1/admin/wardens/warden.ganga'));
      expect(_sentBody(adapter.last!).keys, unorderedEquals(['account_status']));
    });

    test('patchWarden has no path that can change a role', () async {
      final (client, adapter) = _client(body: _wardenOk);
      await AdminRepository(client).patchWarden(
        'warden.ganga',
        hostelIds: ['95bb0f53-1423-4f15-b2f4-f0f916d761eb'],
        password: 'another-long-password',
      );
      expect(
        _sentBody(adapter.last!).keys,
        unorderedEquals(['hostel_ids', 'password']),
      );
    });

    test('deleteWarden targets the admin endpoint for that username', () async {
      final (client, adapter) = _client(status: 204, body: '');
      await AdminRepository(client).deleteWarden('warden.ganga');
      expect(adapter.last!.method, 'DELETE');
      expect(
        adapter.last!.path,
        endsWith('/v1/admin/wardens/warden.ganga'),
      );
    });
  });

  // ---------------------------------------------------------------------
  // Requirement: no hardcoded credentials; admin section is role-gated.
  // ---------------------------------------------------------------------
  group('Admin console source guarantees', () {
    test('AdminRepository only ever calls /v1/admin', () {
      final source = File(
        'lib/features/admin/admin_repository.dart',
      ).readAsStringSync();
      expect(source.contains("'/v1/admin'"), isTrue);
      // Every path it builds is '$_base/...' — nothing may fall through to a
      // warden or student endpoint, which would be a privilege mismatch.
      expect(source.contains('/v1/warden'), isFalse);
      expect(source.contains('/v1/auth'), isFalse);
      expect(source.contains('/v1/students'), isFalse);
    });

    test('no development credential literal appears anywhere in lib/', () {
      final banned = [
        'AdminPass123',
        'WardenPass123',
        'student123',
        'ChangeMe',
        'password123',
        'admin123',
      ];
      for (final file in Directory('lib')
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'))) {
        final source = file.readAsStringSync();
        for (final secret in banned) {
          expect(
            source.contains(secret),
            isFalse,
            reason: '${file.path} must not contain the literal "$secret"',
          );
        }
      }
    });

    test('the router bounces a non-admin away from /admin/*', () {
      final router = File('lib/core/routing/app_router.dart').readAsStringSync();
      expect(
        router.contains('onAdminArea && !isAdmin'),
        isTrue,
        reason: 'a warden session must be redirected out of the admin console',
      );
      expect(router.contains("path: '/admin/wardens'"), isTrue);
      expect(router.contains('parentNavigatorKey: rootNavigatorKey'), isTrue);
      // Signed-out callers fall through to /signin before any admin path.
      expect(router.contains("if (onSignIn || onActivate) return null;"), isTrue);
    });

    test('admin-only entry points are guarded by the verified role', () {
      final profile = File(
        'lib/features/profile/profile_screen.dart',
      ).readAsStringSync();
      expect(profile.contains('staff.isAdmin'), isTrue);
      expect(
        profile.indexOf('staff.isAdmin'),
        lessThan(profile.indexOf("/admin/wardens")),
        reason: 'the console link must sit inside the isAdmin guard',
      );

      final dashboard = File(
        'lib/features/warden/warden_dashboard_screen.dart',
      ).readAsStringSync();
      expect(dashboard.contains('if (isAdmin)'), isTrue);
      expect(
        dashboard.indexOf('if (isAdmin)'),
        lessThan(dashboard.indexOf("/admin/wardens")),
        reason: 'the console card must sit inside the isAdmin guard',
      );
    });

    test('no app code can create an administrator account', () {
      // There is no UI or repository path that mints an ADMIN: the only
      // creation call targets /admin/wardens (which the server hardcodes to
      // role=warden), and the first admin exists solely via the server-side
      // CLI. Fail if anything grows a user-creation or role-setting call.
      final sources = _libSources();
      for (final banned in [
        'admin/users',
        'createAdmin',
        'create_admin',
        "'role': 'admin'",
        '"role": "admin"',
        'promoteToAdmin',
        'bootstrap',
      ]) {
        expect(
          sources.where((s) => s.contains(banned)),
          isEmpty,
          reason: 'no Flutter source may contain "$banned"',
        );
      }
    });
  });
}
