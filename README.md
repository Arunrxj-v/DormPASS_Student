# DormPASS — Student App

DormPASS Student App is the mobile application used by hostel residents to access their hostel account, perform attendance check-ins, and manage their student profile.

The app communicates with the DormPASS backend API and uses the student's activated account to provide secure hostel attendance services.

---

## Overview

The Student App is designed around a simple student workflow:

1. Receive an account activation email from the hostel warden.
2. Use the activation key to activate the student account.
3. Sign in to the Student App.
4. View hostel and attendance information.
5. Perform attendance check-in using the biometric verification pipeline.
6. View attendance history and account information.

---

## Core Features

### Student Account Activation

Students do not create their own accounts.

The account is created by the hostel warden with the student's details and email address.

The system then sends an activation email to the student's registered email address.

The student uses the activation key from the email to activate their account.

```text
Warden creates student
        ↓
Student email registered
        ↓
Activation email sent
        ↓
Student receives activation key
        ↓
Student activates account
        ↓
Student can sign in
