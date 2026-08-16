# Text-to-Audio MVP Product and Technical Specification

## 1. Document status

- **Status:** Approved MVP direction
- **Product:** A web application that converts user-provided text into downloadable narrated audio
- **Primary output:** High-quality MP3 with optional JPG/PNG cover art embedded in its ID3 metadata
- **Alternative output:** M4A may be added after compatibility testing, but it is not required for launch
- **Explicitly out of scope:** MP4, video rendering, animated images, GIFs, timelines, and video editing
- **Guiding principle:** KISS—ship the smallest reliable product, measure usage, and add complexity only in response to evidence

## 2. Product promise

> Paste text or upload a plain-text file, select a natural voice and optional cover image, and download a polished narrated MP3.

The MVP is an audio product. A cover image is embedded as MP3 ID3 `APIC` artwork so compatible players can display it, but it does not create a visual or video track. The generated file remains ordinary audio and is cheap to generate, store, and deliver.

## 3. Final media decision

### 3.1 Launch format

The canonical launch artifact is:

| Property | MVP value |
| --- | --- |
| Container | MP3 |
| Audio codec | MPEG Layer III |
| Bitrate | 192 kbps constant bitrate by default; 256 kbps is configurable |
| Sample rate | Preserve the TTS source when practical, otherwise 44.1 kHz |
| Channels | Preserve source; normally mono for narration |
| Metadata | ID3v2.3 for broad player compatibility |
| Cover art | One embedded JPEG or PNG `APIC` frame, front-cover type |
| Text metadata | Title, artist/voice label, album/product name, year, and comment where provided |
| File name | Sanitized project title plus `.mp3` |

MP3 is recommended over M4A for the first release because cover art and metadata support are widely understood across browsers, desktop players, mobile players, podcast tooling, and download workflows. `edge-tts` already produces MP3-compatible audio, minimizing transcoding and reducing both latency and quality loss. M4A/AAC can later be offered as an opt-in second format if user demand or measured file-size savings justify the additional encoding and metadata test matrix.

### 3.2 Cover-art rules

- Accept JPEG and PNG only.
- Maximum upload size: 5 MB.
- Decode the image server-side to verify its real type; do not trust the extension or browser MIME header.
- Reject animated PNG and malformed files.
- Correct EXIF orientation.
- Convert to RGB and downscale to a maximum of 1600 × 1600 pixels.
- Use a square center crop only when the user explicitly chooses it; otherwise preserve aspect ratio.
- Prefer JPEG at approximately 85% quality for photographic images to prevent artwork from dominating MP3 size. The normalized MVP output is JPEG even when the input is PNG; PNG input is accepted for convenience and validation.
- Store the original upload privately only until processing succeeds; retain the normalized artwork with the project according to the retention policy.
- Embed artwork with Python's `mutagen` library. Keep FFmpeg available only for audio probing, concatenation, normalization, or format conversion—not video.

### 3.3 Audio pipeline

1. Normalize Unicode, line endings, whitespace, and paragraph breaks.
2. Validate the server-side character limit and reject empty content.
3. Split text at sentence boundaries into conservative provider-safe chunks.
4. Generate each chunk through an `EdgeTTSProvider` adapter.
5. Retry only transient provider/network failures.
6. Concatenate chunks in order.
7. Probe the result and optionally normalize loudness if tests show inconsistent output.
8. Write ID3 text fields and the normalized image as an `APIC` frame with `mutagen`.
9. Validate that the final file is non-empty, contains an audio stream, has a plausible duration, and contains artwork when requested.
10. Upload it to private Supabase Storage and expose it through a short-lived signed download URL.
11. Delete all temporary worker files in success and failure paths.

Do not transcode merely to reach a nominal bitrate when the upstream MP3 is already suitable. A no-op/copy path should be preferred because re-encoding lossy audio cannot improve quality. The backend should record actual codec, bitrate, duration, and size rather than make unsupported quality claims.

## 4. User experience and MVP scope

### 4.1 In scope

- Public landing page with a concise product explanation and example.
- Free email signup, verification, sign-in, password reset, and sign-out.
- Authenticated dashboard listing the user's projects.
- Paste text or upload UTF-8 `.txt`.
- Curated language and voice selector.
- Short pre-generated voice previews.
- Speech-rate selector with a deliberately small range.
- Optional title and cover-art upload.
- Character count and estimated narration duration.
- Generate audio, observe its state, play it in the browser, and download MP3.
- Retry a failed job without duplicate quota charging when failure is internal.
- Delete a project and its stored objects.
- Free-plan quota and basic abuse controls.
- Responsive and accessible UI.

### 4.2 Out of scope

- MP4 and all video output.
- GIFs, animations, waveforms, visualizers, slides, and timelines.
- Rich-text, PDF, EPUB, and DOCX ingestion.
- Generative cover art.
- Voice cloning.
- User-uploaded voice models.
- Background music and multi-track mixing.
- Collaborative workspaces.
- Public share pages.
- Native mobile applications.
- Payments during the free launch.
- Redis, Celery, Kafka, Kubernetes, and distributed workflow engines.
- Offline model hosting such as Piper until provider economics or reliability justify it.

## 5. Exact technology stack

### 5.1 Frontend

| Concern | Technology | Decision |
| --- | --- | --- |
| Framework | Next.js, App Router, TypeScript | Product UI and lightweight browser-facing routes only |
| UI | React, Tailwind CSS, shadcn/ui | Fast, accessible, locally owned components |
| Forms | React Hook Form and Zod | Typed client validation; backend remains authoritative |
| Authentication | Supabase Auth client | Email/password and email verification |
| Data access | Native `fetch` | Avoid a state library until needed |
| Icons | Lucide | Small consistent icon set |
| Hosting | Vercel | Static/server-rendered frontend delivery |

### 5.2 Backend

| Concern | Technology | Decision |
| --- | --- | --- |
| Language | Python 3.12 | Reuses the existing TTS ecosystem |
| API | FastAPI and Pydantic | Typed REST API and generated OpenAPI schema |
| TTS | `edge-tts` behind a provider interface | Fastest route to natural voices; replaceable later |
| MP3 metadata | `mutagen` | Write ID3 text and `APIC` cover-art frames directly |
| Image processing | Pillow | Verify, orient, resize, and normalize JPG/PNG uploads |
| Audio utility | FFmpeg/ffprobe | Audio-only concatenation, probing, and optional normalization |
| Database/storage client | Supabase Python client | One managed data platform |
| Tests | pytest, pytest-asyncio, HTTPX | Unit and API integration coverage |
| Packaging | `pyproject.toml` with locked dependencies | Reproducible builds |
| Runtime | Containerized API and worker on Railway, Render, or Fly.io | Long-running Python and system binaries are supported |

### 5.3 Managed services and operations

| Concern | Technology |
| --- | --- |
| Identity | Supabase Auth |
| Database | Supabase PostgreSQL |
| Object storage | Private Supabase Storage buckets |
| Frontend hosting | Vercel |
| Backend hosting | One container platform with separate API and worker commands if async mode is enabled |
| Source/CI | GitHub and GitHub Actions |
| Errors | Sentry for frontend and backend |
| Logs | Structured JSON logs from FastAPI and worker |
| Analytics | PostHog or Plausible after the core funnel is working |

## 6. Architecture

```text
Browser
  |
  | HTTPS + Supabase access token
  v
Next.js on Vercel
  |-- renders marketing/authenticated UI
  |-- performs only lightweight session/UI routes
  |-- never runs TTS, FFmpeg, image processing, or large uploads
  |
  +---------------------> Supabase Auth
  |
  v
FastAPI container
  |-- verifies Supabase JWT
  |-- validates projects and quotas
  |-- issues signed upload/download URLs
  |-- runs short generation synchronously only under a measured threshold
  |-- otherwise creates/serves job state
  |
  +---------------------> Supabase PostgreSQL
  +---------------------> Supabase private Storage
  |
  v
Standalone Python worker container
  |-- claims PostgreSQL jobs with a service-only Supabase key
  |-- Piper TTS model and local inference
  |-- Pillow and mutagen
  `-- FFmpeg for WAV-to-MP3 encoding only
```

### 6.1 Architectural decision: media generation stays off Vercel

Vercel/Next.js is strictly the frontend and may expose only lightweight routes such as an auth callback or frontend-specific proxy where necessary. It must not:

- Execute `edge-tts` generation.
- Invoke FFmpeg or ffprobe.
- Decode or resize cover images.
- Concatenate audio.
- Embed ID3 artwork.
- Hold a request open for long media work.
- Proxy large media bytes when a signed Storage URL can upload/download directly.

This boundary avoids serverless execution-duration risk, ephemeral-filesystem constraints, binary packaging complexity, memory spikes, and duplicated backend logic. All media work belongs in the standalone worker container. The FastAPI deployment only validates requests, creates jobs, serves status, and issues signed URLs.

### 6.2 Synchronous versus asynchronous processing

Implement one service function, `generate_audio(project_id)`, usable by both execution modes. Begin with a measured hybrid policy rather than two distinct pipelines:

- The API may process synchronously only when text is below an environment-configured limit and a staging benchmark demonstrates comfortable completion within the backend request timeout.
- Suggested initial synchronous experiment: up to 1,500 characters with a hard application timeout of 20 seconds.
- Production should default to asynchronous if provider latency is variable or the platform request limit leaves insufficient safety margin.
- Larger work always becomes a job and immediately returns `202 Accepted`.
- The UI must handle both responses through the same project-status screen.
- Never select a path based solely on an optimistic duration estimate. Record real latency by character count and voice.

For maximum launch reliability, the recommended default is **asynchronous for every generation**. It adds one jobs table and one worker loop, but prevents provider latency from becoming an HTTP failure and lets users close the tab. If benchmarks establish that short requests are consistently safe, the synchronous fast path can be enabled later through configuration without changing the UI or media service.

### 6.3 KISS job queue

Use PostgreSQL rather than adding Redis:

1. Create a `queued` job in the same transaction as the project.
2. A worker claims one due job atomically with `FOR UPDATE SKIP LOCKED`.
3. Commit the claim before doing external work.
4. Record simple stages: `queued`, `generating`, `tagging`, `uploading`, `ready`, or `failed`.
5. Retry transient failures at 30 seconds, 2 minutes, and 10 minutes.
6. A periodic recovery query requeues stale locks.
7. Make output paths and usage accounting idempotent.

Do not add real-time sockets. Poll `GET /v1/projects/{id}` every 2–3 seconds while the state is active and stop in a terminal state.

## 7. Monorepo structure

```text
/
├── frontend/
│   ├── app/                    # Next.js routes and layouts
│   ├── components/             # Reusable product UI
│   ├── lib/                    # Auth, API client, validation, utilities
│   ├── public/                 # Static public assets
│   └── tests/                  # Frontend tests
├── backend/
│   ├── app/
│   │   ├── api/routes/         # Thin FastAPI route handlers
│   │   ├── core/               # Config, auth, logging, errors
│   │   ├── db/                 # Supabase/database access
│   │   ├── media/              # Chunking, audio, images, ID3
│   │   ├── models/             # Internal domain objects
│   │   ├── schemas/            # Pydantic request/response types
│   │   ├── services/           # Project, quota, storage orchestration
│   │   └── worker/             # Claim loop and job execution
│   └── tests/
├── supabase/
│   └── migrations/             # Versioned schema and RLS SQL
├── docs/                       # ADRs and operational runbooks
├── legacy/                     # Original proof of concept, preserved unchanged
└── spec.md                     # This source-of-truth product specification
```

Routes must remain thin. Media modules should not know about HTTP, and route handlers should not construct FFmpeg commands or ID3 frames.

## 8. Frontend specification

### 8.1 Routes

- `/` — landing page, example, free-plan explanation, signup CTA.
- `/auth/sign-up` — email/password signup.
- `/auth/sign-in` — signin.
- `/auth/callback` — Supabase confirmation callback.
- `/auth/forgot-password` — reset flow.
- `/dashboard` — quota summary and project history.
- `/projects/new` — single-page creation form.
- `/projects/[id]` — processing, playback, metadata, download, retry, and deletion.
- `/settings` — profile and account deletion.
- `/privacy` and `/terms` — launch policies.

### 8.2 New-project form

- Title, optional but defaulted from the first words of the text.
- Textarea or UTF-8 `.txt` upload.
- Live character count and server-provided remaining quota.
- Language and curated voice selector.
- Pre-generated voice preview; do not generate arbitrary preview audio on demand.
- Speech rate: `slow`, `normal`, or `fast` mapped to controlled provider values.
- Optional JPEG/PNG cover art with client preview.
- Optional artist/author field.
- Review summary and a single **Generate audio** action.

### 8.3 Project page

- Status and current stage.
- Clear failure reason with retry when retry is allowed.
- Native HTML audio player when ready.
- Cover-art preview.
- Duration, size, voice, language, and creation time.
- Download MP3 using a newly requested signed URL.
- Delete action with confirmation.

### 8.4 Visual and accessibility direction

- Calm creator-tool aesthetic: neutral background, one accent color, restrained shadows, large readable typography.
- Mobile-first responsive layout.
- Full keyboard navigation and visible focus.
- Proper labels, descriptions, errors, and live status announcements.
- WCAG AA color contrast.
- No fake progress percentages; show honest stages.
- Respect reduced motion.

## 9. API contract

All authenticated endpoints use `Authorization: Bearer <supabase-access-token>`, UUID identifiers, UTC timestamps, and a versioned `/v1` prefix.

### 9.1 Endpoints

```text
GET    /health
GET    /v1/voices?locale=en-US
POST   /v1/uploads/cover-art
POST   /v1/projects
GET    /v1/projects
GET    /v1/projects/{project_id}
POST   /v1/projects/{project_id}/retry
POST   /v1/projects/{project_id}/download
DELETE /v1/projects/{project_id}
GET    /v1/me/usage
DELETE /v1/me
```

`POST /v1/uploads/cover-art` validates metadata and returns a short-lived signed direct-upload target. The browser uploads directly to private Storage; it does not stream the image through Vercel.

### 9.2 Create-project request

```json
{
  "title": "Quarterly report",
  "text": "Narration text...",
  "voice_id": "en-US-AriaNeural",
  "speech_rate": "normal",
  "author": "Example Author",
  "cover_asset_id": "optional-uuid",
  "output_format": "mp3"
}
```

The response is either:

- `201 Created` with a ready project only when a configured synchronous path completed safely; or
- `202 Accepted` with the project in `queued`/`processing` state.

### 9.3 Error shape

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Your free monthly character allowance has been reached.",
    "request_id": "uuid"
  }
}
```

Stable codes include `AUTH_REQUIRED`, `FORBIDDEN`, `INVALID_TEXT`, `TEXT_TOO_LONG`, `INVALID_COVER`, `VOICE_UNAVAILABLE`, `QUOTA_EXCEEDED`, `GENERATION_FAILED`, and `INTERNAL_ERROR`.

## 10. Data model

### `profiles`

```text
id                  uuid primary key references auth.users
display_name        text null
plan                text not null default 'free'
monthly_char_limit  integer not null
created_at          timestamptz not null
updated_at          timestamptz not null
```

### `projects`

```text
id                   uuid primary key
user_id              uuid not null
title                 text not null
source_text           text not null
character_count       integer not null
voice_id               text not null
locale                 text not null
speech_rate            text not null
author                 text null
output_format          text not null default 'mp3'
cover_asset_id         uuid null
 status                 text not null
duration_ms            integer null
output_size_bytes      bigint null
output_bitrate         integer null
created_at             timestamptz not null
updated_at             timestamptz not null
deleted_at             timestamptz null
```

### `jobs`

```text
id             uuid primary key
project_id     uuid not null unique
user_id        uuid not null
status         text not null
stage          text not null
attempt        integer not null default 0
max_attempts   integer not null default 3
locked_at      timestamptz null
locked_by      text null
next_run_at    timestamptz not null
error_code     text null
error_detail   text null
created_at     timestamptz not null
started_at     timestamptz null
finished_at    timestamptz null
```

### `assets`

```text
id              uuid primary key
project_id      uuid null
user_id         uuid not null
kind            text not null       # cover_original, cover_normalized, mp3
storage_path    text not null
content_type    text not null
size_bytes      bigint not null
checksum        text null
created_at      timestamptz not null
expires_at      timestamptz null
```

### `usage_ledger`

```text
id               uuid primary key
user_id          uuid not null
project_id       uuid not null
characters       integer not null
event_type       text not null       # reserve, consume, refund
billing_period   date not null
created_at       timestamptz not null
```

Row-level security must isolate every user-owned row. Only the backend service role may transition jobs or write generated output. Storage buckets remain private, paths begin with the owner's user ID, and downloads use short-lived signed URLs.

## 11. Free-plan policy and safety

Initial configurable defaults:

- 3 completed audio projects per month.
- 10,000 characters per project.
- 20,000 characters per month.
- One active job per account.
- 5 MB cover-art upload.
- Generated artifacts retained for 14 days.
- Verified email required before generation.

Enforce limits in FastAPI, not only in the UI. Reserve characters transactionally when accepting a project, consume them on success, and refund them on an attributable internal failure. Add rate limiting to signup-sensitive and generation endpoints. CAPTCHA is deferred until abuse appears but must be easy to enable.

Public signup remains disabled in local development, preview environments, and any deployment that has not yet published the required privacy, retention, deletion, terms, and acceptable-use policies. Enabling it is a release gate, not a side effect of wiring Supabase Auth.

## 12. Security, privacy, and reliability

- Verify JWT issuer, audience, signature, and expiry in FastAPI.
- Authorize ownership for every project, asset, retry, download, and deletion.
- Never ship Supabase service credentials to the browser.
- Use private buckets and short-lived upload/download URLs.
- Validate image bytes through Pillow and protect against decompression bombs.
- Sanitize download names; use generated object paths.
- Invoke FFmpeg with an argument array, never interpolated shell input.
- Apply strict request and upload size limits.
- Restrict CORS to known frontend origins.
- Do not log source text, auth tokens, signed URLs, or media bytes.
- Use per-job temporary directories and guaranteed cleanup.
- Pin dependencies and run dependency/security scans in CI.
- Publish privacy, retention, deletion, terms, and acceptable-use policies before public signup.
- Make job processing and usage accounting idempotent.
- Use structured logs with request, project, and job IDs but no sensitive content.

## 13. Testing and quality gates

### Backend unit tests

- Unicode and whitespace normalization.
- Sentence-aware chunking and boundary cases.
- Character/quota reservation, consumption, and refund.
- Voice validation and rate mapping.
- Image format verification, orientation, resize, and size limits.
- ID3 fields and `APIC` artwork generation.
- Filename and object-path sanitization.
- Job state transitions, retry classification, and stale-lock recovery.
- Authentication and cross-user authorization.

### Media integration tests

Use a tiny deterministic, valid MP3 fixture or local fake provider in ordinary CI rather than calling the live TTS provider. The fake provider may use the system FFmpeg binary to create short silent audio; it must never call a network service. Assert:

- The output opens as a valid MP3.
- Duration is plausible.
- The MP3 audio stream is present and non-empty.
- Expected ID3 text frames are present.
- Cover artwork bytes and MIME type are correct when supplied.
- Output without artwork remains valid.
- Temporary files are cleaned up.

Run a small opt-in live-provider smoke test on a schedule or before release, not on every pull request.

### API integration tests

- Unauthorized request returns `401`.
- Cross-user access is denied.
- Project creation and job creation are atomic.
- Repeated client submissions use an idempotency key and do not double-charge.
- Ready projects receive expiring signed URLs.
- Deletion removes or schedules removal of every object.
- Failed generation produces a stable public error and private diagnostic.

### Frontend and end-to-end tests

- Authentication guards and callbacks.
- Form validation and character counter.
- Cover preview and invalid-image errors.
- Honest processing stages and terminal failure state.
- Audio playback and download.
- Keyboard and accessibility smoke checks.
- Complete test-user journey from signup to deletion.

### CI gates

- Frontend format, lint, type-check, unit tests, and production build.
- Backend format, lint, type-check, unit/integration tests, and container build.
- Database migration validation.
- Secret and dependency scanning.

## 14. Delivery sequence

To keep each change independently verifiable, implement the MVP in these local-first slices:

1. **Media foundation:** normalization, conservative chunking, provider adapters, valid local MP3 fixture, artwork validation, ID3/APIC, and media tests.
2. **Local application flow:** typed project/job models, SQLite-backed repositories, generation service, status polling endpoints, and local filesystem storage. This slice uses fake TTS by default and requires no Supabase credentials. An in-process background task is acceptable as a development adapter only; it is not the production worker or a durable queue.
3. **Managed boundary:** Supabase migrations, Auth/JWT verification, private Storage signed URLs, RLS, quota ledger, and a worker claim loop. Validate locally against a disposable Supabase-compatible environment before any hosted change.
4. **Product surface:** authenticated Next.js routes, accessible project form/status UI, and end-to-end tests.

Do not start with hosted deployment, public signup, or production data. Each slice must pass its relevant quality gates before the next slice begins.

## 14. Metrics funnel and operating metrics

### Acquisition-to-value funnel

1. Landing-page unique visitor.
2. Signup started.
3. Email verified.
4. New-project form opened.
5. Valid text entered.
6. Generation submitted.
7. Generation completed successfully.
8. Audio played.
9. MP3 downloaded.
10. A second project submitted within 7 or 30 days.

Measure conversion and median time between adjacent steps. The north-star activation event is **a verified user downloading their first successfully generated MP3**. The primary retention signal is a second successful generation.

### Product quality metrics

- Generation success rate by voice, locale, and text-size bucket.
- Submission-to-ready median and p95 latency.
- Queue wait and processing duration separately.
- Download rate among completed projects.
- Retry and terminal-failure rates by stage/error code.
- Cover-art adoption rate.
- Characters generated per active user.
- Day-7 and day-30 returning creator rate.

### Cost and capacity metrics

- TTS request count and latency.
- Backend CPU and memory per completed project.
- Stored bytes and egress bytes per project.
- Average MP3 size and duration.
- Cost per completed/downloaded project.
- Active-job concurrency and oldest queued-job age.
- Free quota consumption and suspected-abuse rate.

Initial launch targets should include at least 95% success for valid short inputs, zero known cross-user data access, and a measured cost per activated user that supports the configured free quota.

## 15. Implementation plan optimized for Codex, speed, tokens, and cost

### 15.1 Recommendation: supervised vertical slices, not one unattended mega-run

Do **not** use a single giant one-shot implementation prompt and leave it running day and night. That approach appears fast but tends to spend more tokens and human time because late discovery of an authentication, schema, deployment, or media assumption causes broad rework. It also makes reviews and rollback difficult.

Use a **two-day, checkpointed build composed of complete vertical slices**. Each slice should end with executable checks and a commit. Codex can work continuously within a slice, but a human should make short decisions at high-leverage checkpoints. This is typically faster overall than either constant micromanagement or an entirely unattended build.

### 15.2 Context and token-efficiency rules

- Treat this file as the source of truth; do not repeatedly restate the full product brief in prompts.
- Give each Codex run one bounded outcome and explicit acceptance commands.
- Ask Codex to inspect the existing state and continue, rather than regenerate scaffolding.
- Commit after every green vertical slice so regressions are cheap to isolate.
- Keep one stack and one implementation path; do not ask for multiple framework alternatives.
- Prefer deterministic fixtures over repeated network TTS calls.
- Run narrow tests during development and the full suite at each checkpoint.
- Request human input only for credentials, provider selection, visual approval, and decisions that materially change scope.
- Avoid parallel agents editing shared foundational files. Parallelize only independent work such as documentation review versus isolated tests.
- Keep generated logs concise and have Codex summarize failures instead of pasting enormous build output into subsequent prompts.

### 15.3 Day 1: foundation and end-to-end backend slice

#### Slice A — workspace and contracts (approximately 2–3 hours)

- Scaffold installable Next.js and FastAPI applications.
- Add root developer commands and environment examples.
- Add formatting, linting, typing, tests, and CI.
- Create Supabase migrations and RLS policies.
- Define API schemas and generate or document the frontend contract.
- Add a local fake TTS provider.

**Checkpoint:** clean install, database schema review, frontend build, backend tests, and container build.

#### Slice B — media engine (approximately 3–4 hours)

- Implement normalization and sentence chunking.
- Implement `TTSProvider`, fake provider, and `EdgeTTSProvider`.
- Implement concatenation/probing with the smallest necessary FFmpeg surface.
- Implement Pillow cover normalization.
- Implement mutagen metadata/artwork writing.
- Test deterministic output fixtures and cleanup.

**Checkpoint:** a command/service test produces a valid tagged MP3 with and without artwork.

#### Slice C — authenticated project flow (approximately 3–4 hours)

- Implement JWT verification and ownership.
- Implement projects, assets, jobs, usage ledger, and signed URLs.
- Implement worker claiming, generation, retries, and status.
- Exercise the API with fake TTS locally.

**Checkpoint:** an authenticated API request creates a project and reaches a downloadable ready state without Vercel participating in media work.

### 15.4 Day 2: product UI, live integration, and launch hardening

#### Slice D — usable frontend (approximately 4–5 hours)

- Build landing and auth pages.
- Build dashboard, project form, cover preview, voice selection, and project status.
- Add audio player, download, retry, and deletion.
- Add responsive/accessibility behavior.

**Checkpoint:** full fake-provider browser journey passes.

#### Slice E — live services and troubleshooting (approximately 3–4 hours)

- Connect a development Supabase project.
- Run migrations and verify RLS with two users.
- Enable a small live edge-tts smoke test.
- Benchmark generation by character-size buckets.
- Choose async-by-default or enable the small synchronous threshold using measured results.
- Deploy frontend and backend/worker previews.

**Checkpoint:** real text produces a playable private MP3 with expected artwork and metadata in the deployed preview.

#### Slice F — release checks (approximately 2–3 hours)

- Add rate limiting, quotas, retention, account deletion, error reporting, and structured metrics.
- Run cross-user security tests, E2E, production builds, and smoke tests.
- Document deployment, rollback, backup, and common-failure runbooks.

**Checkpoint:** invite-only launch approval. Public free signup follows after monitoring the preview under realistic use.

### 15.5 When unattended work is appropriate

Codex can safely run unattended within bounded tasks such as implementing unit-tested chunking, generating migrations from an approved schema, building static UI components from an approved design, or fixing a known finite test list. It should not autonomously choose production credentials, weaken RLS to make tests pass, alter quotas, publish deployments, or broaden product scope.

### 15.6 Realistic duration

The two-day schedule is an aggressive build sprint for a functional internal alpha when credentials and hosting accounts are ready and one decision-maker can answer blockers promptly. Allow an additional 1–3 days for production polish, email deliverability, browser compatibility, security review, deployment surprises, and real-user feedback. The fastest responsible path is therefore:

1. Two focused build days.
2. An invite-only alpha.
3. One short hardening cycle driven by measured failures.
4. Public free signup only after quota, retention, monitoring, and deletion are verified.

## 16. Delivery phases and acceptance criteria

### Phase 0 — foundation

- Reproducible local installs.
- Frontend and backend start independently.
- Backend container includes only required audio/image binaries.
- CI runs baseline quality gates.
- Environment variables are documented.

### Phase 1 — media engine

- Text chunks reliably.
- Fake and live TTS providers implement the same interface.
- MP3 is valid with and without cover art.
- Metadata can be inspected programmatically.
- Temporary data is cleaned up.

### Phase 2 — backend product flow

- Authenticated project creation is quota-protected.
- Async job survives browser disconnect.
- Assets are private and owned.
- Signed downloads expire.
- Retries are safe and idempotent.

### Phase 3 — frontend

- A new user can sign up, create, monitor, play, download, and delete audio without command-line access.
- Forms are accessible and responsive.
- Errors are actionable.
- Vercel performs no media processing.

### Phase 4 — controlled launch

- Two-user isolation test passes.
- Retention and account deletion pass.
- Monitoring and alerting are active.
- Real-provider performance is measured.
- Free quota is configured from observed cost.
- Privacy, terms, and acceptable use are published.

## 17. Decision log

1. **Audio, not video:** MP4, video, GIF, and visual rendering are removed from MVP.
2. **MP3 first:** MP3 plus ID3 cover art is the canonical launch artifact; M4A is deferred pending demand and compatibility tests.
3. **Media off Vercel:** Next.js/Vercel handles product UI and only lightweight routes. FastAPI/container infrastructure owns all media work.
4. **Async-safe design:** One generation service supports both modes, with asynchronous processing recommended by default.
5. **PostgreSQL queue first:** avoid Redis/Celery until measured scale requires it.
6. **Managed product primitives:** Supabase provides authentication, PostgreSQL, and private storage.
7. **Provider abstraction:** launch with edge-tts while preserving an explicit replacement seam.
8. **Checkpointed Codex execution:** use two focused build days and tested vertical slices rather than one unreviewed mega-run.
