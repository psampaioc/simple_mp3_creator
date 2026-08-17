# Simple MP3 Creator

An audio-only text-to-MP3 application. The repository is organized as a small full-stack monorepo: `frontend/` contains the Next.js product UI, `backend/` contains the FastAPI API and media engine, `supabase/` contains database migrations and security policies, and `legacy/` preserves the original prototype.

**Repository status verified:** 2026-08-17. The checkout now includes the TXT/PDF/DOCX upload and extraction path, but the new migration, worker dependencies, and deployed managed flow still require validation before release.

## Local development

```bash
cp .env.example .env
make install
make backend   # terminal 1
make frontend  # terminal 2
```

The local backend uses the deterministic fake TTS provider by default. Set `TTS_PROVIDER=edge-tts` only for an intentional live smoke test.

## Day 1 boundaries

Day 1 provides the runnable foundation, deterministic media pipeline, local project/job flow, and initial Supabase schema. Production deployment, credentials, public signup, and production database changes remain out of scope.

## Hosted runtime rule

The site is already live. Product validation must use the deployed Vercel frontend/API, Supabase, and the GitHub Actions media worker. Do not start or use the local FastAPI API, SQLite flow, local worker, or local audio generation for product behavior—even during development. A local frontend is allowed only for visual work and must be configured with an explicit deployed `NEXT_PUBLIC_API_URL`; there is no localhost fallback.

For the hosted flow, the FastAPI API creates the Supabase job and dispatches `.github/workflows/media-worker.yml`. GitHub Actions is the only supported media-generation path; it claims the job, generates and uploads the private MP3, and updates Supabase status.

## Planned document upload

The planned upload flow supports `.txt`, `.pdf`, and `.docx`: the browser uploads the private source file to Supabase Storage, the hosted worker extracts and normalizes text, and the existing TTS job generates the MP3. The source remains subject to size, type, character, and privacy limits. OCR for scanned PDFs and legacy `.doc` files are intentionally deferred.

This section records the 2026-08-17 repository audit and implementation decision; it does not claim that the feature is already deployed.
