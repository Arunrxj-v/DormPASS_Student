import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/core/errors/app_exception.dart';
import 'package:hostelpass/core/network/api_client.dart';

/// Stub HTTP adapter returning canned responses to exercise the
/// {"error":{"code","message","details"}} envelope mapping.
class _StubAdapter implements HttpClientAdapter {
  _StubAdapter(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async => ResponseBody.fromString(
    body,
    statusCode,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );

  @override
  void close({bool force = false}) {}
}

ApiClient _clientWith(int statusCode, String body) {
  final dio = Dio(BaseOptions(baseUrl: 'http://test.local'));
  dio.httpClientAdapter = _StubAdapter(statusCode, body);
  return ApiClient(tokenStore: InMemoryTokenStore(), dio: dio);
}

Future<AppException> _expectFailure(Future<Object?> run) async {
  try {
    await run;
    fail('expected AppException');
  } on AppException catch (e) {
    return e;
  }
}

void main() {
  group('ApiClient error envelope mapping', () {
    test('error envelope code/message/details are surfaced', () async {
      final client = _clientWith(409, jsonEncode({
        'error': {
          'code': 'duplicate_attendance',
          'message': 'Attendance already marked for this date.',
          'details': {'date': '2026-10-13'},
        },
      }));

      final ex = await _expectFailure(client.get('/api/v1/attendance/status'));
      expect(ex.code, 'duplicate_attendance');
      expect(ex.message, contains('already marked'));
      expect(ex.details['date'], '2026-10-13');
    });

    test('outside_geofence code from verify endpoint', () async {
      final client = _clientWith(422, jsonEncode({
        'error': {
          'code': 'outside_geofence',
          'message': 'Location is outside the permitted zone.',
          'details': {'distance_m': 420.5, 'permitted_radius_m': 100.0},
        },
      }));

      final ex = await _expectFailure(
        client.post('/api/v1/attendance/verify', body: const {}),
      );
      expect(ex.code, 'outside_geofence');
      expect(ex.details['distance_m'], 420.5);
    });

    test('non-envelope JSON 401 falls back to token_invalid', () async {
      final client = _clientWith(401, '{"detail":"Not authenticated"}');
      final ex = await _expectFailure(client.get('/api/v1/auth/me'));
      expect(ex.code, 'token_invalid');
    });

    test('non-envelope 429 maps to rate_limited', () async {
      final client = _clientWith(429, '{"detail":"slow down"}');
      final ex = await _expectFailure(client.get('/api/v1/attendance/verify'));
      expect(ex.code, 'rate_limited');
    });
  });
}
