import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/env.dart';
import '../errors/app_exception.dart';

abstract interface class TokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

/// Secures the JWT in Android Keystore-backed storage.
class SecureTokenStore implements TokenStore {
  SecureTokenStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _key = 'hostelpass.access_token';

  @override
  Future<String?> read() => _storage.read(key: _key);
  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);
  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// In-memory store for tests.
class InMemoryTokenStore implements TokenStore {
  String? value;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String token) async => value = token;
  @override
  Future<void> clear() async => value = null;
}

/// Single Dio instance wiring auth headers and normalizing every failure into
/// [AppException] with a machine code from the API contract.
class ApiClient {
  ApiClient({TokenStore? tokenStore, Dio? dio, String? baseUrl})
    : tokenStore = tokenStore ?? SecureTokenStore(),
      dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: baseUrl ?? Env.apiBaseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 20),
              contentType: 'application/json',
            ),
          ) {
    this.dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await this.tokenStore.read();
          if (token != null) options.headers['Authorization'] = 'Bearer $token';
          handler.next(options);
        },
      ),
    );
  }

  final Dio dio;
  final TokenStore tokenStore;

  /// GET helper returning decoded JSON.
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _wrap(() => dio.get(path, queryParameters: query));

  Future<dynamic> post(String path, {Object? body}) =>
      _wrap(() => dio.post(path, data: body));

  Future<dynamic> put(String path, {Object? body}) =>
      _wrap(() => dio.put(path, data: body));

  Future<dynamic> patch(String path, {Object? body}) =>
      _wrap(() => dio.patch(path, data: body));

  Future<dynamic> delete(String path) => _wrap(() => dio.delete(path));

  Future<T> _wrap<T>(Future<Response<T>> Function() run) async {
    try {
      final res = await run();
      return res.data as T;
    } on DioException catch (e) {
      throw _map(e);
    }
  }

  AppException _map(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.badCertificate:
        return const AppException('local_server_unreachable');
      case DioExceptionType.connectionError:
        return const AppException('local_network_unavailable');
      case DioExceptionType.cancel:
        return const AppException('local_cancelled');
      default:
        break; // badResponse / unknown → parsed from the response below
    }

    final res = e.response;
    if (res == null) return const AppException('local_server_unreachable');

    // Parse the {"error":{"code","message","details"}} envelope.
    String code = 'internal_error';
    String? message;
    var details = <String, dynamic>{};
    final data = res.data;
    if (data is Map && data['error'] is Map) {
      final err = data['error'] as Map;
      code = (err['code'] as String?) ?? code;
      message = err['message'] as String?;
      if (err['details'] is Map) {
        details = Map<String, dynamic>.from(err['details'] as Map);
      }
    } else {
      code = switch (res.statusCode) {
        400 => 'invalid_payload',
        401 => 'token_invalid',
        403 => 'forbidden',
        404 => 'not_found',
        409 => 'conflict',
        422 => 'invalid_payload',
        429 => 'rate_limited',
        _ => 'internal_error',
      };
    }
    return AppException(code, message: message, details: details);
  }
}
