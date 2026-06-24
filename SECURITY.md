# Security

## Secrets
- **No API keys, tokens, or credentials are committed.** The LLM provider key is read at
  runtime from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (env or AWS Secrets Manager).
- `.env` and all `*.key` / `*.pem` / credential patterns are git-ignored. There is no
  `.env.example` with placeholder keys.
- Verified across OpenAI, Anthropic, AWS, GitHub, Slack, Google, Bearer, private-key, and
  high-entropy patterns — zero matches in tracked files.

## Data
- The `data/` corpus is **anonymized**: PII is replaced with placeholders
  (`[EMAIL_ADDRESS_1]`, `[NUMERICAL_PII_1]`, `[DATE_1]`, …). No raw personal data.

## Input validation
- `channel` is user-controlled and becomes a filesystem path (and an `rmtree` target).
  It is validated against a slug allowlist (`^[A-Za-z0-9_-]+$` + known channels) at the
  API boundary (`api._bad_channel`) **and** at the filesystem chokepoint
  (`gitlab._safe`, `researcher.notebook_path`) — defense in depth against path traversal.
- Uploads accept `.txt` only and write via `os.path.basename(...)` into fixed channel
  directories (no path traversal).
- No `exec` / `eval` / `shell=True` / `pickle` anywhere. (The earlier sandbox that
  `exec`'d model-authored code was removed in the knob-based refactor.)
- Cognito JWTs are verified against the pool JWKS with `RS256` pinned (no alg-confusion),
  plus issuer / `token_use` / `client_id` / `aud` checks.

## Authentication
- **Production (AWS) enforces AWS Cognito login.** The deployed box sets `COGNITO_*` in
  its runtime env (via `~/.env`), so `auth.enabled()` is `true` and every `/api/*` call
  requires a valid Cognito JWT (verified — unauthenticated requests get `401`). Cognito
  config is fetched by the SPA at runtime from `/api/auth_config`, so the pool/client IDs
  are *not* baked into the frontend build (they are public identifiers, not secrets).
- **Local dev defaults to open** (no `COGNITO_*` / `APP_PASSWORD` set) for zero friction.
  If you expose a box to a network, set `COGNITO_*` (real login) or `APP_PASSWORD`
  (HTTP Basic) so `/api/run`, `/api/upload`, and `/api/reset` are not world-accessible.
- **CORS is `*` by default** (`backend/api.py`). Restrict `allow_origins` to your
  dashboard's origin in production.
- Serve over HTTPS (the reference AWS deploy puts CloudFront in front).
- The provider key should come from a secrets manager, never an env var baked into an image.

## Reporting
Open a private security advisory on the repository, or contact the maintainer directly.
