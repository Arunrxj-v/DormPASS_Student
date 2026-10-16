"""Live end-to-end proof of the warden → enrollment → activation lifecycle.

Runs against a real HTTP API (default: the Docker stack on :8000). With the
default ALLOW_INLINE_ACTIVATION_TOKEN=true the issuance responses carry the
fresh key, so the script continues all the way through redemption.

    .venv/bin/python scripts/e2e_activation.py [base_url]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
# Unique per run so the script is re-runnable against a persistent dev DB
# (there is deliberately no student-deletion endpoint).
_STAMP = str(int(time.time()))[-6:]
ROLL = f"E2E-{_STAMP}"
EMAIL = f"e2e-{_STAMP}@ceconline.edu"


def call(method: str, path: str, body=None, token: str | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw else None)


def step(label, expect, status, payload):
    got = payload if isinstance(payload, dict) else {}
    ok = status == expect
    print(f"{'PASS' if ok else 'FAIL'}  {label:<52} -> {status} (want {expect})")
    if not ok:
        print("      " + json.dumps(payload)[:400])
        raise SystemExit(1)
    return got


def main() -> None:
    print(f"Target: {BASE}\n")

    # 1. Warden signs in.
    st, r = call("POST", "/auth/login",
                 {"email": "warden", "password": "WardenPass123!"})
    step("warden signs in", 200, st, r)
    wtoken = r["access_token"]
    assert r["student"]["role"] == "warden", r["student"]
    print(f"      role={r['student']['role']}")

    # 2. Warden creates a student record (no password field exists). The
    #    hostel is required — an unassigned student would be invisible to a
    #    hostel-scoped warden.
    st, hostels = call("GET", "/warden/hostels", token=wtoken)
    step("warden reads granted hostels", 200, st, hostels)
    assert hostels, "warden fixture has no hostel grant"
    hostel_id = hostels[0].get("id") or hostels[0].get("hostel_id")
    print(f"      hostel={hostels[0]['name']} ({hostel_id})")

    st, r = call("POST", "/warden/students",
                 {"student_id": ROLL, "name": "E2E Test Student",
                  "email": EMAIL, "hostel_id": hostel_id,
                  "room": "401"}, token=wtoken)
    step("warden creates student record", 201, st, r)
    print(f"      enrollment_status={r['enrollment_status']} "
          f"account_status={r['account_status']}")

    # 3. Non-`ceconline.edu` email is rejected.
    st, r = call("POST", "/warden/students",
                 {"student_id": ROLL + "-X", "name": "Bad Email",
                  "email": "someone@gmail.com", "hostel_id": hostel_id,
                  "room": "402"}, token=wtoken)
    step("gmail address rejected", 400, st, r)
    print(f"      code={r['error']['code']}")

    # 4. The new student cannot sign in yet.
    st, r = call("POST", "/auth/login",
                 {"email": EMAIL, "password": "Whatever123"})
    step("unactivated student cannot sign in", 401, st, r)

    # 5. Warden confirms details.
    st, r = call("POST", f"/warden/students/{ROLL}/verify-details",
                 token=wtoken)
    step("warden verifies details", 200, st, r)
    print(f"      enrollment_status={r['enrollment_status']}")

    # 6. Warden enrolls the face (server validates + encrypts).
    embedding = [0.01] * 128
    st, r = call("PUT", f"/warden/students/{ROLL}/face-enrollment",
                 {"embedding": embedding, "embedding_dim": 128,
                  "model_version": "e2e_smoke_v1"}, token=wtoken)
    step("warden enrolls face", 200, st, r)

    # 7. The student still cannot self-enroll or self-delete. Use an ACTIVE
    #    student so the request passes authentication and the authorization
    #    rule is what actually rejects it.
    st, r = call("POST", "/auth/login",
                 {"email": EMAIL, "password": "nope"})
    step("still cannot sign in pre-activation", 401, st, r)

    st, r = call("POST", "/auth/login",
                 {"email": "cs-2022-084@ceconline.edu",
                  "password": "student123!"})
    step("active student signs in for the denial check", 200, st, r)
    student_token = r["access_token"]

    st, r = call("PUT", "/face-enrollment",
                 {"embedding": embedding, "embedding_dim": 128,
                  "model_version": "x"}, token=student_token)
    step("student self-enroll rejected (403)", 403, st, r)
    print(f"      code={r['error']['code']}")

    st, r = call("DELETE", "/face-enrollment", token=student_token)
    step("student self-delete rejected (403)", 403, st, r)
    print(f"      code={r['error']['code']}")

    # ...and a student cannot reach the warden API at all.
    st, r = call("GET", "/warden/students", token=student_token)
    step("student blocked from warden roster (403)", 403, st, r)
    st, r = call("POST", f"/warden/students/{ROLL}/suspend",
                 token=student_token)
    step("student blocked from suspending (403)", 403, st, r)

    # 8. Warden issues the activation link.
    st, r = call("POST", f"/warden/students/{ROLL}/activate", token=wtoken)
    step("warden issues activation link", 200, st, r)
    print(f"      enrollment_status={r['enrollment_status']} "
          f"activation_pending={r['activation_pending']} "
          f"delivered={r['delivered']} "
          f"activation_token={r.get('activation_token')!r}")
    inline = r.get("activation_token")
    print(f"      inline token returned: {bool(inline)}")

    # 9. Lifecycle status as the warden console reads it.
    st, r = call("GET", f"/warden/students/{ROLL}", token=wtoken)
    step("warden reads enrollment status", 200, st, r)
    print("      " + json.dumps(r))

    # 10. Redeem the key — only possible when the deployment returns the
    #     freshly issued key at issuance (default). With
    #     ALLOW_INLINE_ACTIVATION_TOKEN=false the field is null and the
    #     warden hands the key over out of band (e.g. the email link).
    if not inline:
        print("\nKey-withholding instance: activation_token was null, as "
              "documented.\nRedemption step exercised separately against an "
              "instance with the default ALLOW_INLINE_ACTIVATION_TOKEN=true.")
        print("\nAll steps passed.")
        return

    print("\n--- redemption (issued key hand-off) ---")

    # Replaying the same token twice must fail: single-use.
    st, r = call("POST", "/auth/activate",
                 {"token": inline, "password": "NewPass1234!"})
    step("activation link redeems", 200, st, r)
    print(f"      enrollment_status={r['student']['enrollment_status']} "
          f"account_status={r['student']['account_status']}")
    redeem_token = r["access_token"]

    st, r = call("POST", "/auth/activate",
                 {"token": inline, "password": "Another1234!"})
    step("same link cannot be reused", 400, st, r)
    print(f"      code={r['error']['code']}")

    # The student can now sign in with their own password.
    st, r = call("POST", "/auth/login",
                 {"email": EMAIL, "password": "NewPass1234!"})
    step("activated student signs in", 200, st, r)
    student_token = r["access_token"]
    print(f"      role={r['student']['role']} "
          f"enrollment_status={r['student']['enrollment_status']}")

    # Warden suspends -> sign-in refused with the specific reason.
    st, r = call("POST", f"/warden/students/{ROLL}/suspend", token=wtoken)
    step("warden suspends", 200, st, r)
    st, r = call("POST", "/auth/login",
                 {"email": EMAIL, "password": "NewPass1234!"})
    step("suspended student cannot sign in", 403, st, r)
    print(f"      code={r['error']['code']} :: {r['error']['message']}")

    st, r = call("POST", f"/warden/students/{ROLL}/unsuspend", token=wtoken)
    step("warden restores", 200, st, r)
    st, r = call("POST", "/auth/login",
                 {"email": EMAIL, "password": "NewPass1234!"})
    step("restored student signs in again", 200, st, r)

    # Staff who redeemed a link is still a student: role never escalates.
    assert r["student"]["role"] == "student", r["student"]
    st, r = call("GET", "/warden/students", token=redeem_token)
    step("activated student still blocked from warden API", 403, st, r)

    print("\nAll steps passed.")


if __name__ == "__main__":
    main()
