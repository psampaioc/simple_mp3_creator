# Simple MP3 Creator

An audio-only text-to-MP3 application. The repository is organized as a small full-stack monorepo: `frontend/` contains the Next.js product UI, `backend/` contains the FastAPI API and media engine, `supabase/` contains database migrations and security policies, and `legacy/` preserves the original prototype.

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

