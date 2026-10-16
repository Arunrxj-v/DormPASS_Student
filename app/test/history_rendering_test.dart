import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/core/network/api_client.dart';
import 'package:hostelpass/features/attendance/attendance_models.dart';
import 'package:hostelpass/features/attendance/attendance_repository.dart';
import 'package:hostelpass/features/attendance/scan_flow_controller.dart';
import 'package:hostelpass/features/attendance_history/history_screen.dart';
import 'package:hostelpass/features/auth/auth_providers.dart';
import 'package:hostelpass/features/auth/auth_repository.dart';

class _FakeAttendanceRepository extends AttendanceRepository {
  _FakeAttendanceRepository(this._page, this._summary)
    : super(ApiClient(tokenStore: InMemoryTokenStore()));

  final PagedRecords _page;
  final AttendanceSummary _summary;

  @override
  Future<PagedRecords> history({
    String? month,
    String? status,
    int page = 1,
    int pageSize = 20,
  }) async => _page;

  @override
  Future<AttendanceSummary> summary({String? month}) async => _summary;
}

class _FakeAuthController extends AuthController {
  @override
  AuthState build() => const AuthState(
    AuthStatus.authenticated,
    Student(
      id: 's1',
      studentId: 'CS-2022-084',
      name: 'Rohan Sharma',
      role: 'student',
      accountStatus: 'active',
    ),
  );
}

AttendanceRecord _record({
  required String reference,
  required String status,
  String? outcome,
}) => AttendanceRecord(
  reference: reference,
  date: '2026-10-12',
  status: status,
  outcome: outcome,
  recordedAtLocal: '2026-10-12T20:42:00',
  distanceM: 32.1,
  accuracyM: 8.4,
  faceSimilarity: 0.86,
);

void main() {
  Widget wrap(PagedRecords page, AttendanceSummary summary) => ProviderScope(
    overrides: [
      attendanceRepositoryProvider.overrideWithValue(
        _FakeAttendanceRepository(page, summary),
      ),
      authControllerProvider.overrideWith(_FakeAuthController.new),
    ],
    child: const MaterialApp(home: HistoryScreen()),
  );

  final summary = AttendanceSummary(
    month: '2026-10',
    present: 20,
    absent: 2,
    outpass: 1,
    ratePercent: 87.0,
    daysAccounted: 23,
    totalDays: 31,
    passThresholdPercent: 85,
    eligibilitySafe: true,
  );

  testWidgets('renders performance metrics and log rows', (tester) async {
    final page = PagedRecords(
      items: [
        _record(reference: 'HP-2026-1012-2042', status: 'present', outcome: 'verified'),
        _record(reference: 'HP-2026-1011-2118', status: 'pending', outcome: 'pending_review'),
        _record(reference: 'HP-2026-1010-2105', status: 'absent'),
      ],
      page: 1,
      totalPages: 1,
      hasMore: false,
    );

    await tester.pumpWidget(wrap(page, summary));
    // Allow the initState post-frame reload() to resolve.
    await tester.pumpAndSettle();

    expect(find.text('Rohan Sharma'), findsOneWidget);
    expect(find.text('CS-2022-084'), findsOneWidget);

    // Performance card values.
    expect(find.text('Present'), findsOneWidget);
    expect(find.text('20'), findsOneWidget);
    expect(find.text('Absent'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('87.0%'), findsOneWidget);

    // Log rows with honest status labels. The row renders the reference as a
    // short chip (last 4 chars of "HP-2026-1012-2042"); badges uppercase.
    expect(find.text('2042'), findsOneWidget);
    expect(find.text('PENDING REVIEW'), findsOneWidget);
    expect(find.text('ABSENT'), findsWidgets); // metric label row + badge
    expect(find.text('08:42 PM'), findsWidgets); // present + pending rows
  });

  testWidgets('shows honest empty state when there are no records', (tester) async {
    final empty = PagedRecords(items: const [], page: 1, totalPages: 1, hasMore: false);
    await tester.pumpWidget(wrap(empty, summary));
    await tester.pumpAndSettle();

    expect(find.text('No records for October 2026.'), findsOneWidget);
  });
}
