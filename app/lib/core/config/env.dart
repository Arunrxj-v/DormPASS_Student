/// Compile-time environment configuration.
///
/// Build with:
///   flutter run --dart-define=API_BASE_URL=http://tailscale-or-lan-ip:8000
/// Defaults target the Android emulator hitting the host machine.
abstract final class Env {
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const appVersion = String.fromEnvironment(
    'APP_VERSION',
    defaultValue: '1.0.0',
  );
}
