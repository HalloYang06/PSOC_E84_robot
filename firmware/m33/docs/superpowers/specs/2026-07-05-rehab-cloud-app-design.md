# Rehab Cloud App Product Design

Date: 2026-07-05

## Goal

Build the first cloud product layer for the rehab arm: phone login, patient profile, device binding, training records, and a cloud rehab-agent API that the Stitch-generated app can consume.

## Real App Source

The real app source is not the M33 firmware repository's historical `origin/APP` branch. It is:

```text
https://github.com/wenjunyong666/ai-.git
branch: app/rehab-arm-mobile-stitch
primary app path: apps/web/public/rehab-arm-mobile/
bridge file: apps/web/public/rehab-arm-mobile/mobile-bridge.js
```

The current app is a Stitch-generated static mobile/PWA surface served from the Next.js app's `public/rehab-arm-mobile/` directory. Backend work must preserve this frontend boundary: Codex writes backend code and API contracts; frontend changes are expressed as Stitch prompts.

## Product Boundary

The app and cloud service are user-facing coordination layers. They may store user data, explain training records, request safe high-level actions, and provide rehab guidance. They must not directly authorize or emit real motor commands. Physical motion remains under the existing safety rule:

```text
JointTrajectory -> NanoPi -> M33 safety/control layer -> motor bus
```

## MVP User Journey

1. The user signs in with a phone number and SMS-style verification code.
2. The user creates or updates a simple patient profile.
3. The user binds a rehab device by scanning a QR code or entering a device claim code.
4. The app displays bound devices, safety status, and recent sessions.
5. The app uploads training session summaries.
6. The user asks the rehab agent questions. The agent uses the user's profile and recent sessions as context.

## Backend Scope

The first backend service lives under `cloud/rehab-platform/` and exposes a JSON API compatible with the current Stitch app. The app already calls these endpoints:

- `POST /api/auth/session`
- `GET /api/rehab-arm/app/v1/public-config`
- `GET /api/rehab-arm/app/v1/catalog`
- `GET /api/rehab-arm/app/v1/me`
- `GET /api/rehab-arm/app/v1/me/workflow`
- `POST /api/rehab-arm/app/v1/me/workflow/actions`
- `GET /api/rehab-arm/app/v1/emg/latest`
- `POST /api/rehab-arm/app/v1/devices/bind`
- `POST /api/rehab-arm/app/v1/devices/{device_id}/legacy-spp/inbound`
- `POST /api/rehab-arm/app/v1/ai-training-drafts/generate`
- `POST /api/rehab-arm/app/v1/ai-training-drafts/{draft_id}/accept`
- `POST /api/rehab-arm/app/v1/training-plans/{plan_id}/sync-to-device`
- `POST /api/rehab-arm/app/v1/devices/{device_id}/ble/messages`

The backend may also expose newer phone-code routes for future Stitch updates:

- `POST /auth/request-code`
- `POST /auth/verify-code`
- `GET /me`
- `PUT /me/profile`
- `POST /devices/claim`
- `GET /devices`
- `POST /sessions`
- `GET /sessions`
- `POST /agent/chat`
- `GET /health`

The service uses a clean internal boundary:

- API routers validate HTTP input and output.
- Service modules own business rules.
- Repository modules persist data through SQLAlchemy.
- Agent modules build safe context and call the configured model provider.

## Frontend Boundary

Frontend implementation is delegated to Stitch. Codex provides only the prompt, API contract, and QA checklist. The UI should feel like a patient-facing rehab companion, not an engineering debug panel. Direct joint move controls remain hidden from normal users. The current `mobile-bridge.js` uses `localStorage` keys `rehabArmMobileApiBase`, `rehabArmAccessToken`, and `rehabArmMobileState`; backend QA should exercise those flows before requesting Stitch changes.

## Data Model

Core records:

- User: phone, display name, role.
- Profile: rehab stage, affected side, notes, safety notes.
- Device: device id, serial number, display name, bound owner, firmware version.
- VerificationCode: phone, hashed code, expiry, consumption state.
- DeviceClaim: one-time claim code, device id, expiry, consumption state.
- TrainingSession: user id, device id, mode, duration, sensor summary, safety events, pain and fatigue scores.
- AgentMessage: user id, role, content, timestamp.

## Safety Rules

- Agent answers must include clear stop/contact-professional guidance when the user reports pain, numbness, dizziness, abnormal oxygen, or unsafe symptoms.
- Agent output is advice only and must not contain low-level motor commands, CAN frames, torque/current targets, or M33 safety overrides.
- Device binding proves account ownership of product data, not motion authority.
- The app may request mode changes only through future safe server/NanoPi contracts; this MVP stores and displays state only.

## Deployment

The service should be deployable to a cloud VM with Docker Compose:

- API container.
- PostgreSQL container.
- Redis container for verification-code and rate-limit ready state.

The MVP can run locally with SQLite for tests and development, while production uses PostgreSQL through `DATABASE_URL`.

Delivery rule:

- After each major milestone, deploy the backend/app integration to the cloud server.
- After deployment, package an installable app build for user testing.
- A milestone is not considered handed off until cloud smoke tests and install-package smoke checks are recorded.

## QA

QA should cover:

- Phone code request and verification.
- Token-protected profile calls.
- Device claim success and one-time reuse failure.
- Session upload and listing.
- Agent response using profile/session context.
- Browser-visible frontend smoke flow after Stitch produces the app.
