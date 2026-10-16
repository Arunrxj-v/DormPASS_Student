import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../theme/app_colors.dart';
import '../../features/admin/admin_wardens_screen.dart';
import '../../features/admin/create_warden_screen.dart';
import '../../features/attendance/attendance_result_screen.dart';
import '../../features/attendance/face_verification_screen.dart';
import '../../features/attendance/location_step_screen.dart';
import '../../features/attendance_history/history_screen.dart';
import '../../features/auth/activate_screen.dart';
import '../../features/auth/auth_providers.dart';
import '../../features/auth/sign_in_screen.dart';
import '../../features/dashboard/home_screen.dart';
import '../../features/profile/profile_screen.dart';
import '../../features/warden/create_student_screen.dart';
import '../../features/warden/student_detail_screen.dart';
import '../../features/warden/warden_dashboard_screen.dart';
import '../../features/warden/warden_enrollment_screen.dart';
import '../../features/warden/warden_students_screen.dart';

final rootNavigatorKey = GlobalKey<NavigatorState>();

/// Which navigation shell the current session should see.
///
/// Role comes from the server-verified `GET /auth/me` payload — never from
/// anything the client stores or edits. Students get the three-tab attendance
/// shell; wardens and admins get the three-tab management shell.
bool _isStaff(AuthState auth) => auth.student?.isWarden ?? false;

/// Student shell: Home · Attendance · Profile.
class _StudentShell extends StatelessWidget {
  const _StudentShell({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    final index = location.startsWith('/attendance')
        ? 1
        : location.startsWith('/profile')
        ? 2
        : 0;

    final headerTitle = switch (index) {
      1 => 'Attendance',
      2 => 'Profile',
      _ => 'Home',
    };

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: Column(
        children: [
          AppHeader(title: headerTitle),
          Expanded(child: child),
        ],
      ),
      bottomNavigationBar: _NavBar(
        index: index,
        onSelect: (i) => switch (i) {
          0 => context.go('/home'),
          1 => context.go('/attendance'),
          _ => context.go('/profile'),
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month),
            label: 'Attendance',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

/// Warden shell: Dashboard · Students · Profile.
///
/// Attendance history and the face-enrollment entry point are deliberately
/// absent — students mark their own attendance, and enrollment is initiated
/// from a student's profile, never from a self-service tab.
class _WardenShell extends StatelessWidget {
  const _WardenShell({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    final index = location.startsWith('/warden/students')
        ? 1
        : location.startsWith('/warden/profile')
        ? 2
        : 0;

    final headerTitle = switch (index) {
      1 => 'Students',
      2 => 'Profile',
      _ => 'Dashboard',
    };

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: Column(
        children: [
          AppHeader(title: headerTitle),
          Expanded(child: child),
        ],
      ),
      bottomNavigationBar: _NavBar(
        index: index,
        onSelect: (i) => switch (i) {
          0 => context.go('/warden/dashboard'),
          1 => context.go('/warden/students'),
          _ => context.go('/profile'),
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.groups_outlined),
            selectedIcon: Icon(Icons.groups),
            label: 'Students',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

class _NavBar extends StatelessWidget {
  const _NavBar({
    required this.index,
    required this.onSelect,
    required this.destinations,
  });

  final int index;
  final ValueChanged<int> onSelect;
  final List<NavigationDestination> destinations;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.card,
        border: Border(top: BorderSide(color: AppColors.hairline)),
      ),
      child: NavigationBar(
        height: 56,
        backgroundColor: AppColors.card,
        indicatorColor: AppColors.primaryTint.withValues(alpha: 0.45),
        selectedIndex: index.clamp(0, destinations.length - 1),
        onDestinationSelected: onSelect,
        destinations: destinations,
      ),
    );
  }
}

final appRouterProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);

  final signedIn = auth.isAuthenticated;
  final staff = signedIn && _isStaff(auth);
  final isAdmin = signedIn && (auth.student?.isAdmin ?? false);

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/home',
    redirect: (context, state) {
      if (auth.status == AuthStatus.unknown) return null;

      final path = state.matchedLocation;
      final onSignIn = path == '/signin';
      final onActivate = path == '/activate';

      // Signed out: only the sign-in and activation screens are reachable.
      if (!signedIn) {
        if (onSignIn || onActivate) return null;
        return '/signin';
      }

      // Signed in: never show the sign-in screen again.
      if (onSignIn) return staff ? '/warden/dashboard' : '/home';

      // Activation is a pre-auth hand-off; once the account is active the
      // route has no further purpose.
      if (onActivate) return staff ? '/warden/dashboard' : '/home';

      final onWardenArea = path.startsWith('/warden');
      final onAdminArea = path.startsWith('/admin');
      final onStudentArea = path.startsWith('/home') ||
          path.startsWith('/attendance') ||
          path.startsWith('/profile');

      // Cross-role access is refused client-side too — the backend rejects
      // these calls with 403 regardless, so this is navigation hygiene only.
      // `/profile` is the student shell's tab; staff have their own copy at
      // `/warden/profile` so each shell keeps its own navigation stack.
      if (staff) {
        // The admin console is admin-only. A warden session that lands here
        // is bounced to its dashboard; every request the screen would make
        // is independently rejected with 403 by require_admin anyway.
        if (onAdminArea && !isAdmin) return '/warden/dashboard';
        if (path == '/profile') return '/warden/profile';
        if (path.startsWith('/home') || path.startsWith('/attendance')) {
          return '/warden/dashboard';
        }
        return null;
      }
      if (!staff && (onWardenArea || onAdminArea)) return '/home';
      if (!staff && onStudentArea) return null;

      return null;
    },
    // A VIEW-intent link arrives as a raw URI (hostelpass://activate?token=…)
    // whose path never matches a route pattern — without this it fell back
    // to the initial location and the emailed token was silently dropped.
    // Normalize it onto the in-app activation screen (which already reads
    // the token via tokenFromActivationUri); anything else unmatched falls
    // back to sign-in, where the redirect above routes an active session to
    // its proper home.
    onException: (context, state, router) {
      final uri = state.uri;
      if (uri.scheme == 'hostelpass' && uri.host == 'activate') {
        final token = tokenFromActivationUri(uri);
        router.go(token == null || token.isEmpty
            ? '/activate'
            : '/activate?token=$token');
        return;
      }
      router.go('/signin');
    },
    routes: [
      GoRoute(
        path: '/signin',
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: '/activate',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => ActivateScreen(
          initialToken: tokenFromActivationUri(state.uri),
        ),
      ),

      // ---------------------------------------------------- student shell
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => _StudentShell(child: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/attendance',
                builder: (context, state) => const HistoryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const ProfileScreen(),
              ),
            ],
          ),
        ],
      ),

      // ------------------------------------------------------- staff shell
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => _WardenShell(child: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/warden/dashboard',
                builder: (context, state) => const WardenDashboardScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/warden/students',
                builder: (context, state) => const WardenStudentsScreen(),
                routes: [
                  GoRoute(
                    path: 'new',
                    parentNavigatorKey: rootNavigatorKey,
                    builder: (context, state) => const CreateStudentScreen(),
                  ),
                  GoRoute(
                    path: ':ref',
                    parentNavigatorKey: rootNavigatorKey,
                    builder: (context, state) => StudentDetailScreen(
                      studentRef: state.pathParameters['ref'] ?? '',
                    ),
                    routes: [
                      GoRoute(
                        path: 'enroll',
                        parentNavigatorKey: rootNavigatorKey,
                        builder: (context, state) => WardenEnrollmentScreen(
                          studentRef: state.pathParameters['ref'] ?? '',
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/warden/profile',
                builder: (context, state) => const ProfileScreen(),
              ),
            ],
          ),
        ],
      ),

      // ------------------------------------------------ admin console
      // Sits on the root navigator so it renders above the staff shell as a
      // distinct section rather than a fourth tab of the warden shell — the
      // two roles have different navigation, and an admin-only tab inside a
      // warden shell would put an admin control one stray redirect away from
      // a warden's screen. Server-side `require_admin` authorizes the calls
      // this screen makes; the redirect below only keeps it out of view.
      GoRoute(
        path: '/admin/wardens',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const AdminWardensScreen(),
        routes: [
          GoRoute(
            path: 'new',
            builder: (context, state) => const CreateWardenScreen(),
          ),
        ],
      ),

      // ---------------------------------------- student attendance flow
      GoRoute(
        path: '/attendance/location',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const LocationStepScreen(),
      ),
      GoRoute(
        path: '/attendance/face',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const FaceVerificationScreen(),
      ),
      GoRoute(
        path: '/attendance/outside',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const OutsideZoneScreen(),
      ),
      GoRoute(
        path: '/attendance/result',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const AttendanceResultScreen(),
      ),
      // NOTE: the student self-enrollment route (`/enroll`) was removed.
      // Enrollment is warden-initiated at /warden/students/:ref/enroll.
    ],
  );
});
