import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/core/network/api_client.dart';
import 'package:hostelpass/features/auth/auth_repository.dart';
import 'package:hostelpass/features/auth/public_config.dart';
import 'package:hostelpass/features/auth/sign_in_screen.dart';
import 'package:hostelpass/features/warden/warden_models.dart';

/// Records the last request so tests can assert the exact payload the app
/// sends — the security property here is that no registration call exists.
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
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

(ApiClient, _RecordingAdapter) _client({
  int status = 200,
  String body = '{}',
}) {
  final adapter = _RecordingAdapter(status, body);
  final dio = Dio(BaseOptions(baseUrl: 'http://test.local'));
  dio.httpClientAdapter = adapter;
  return (ApiClient(tokenStore: InMemoryTokenStore(), dio: dio), adapter);
}

/// Dio decodes a JSON body into a map before [HttpClientAdapter] returns it
/// to the caller, so tests read the sent payload through `options.data`.
Map<String, dynamic> _sentBody(RequestOptions options) {
  final data = options.data;
  if (data is Map<String, dynamic>) return data;
  if (data is String) return jsonDecode(data) as Map<String, dynamic>;
  fail('unexpected request payload type: ${data.runtimeType}');
}

const _loginOk = '''
{
  "access_token": "tok-abc",
  "expires_in": 1800,
  "token_type": "bearer",
  "student": {
    "id": "s-1",
    "student_id": "CS-2024-800",
    "name": "Rohan Sharma",
    "email": "cs-2024-800@ceconline.edu",
    "enrollment_status": "active",
    "role": "student",
    "account_status": "active",
    "hostel": {"id": "h-1", "name": "Ganga Boys Hostel", "block": "B", "room": "314"}
  }
}
''';

void main() {
  // ---------------------------------------------------------------------
  // Requirement: exact @ceconline.edu domain — no substring shortcuts.
  // ---------------------------------------------------------------------
  group('College email validation (exact domain)', () {
    const valid = <String>[
      'student@ceconline.edu',
      'Student@ceconline.edu',
      '  padded@ceconline.edu  ',
      'f.l.dash+tag@ceconline.edu',
      'a@ceconline.edu',
    ];
    const invalid = <String>[
      'student@gmail.com',
      'student@ceconline.com',
      'student@ceconline.edu.example.com',
      'student@xceconline.edu',
      'student@sub.ceconline.edu',
      'student@CECONLINE.EDU.example.com',
      'student@host.ceconline.edu',
      'plainaddress',
      'student@',
      '@ceconline.edu',
      'student @ceconline.edu',
      'two@at@ceconline.edu',
    ];

    for (final email in valid) {
      test('accepts "$email"', () {
        expect(isCollegeEmail(email), isTrue);
      });
    }

    for (final email in invalid) {
      test('rejects "$email"', () {
        expect(isCollegeEmail(email), isFalse);
      });
    }

    test('rejects a lookalike whose hostname merely CONTAINS the domain', () {
      // Substring check would wrongly accept all of these.
      expect(isCollegeEmail('x@ceconline.edu.attacker.com'), isFalse);
      expect(isCollegeEmail('x@notceconline.edu'), isFalse);
      expect(isCollegeEmail('x@ceconline.edu.evil.io'), isFalse);
    });
  });

  // ---------------------------------------------------------------------
  // Requirement: students must NOT self-register.
  // ---------------------------------------------------------------------
  group('No self-registration path exists in the app', () {
    test('AuthRepository source exposes no register / signUp method', () {
      // Reflection isn't available in Flutter, so assert against the actual
      // source the app compiles — an honest, observable check.
      final source = File(
        'lib/features/auth/auth_repository.dart',
      ).readAsStringSync();
      for (final banned in [
        'register(',
        'signUp(',
        'signup(',
        'createAccount(',
        'enrollFace(',
        'selfEnroll(',
      ]) {
        expect(
          source.contains(banned),
          isFalse,
          reason: 'AuthRepository must not expose "$banned"',
        );
      }
      // Sanity: the methods that DO exist are present.
      expect(source.contains('Future<LoginResult> login('), isTrue);
      expect(source.contains('loginWithGoogle('), isTrue);
      expect(source.contains('Future<ActivationResult> activate('), isTrue);
    });

    test('no screen in the app links to a removed self-enrollment route', () {
      final router = File('lib/core/routing/app_router.dart')
          .readAsStringSync();
      expect(router.contains("path: '/enroll'"), isFalse,
          reason: 'the student self-enrollment route must be gone');
      expect(router.contains("'/warden/students/:ref/enroll'") ||
              router.contains("path: 'enroll'"),
          isTrue,
          reason: 'the warden-initiated enrollment route must exist');
    });

    test('login sends email OR student_id, never both, and no role field',
        () async {
      final (client, adapter) = _client(body: _loginOk);
      await AuthRepository(client)
          .login(identifier: 'a@ceconline.edu', password: 'pw');

      expect(adapter.last!.path, endsWith('/v1/auth/login'));
      final body = _sentBody(adapter.last!);
      expect(body.keys, unorderedEquals(['email', 'password']));
      expect(body.containsKey('role'), isFalse);
      expect(body.containsKey('account_status'), isFalse);
      expect(body.containsKey('enrollment_status'), isFalse);
      expect(body.containsKey('student_id'), isFalse);
    });

    test('a non-email identifier is sent as student_id (staff/legacy)', () async {
      final (client, adapter) = _client(body: _loginOk);
      await AuthRepository(client)
          .login(identifier: '  warden1  ', password: 'pw');
      final body = _sentBody(adapter.last!);
      expect(body.keys, unorderedEquals(['student_id', 'password']));
      expect(body['student_id'], 'warden1');
    });

    test('Google sign-in posts only the ID token', () async {
      final (client, adapter) = _client(body: _loginOk);
      await AuthRepository(client).loginWithGoogle('id-token-value');
      expect(adapter.last!.path, endsWith('/v1/auth/google'));
      final body = _sentBody(adapter.last!);
      expect(body.keys, ['id_token']);
    });

    test('activation posts only token + password', () async {
      final (client, adapter) = _client(body: _loginOk);
      await AuthRepository(client)
          .activate(token: 'a' * 40, password: 'LongEnough1');
      expect(adapter.last!.path, endsWith('/v1/auth/activate'));
      final body = _sentBody(adapter.last!);
      expect(body.keys, unorderedEquals(['token', 'password']));
      // No self-asserted lifecycle flags can ride along.
      expect(body.containsKey('face_enrolled'), isFalse);
      expect(body.containsKey('enrollment_status'), isFalse);
      expect(body.containsKey('active'), isFalse);
    });
  });

  // ---------------------------------------------------------------------
  // Model parsing: server-reported lifecycle is trusted, not invented.
  // ---------------------------------------------------------------------
  group('Student model', () {
    test('parses email, enrollment_status and role from the server', () {
      final s = Student.fromJson({
        'id': 's-1',
        'student_id': 'CS-2024-800',
        'name': 'Rohan',
        'email': 'x@ceconline.edu',
        'enrollment_status': 'account_provisioned',
        'role': 'warden',
        'account_status': 'inactive',
      });
      expect(s.email, 'x@ceconline.edu');
      expect(s.enrollmentStatus, 'account_provisioned');
      expect(s.role, 'warden');
      expect(s.isWarden, isTrue);
      expect(s.isStudent, isFalse);
    });

    test('missing fields fall back to safe defaults', () {
      final s = Student.fromJson({
        'id': 's-1',
        'student_id': 'CS-1',
        'name': 'A',
      });
      expect(s.role, 'student');
      expect(s.accountStatus, 'active');
      expect(s.email, isNull);
      expect(s.enrollmentStatus, isNull);
      expect(s.isWarden, isFalse);
    });

    test('initials monogram handles one-, two- and blank names', () {
      Student named(String n) => Student.fromJson({
        'id': 'i',
        'student_id': 'r',
        'name': n,
      });
      expect(named('Rohan Sharma').initials, ['R', 'S']);
      expect(named('Rohan').initials, ['R']);
      expect(named('  ').initials, ['?']);
      expect(named('').initials, ['?']);
    });
  });

  group('EnrollmentStatus model', () {
    test('reads every flag the server sent', () {
      final e = EnrollmentStatus.fromJson({
        'student_id': 's-1',
        'roll': 'CS-1',
        'name': 'Rohan',
        'email': 'x@ceconline.edu',
        'enrollment_status': 'face_enrolled',
        'account_status': 'inactive',
        'details_complete': true,
        'face_enrolled': true,
        'password_set': false,
        'activation_pending': false,
        'hostel_id': 'h-1',
        'room': '314',
      });
      expect(e.faceEnrolled, isTrue);
      expect(e.passwordSet, isFalse);
      expect(e.enrollmentStatus, 'face_enrolled');
    });

    test('absent optional flags default to false, never true', () {
      final e = EnrollmentStatus.fromJson({
        'student_id': 's-1',
        'roll': 'CS-1',
        'name': 'Rohan',
        'enrollment_status': 'created',
        'account_status': 'inactive',
      });
      expect(e.faceEnrolled, isFalse);
      expect(e.passwordSet, isFalse);
      expect(e.activationPending, isFalse);
      expect(e.detailsComplete, isFalse);
    });
  });

  group('ActivationIssue model', () {
    test('production response (no inline token) is parsed honestly', () {
      final a = ActivationIssue.fromJson({
        'enrollment_status': 'account_provisioned',
        'activation_pending': true,
        'delivered': true,
        'expires_at': '2026-10-20T15:00:00Z',
        'activation_token': null,
        'setup_url': null,
      });
      expect(a.activationToken, isNull);
      expect(a.setupUrl, isNull);
      expect(a.delivered, isTrue);
      expect(a.activationPending, isTrue);
    });

    test('development inline token is surfaced when present', () {
      final a = ActivationIssue.fromJson({
        'enrollment_status': 'account_provisioned',
        'activation_pending': true,
        'delivered': false,
        'activation_token': 'tok-43-chars-long-enough-for-validation-here',
      });
      expect(a.activationToken, isNotNull);
      expect(a.delivered, isFalse);
    });
  });

  group('Paged envelope', () {
    test('parses items and paging flags', () {
      final p = Paged.fromJson(
        {
          'items': [
            {'id': '1', 'student_id': 'CS-1', 'name': 'A', 'role': 'student',
           'account_status': 'active'},
          ],
          'page': 2,
          'page_size': 50,
          'total_pages': 3,
          'has_more': true,
        },
        WardenStudent.fromJson,
      );
      expect(p.items, hasLength(1));
      expect(p.page, 2);
      expect(p.hasMore, isTrue);
      expect(p.items.first.studentId, 'CS-1');
    });
  });

  // ---------------------------------------------------------------------
  // Google button honesty: never a control that fails on press.
  // ---------------------------------------------------------------------
  group('googleUnavailableReason', () {
    const enabled = PublicConfig(googleSsoEnabled: true);
    const disabled = PublicConfig(googleSsoEnabled: false);

    test('returns null when the backend reports SSO configured', () {
      expect(
        googleUnavailableReason(const AsyncData(enabled)),
        isNull,
        reason: 'a working button must show the normal caption',
      );
    });

    test('explains the unconfigured state instead of failing on tap', () {
      final reason = googleUnavailableReason(const AsyncData(disabled))!;
      expect(reason, isNotNull);
      expect(reason, contains('not enabled'));
      // Must point the user at the path that actually works.
      expect(reason, contains('college email'));
      // And must not pretend the account can be created here.
      expect(reason.toLowerCase(), isNot(contains('sign up')));
      expect(reason.toLowerCase(), isNot(contains('register')));
    });

    test('says it is still checking while the config request is in flight', () {
      final reason = googleUnavailableReason(
        AsyncValue<PublicConfig>.loading(),
      );
      expect(reason, isNotNull);
      expect(reason, contains('Checking'));
    });

    test('reports an unreachable config honestly, not as "not enabled"', () {
      final reason = googleUnavailableReason(
        AsyncValue<PublicConfig>.error(Exception('offline'), StackTrace.current),
      )!;
      expect(reason, isNotNull);
      expect(reason, contains('Could not check'));
      expect(reason, isNot(contains('not enabled')),
          reason: 'a network failure is not the same as a disabled feature');
    });
  });
}
