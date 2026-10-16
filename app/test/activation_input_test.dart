import 'package:flutter_test/flutter_test.dart';
import 'package:hostelpass/features/auth/activate_screen.dart';

/// The warden hands the student a raw activation KEY through WhatsApp; links
/// (deep link, hosted `#token=` fragment, legacy `?token=` query) are the
/// secondary path. These tests lock in that every one of those shapes
/// resolves to the same raw key the backend generated — and that key
/// characters (`-`, `_` — urlsafe base64) are never corrupted.
void main() {
  // Representative shape of secrets.token_urlsafe(32): urlsafe base64, so `-`
  // and `_` are legitimate KEY characters and must survive untouched.
  const key = 'aB3_-xY9_zQ1wS2kL4mN6pR8uV0-_TgH_JkLmnopQrstuvwxyz12';

  group('resolveActivationInput', () {
    test('passes a bare key through unchanged', () {
      expect(resolveActivationInput(key), key);
    });

    test('strips WhatsApp wrapping but keeps - and _ characters', () {
      final wrapped = 'aB3_-xY9_zQ1wS2kL4mN6pR8uV0-\n_TgH_JkLmnop\nQrstuvwxyz12';
      expect(resolveActivationInput(wrapped), key);
      expect(resolveActivationInput('  $key  '), key);
    });

    test('extracts from the hostelpass deep link (query form)', () {
      expect(
        resolveActivationInput('hostelpass://activate?token=$key'),
        key,
      );
    });

    test('extracts from the hostelpass deep link (path form)', () {
      expect(resolveActivationInput('hostelpass://activate/$key'), key);
    });

    test('extracts from the hosted web link (fragment form)', () {
      // #token=… never reaches server logs — it must still resolve here.
      expect(
        resolveActivationInput('http://localhost:8000/activate#token=$key'),
        key,
      );
    });

    test('extracts from the legacy hosted link (query form)', () {
      expect(
        resolveActivationInput(
          'https://hostel.example.com/activate?token=$key',
        ),
        key,
      );
    });

    test('empty and token-less input stay safe', () {
      expect(resolveActivationInput(''), '');
      expect(resolveActivationInput('   '), '');
      // A URI without any token resolves to its cleaned self — the backend
      // then rejects it with the clear invalid-key message.
      expect(
        resolveActivationInput('https://hostel.example.com/activate'),
        'https://hostel.example.com/activate',
      );
    });
  });

  group('tokenFromActivationUri', () {
    test('reads the query parameter', () {
      final uri = Uri.parse('hostelpass://activate?token=$key');
      expect(tokenFromActivationUri(uri), key);
    });

    test('reads the path form', () {
      final uri = Uri.parse('hostelpass://activate/$key');
      expect(tokenFromActivationUri(uri), key);
    });

    test('returns null when no token is present', () {
      expect(tokenFromActivationUri(Uri.parse('hostelpass://activate')), isNull);
    });
  });
}
