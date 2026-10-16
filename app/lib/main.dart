import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/routing/app_router.dart';
import 'core/theme/app_colors.dart';
import 'core/theme/app_theme.dart';
import 'core/widgets/common.dart';
import 'features/auth/activate_screen.dart' show tokenFromActivationUri;
import 'features/auth/auth_providers.dart';

/// Native hand-off for `hostelpass://` VIEW intents (the emailed activation
/// link). The Flutter engine only auto-delivers http(s) app links, so
/// MainActivity reads the launch URI itself and forwards it here: the cold
/// start once via `getInitialLink`, later taps via the `onLink` callback.
const _deepLinkChannel = MethodChannel('hostelpass/deep_links');

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
    ),
  );
  runApp(const ProviderScope(child: HostelPassApp()));
}

class HostelPassApp extends ConsumerStatefulWidget {
  const HostelPassApp({super.key});

  @override
  ConsumerState<HostelPassApp> createState() => _HostelPassAppState();
}

class _HostelPassAppState extends ConsumerState<HostelPassApp> {
  @override
  void initState() {
    super.initState();
    // Validate any stored session before the router makes decisions.
    Future.microtask(
      () => ref.read(authControllerProvider.notifier).restoreSession(),
    );
    _initDeepLinks();
  }

  /// Registers the native link handler first (so no tap can be missed),
  /// then collects the cold-start URI the activity captured for us.
  Future<void> _initDeepLinks() async {
    _deepLinkChannel.setMethodCallHandler((call) async {
      if (call.method == 'onLink') {
        final link = call.arguments as String?;
        if (link != null) _handleDeepLink(link);
      }
    });
    try {
      final initial =
          await _deepLinkChannel.invokeMethod<String>('getInitialLink');
      if (initial != null) _handleDeepLink(initial);
    } on PlatformException {
      // Native side unavailable (unit tests, other platforms): links stay
      // inert — activation still works via the app's paste-the-code screen.
    } on MissingPluginException {
      // Same: no native channel on this host.
    }
  }

  /// Routes a `hostelpass://activate` URI onto the activation screen with
  /// its token; anything else is intentionally ignored.
  void _handleDeepLink(String link) {
    final uri = Uri.tryParse(link);
    if (uri == null || uri.scheme != 'hostelpass' || uri.host != 'activate') {
      return;
    }
    final token = tokenFromActivationUri(uri);
    final target =
        '/activate${token == null || token.isEmpty ? '' : '?token=$token'}';
    // While the session check is in flight the router subtree is replaced by
    // the loading scaffold (auth.status == unknown), and a go() issued in
    // that window is silently dropped. Wait for the auth state to settle
    // (normally well under a second), then navigate.
    Future<void>(() async {
      while (ref.read(authControllerProvider).status == AuthStatus.unknown) {
        await Future<void>.delayed(const Duration(milliseconds: 40));
      }
      if (mounted) ref.read(appRouterProvider).go(target);
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'HostelPass',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      routerConfig: router,
      builder: (context, child) {
        final auth = ref.watch(authControllerProvider);
        if (auth.status == AuthStatus.unknown) {
          return const Scaffold(
            backgroundColor: AppColors.surface,
            body: LoadingView(),
          );
        }
        return child ?? const SizedBox.shrink();
      },
    );
  }
}
