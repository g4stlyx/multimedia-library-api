# Multi-Media Library Application Plan

Last updated: 2026-07-05

## 1. Product Intent

Build a Letterboxd-style media library for multiple media types:

- Movies
- Series
- Books
- Games
- Music albums and tracks

The product is not just a metadata search app. The defensible layer is user-owned cultural memory: library status, ratings, reviews, comments, lists, imports, taste graph, and eventually recommendations.

Core user jobs:

- Search for media quickly.
- Add media to a personal library.
- Track state: planned, in progress, completed, paused, dropped.
- Rate and review media.
- Comment on reviews and lists.
- Import existing history from platforms such as Letterboxd, Steam, Spotify, Goodreads-style CSVs, and other CSV exports.
- Discover canonical pages for media with stable external identifiers.

Core admin jobs:

- Review audit logs.
- Moderate users, reviews, comments, and imported data conflicts.
- Manage media merges and duplicate candidates.
- Monitor provider failures, rate limits, import jobs, and backup jobs.

## 2. Current Repo Assumption

The current repo is an early FastAPI backend scaffold. Existing dependencies indicate:

- FastAPI
- SQLAlchemy
- PostgreSQL via `psycopg2-binary`
- Pydantic settings
- Requests

Plan around FastAPI unless the stack is intentionally changed. Use FastAPI equivalents for the controller/service/DTO/repository separation:

- Routers = controllers
- Schemas = DTOs
- Services = business logic
- Repositories = persistence access
- Providers = external API adapters
- Workers = async/background jobs

Immediate issue found in the current repo:

- `app/database.py` hardcodes the database URL.
- `app/database.py` uses `create_backend`, but SQLAlchemy should use `create_engine`.
- The first implementation step must move configuration to `.env` through `pydantic-settings`.

## 3. High-Level Architecture

Use a modular monolith first. Do not split services early.

Recommended runtime components:

- FastAPI API server
- PostgreSQL primary database
- Redis for rate limiting, queues, locks, and short-lived caches
- RQ, Celery, or Arq workers for async jobs
- Cloudflare in front of the app
- Cloudflare R2 for user-uploaded assets
- SMTP provider for auth emails and backup notifications
- Scheduled worker for nightly backups and provider refreshes

Recommended backend module layout:

```text
app/
  main.py
  core/
    config.py
    security.py
    logging.py
    rate_limit.py
    permissions.py
  db/
    session.py
    base.py
    migrations/
  models/
    user.py
    auth.py
    media.py
    social.py
    import_job.py
    audit.py
    upload.py
  schemas/
    auth.py
    user.py
    media.py
    library.py
    review.py
    import_job.py
    admin.py
  repositories/
    user_repository.py
    media_repository.py
    library_repository.py
    review_repository.py
    audit_repository.py
  services/
    auth_service.py
    media_service.py
    library_service.py
    review_service.py
    import_service.py
    upload_service.py
    admin_service.py
    backup_service.py
  providers/
    base.py
    tmdb.py
    rawg.py
    igdb.py
    google_books.py
    open_library.py
    spotify.py
  workers/
    jobs.py
    ingestion_jobs.py
    import_jobs.py
    email_jobs.py
    backup_jobs.py
  routers/
    auth.py
    media.py
    library.py
    reviews.py
    comments.py
    imports.py
    uploads.py
    admin.py
```

Request flow for search:

```text
User search
  -> normalize query
  -> query local DB first
  -> if enough high-confidence local results: return immediately
  -> if local miss: query provider adapters with provider-specific rate limits
  -> return external results marked as not yet persisted
  -> when user adds a result: upsert canonical media inside a DB transaction
  -> create/update user's library entry
  -> enqueue provider enrichment and image metadata refresh
```

Do not promise "0 ms" local search. Target sub-50 ms database search for common queries after indexes and caching.

## 4. Core Product Model

### Media Types

Use explicit media types instead of a vague `music` type:

- `MOVIE`
- `SERIES`
- `BOOK`
- `GAME`
- `ALBUM`
- `TRACK`

Future:

- `EPISODE`
- `SEASON`
- `PODCAST`
- `COMIC`
- `MANGA`

Series should start as a single trackable media record. Add season/episode tracking later through a parent-child media model.

### User Library Status

Use generic statuses internally and map them to media-specific labels in the frontend:

| Internal status | Movie label | Series label | Book label | Game label | Music label |
| --- | --- | --- | --- | --- | --- |
| `PLANNED` | Will watch | Will watch | Want to read | Will play | Will listen |
| `IN_PROGRESS` | Watching | Watching | Reading | Playing | Listening |
| `COMPLETED` | Watched | Watched | Read | Played | Listened |
| `PAUSED` | Paused | Paused | Paused | Paused | Paused |
| `DROPPED` | Dropped | Dropped | Dropped | Dropped | Dropped |

Also store optional progress:

- `progress_value`
- `progress_total`
- `progress_unit`: pages, episodes, hours, tracks, percent

### Ratings

Use one consistent internal rating system:

- Store integer `rating_value` from 1 to 100.
- Frontend can render 5 stars, 10 points, or percentage.
- Avoid floats for ratings.

### Reviews and Comments

Review model:

- One primary review per user/media pair for MVP.
- Allow editing review text and rating.
- Keep `created_at`, `updated_at`, `deleted_at`.
- Use soft delete for moderation and recovery.

Comments:

- Comments can target reviews, lists, and later media pages.
- Start with flat comments or one-level replies.
- Avoid deeply nested comments in MVP.

## 5. Database Design

Use PostgreSQL.

Recommended extensions:

- `pgcrypto` for UUID generation if DB-generated UUIDs are used
- `pg_trgm` for fuzzy title search
- `unaccent` for accent-insensitive search

Primary IDs:

- Use UUIDs for public-facing IDs.
- Keep provider external IDs in separate tables.

Timestamps:

- Every mutable table should have `created_at` and `updated_at`.
- Moderatable/user-owned content should also have `deleted_at`.

### Main Tables

#### `users`

Purpose: one identity table for normal users and admins.

Fields:

- `id`
- `email`
- `email_normalized`
- `username`
- `username_normalized`
- `display_name`
- `role`: `USER` or `ADMIN`
- `admin_level`: nullable integer, valid only for admins
- `email_verified_at`
- `is_active`
- `is_banned`
- `created_at`
- `updated_at`
- `deleted_at`

Admin level semantics:

- `0`: super admin
- `1`: admin
- `2`: moderator

Use a single `users` table. Splitting admins into a separate table creates duplicate auth flows and increases security risk. If admin-specific profile fields grow later, add `admin_profiles` keyed by `user_id`.

Constraints:

- Unique `email_normalized`
- Unique `username_normalized`
- Check: `role = 'ADMIN'` requires `admin_level in (0,1,2)`
- Check: `role = 'USER'` requires `admin_level is null`

#### `user_credentials`

Purpose: isolate password auth details from profile data.

Fields:

- `user_id`
- `password_hash`
- `password_hash_algorithm`
- `password_hash_params`
- `password_changed_at`
- `failed_login_count`
- `locked_until`
- `created_at`
- `updated_at`

Pepper is never stored in the DB.

#### `refresh_tokens`

Purpose: support 30-day refresh tokens with rotation and revocation.

Fields:

- `id`
- `user_id`
- `token_hash`
- `family_id`
- `expires_at`
- `revoked_at`
- `replaced_by_token_id`
- `reuse_detected_at`
- `ip_address`
- `user_agent_hash`
- `created_at`

Rules:

- Store only token hashes.
- Rotate refresh token on every refresh.
- If an old refresh token is reused, revoke the whole token family.

#### `email_verification_tokens`

Fields:

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `consumed_at`
- `created_at`

#### `password_reset_tokens`

Fields:

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `consumed_at`
- `created_at`

#### `media`

Purpose: canonical local media record.

Fields:

- `id`
- `media_type`
- `canonical_title`
- `normalized_title`
- `original_title`
- `description`
- `release_date`
- `release_year`
- `runtime_minutes`
- `primary_language`
- `country_code`
- `poster_url`
- `backdrop_url`
- `source_priority`
- `data_quality_score`
- `popularity_score`
- `metadata_json`
- `last_synced_at`
- `created_at`
- `updated_at`
- `deleted_at`

`metadata_json` is useful for provider-specific non-core fields, but do not hide important query fields only inside JSON.

#### `media_external_ids`

Purpose: prevent duplicates and support imports.

Fields:

- `id`
- `media_id`
- `provider`
- `provider_media_type`
- `external_id`
- `external_url`
- `confidence`
- `created_at`
- `updated_at`

Examples:

- `tmdb_movie: 27205`
- `tmdb_tv: 1399`
- `imdb: tt1375666`
- `rawg: 3498`
- `igdb: 1020`
- `google_books_volume: abc123`
- `openlibrary_work: OL123W`
- `openlibrary_edition: OL123M`
- `isbn_13: 978...`
- `spotify_album: ...`
- `spotify_track: ...`
- `isrc: ...`

Constraints:

- Unique `(provider, external_id)`
- Index `(media_id, provider)`

#### `media_titles`

Purpose: aliases, translations, alternate titles.

Fields:

- `id`
- `media_id`
- `title`
- `normalized_title`
- `language`
- `region`
- `is_primary`
- `created_at`

Index:

- Trigram index on `normalized_title`

#### `media_images`

Purpose: store external image metadata and internal R2 object references.

Fields:

- `id`
- `media_id`
- `image_type`: poster, backdrop, cover, avatar
- `source`: tmdb, rawg, spotify, r2, etc.
- `external_url`
- `r2_object_key`
- `width`
- `height`
- `content_type`
- `created_at`

For provider images, keep external URLs initially. Do not download all posters at MVP stage unless provider terms or availability require it.

#### `genres` and `media_genres`

Normalize genres enough for filtering but preserve provider raw genres in metadata snapshots.

#### `people` / `companies` / `contributors`

Start simple:

- `contributors`
- `media_contributors`

Fields:

- contributor name
- normalized name
- role: author, director, actor, studio, developer, publisher, artist, composer
- provider IDs

Do not over-model cast/crew until product needs it.

#### `user_media_entries`

Purpose: user library.

Fields:

- `id`
- `user_id`
- `media_id`
- `status`
- `rating_value`
- `progress_value`
- `progress_total`
- `progress_unit`
- `started_at`
- `completed_at`
- `notes_private`
- `is_favorite`
- `source`: manual, import, provider
- `created_at`
- `updated_at`
- `deleted_at`

Constraints:

- Unique `(user_id, media_id)` where `deleted_at is null`

#### `reviews`

Fields:

- `id`
- `user_id`
- `media_id`
- `rating_value`
- `body`
- `contains_spoilers`
- `visibility`: public, followers, private
- `like_count`
- `comment_count`
- `created_at`
- `updated_at`
- `deleted_at`

Constraints:

- Unique `(user_id, media_id)` where `deleted_at is null`

#### `comments`

Fields:

- `id`
- `user_id`
- `target_type`: review, list, media
- `target_id`
- `parent_comment_id`
- `body`
- `created_at`
- `updated_at`
- `deleted_at`

#### `lists` and `list_items`

Purpose: user-created lists.

`lists`:

- `id`
- `user_id`
- `title`
- `description`
- `visibility`
- `created_at`
- `updated_at`
- `deleted_at`

`list_items`:

- `id`
- `list_id`
- `media_id`
- `position`
- `note`
- `created_at`

Constraints:

- Unique `(list_id, media_id)`
- Unique `(list_id, position)`

#### `import_jobs`

Fields:

- `id`
- `user_id`
- `source_platform`
- `status`
- `original_filename`
- `file_r2_object_key`
- `total_rows`
- `processed_rows`
- `successful_rows`
- `failed_rows`
- `created_at`
- `started_at`
- `finished_at`

#### `import_items`

Fields:

- `id`
- `import_job_id`
- `row_number`
- `raw_payload_json`
- `matched_media_id`
- `match_confidence`
- `status`
- `error_code`
- `error_message`
- `created_at`

#### `provider_requests`

Purpose: observability and provider rate-limit debugging.

Fields:

- `id`
- `provider`
- `endpoint`
- `request_hash`
- `status_code`
- `duration_ms`
- `rate_limited`
- `created_at`

Do not log API secrets or full tokens.

#### `audit_logs`

Purpose: immutable user/admin action trail.

Fields:

- `id`
- `actor_user_id`
- `actor_role`
- `action`
- `resource_type`
- `resource_id`
- `ip_address`
- `user_agent_hash`
- `metadata_json`
- `created_at`

Visible only to admin level `0`.

#### `auth_error_logs`

Fields:

- `id`
- `event_type`
- `email_or_username_hash`
- `user_id`
- `ip_address`
- `user_agent_hash`
- `reason`
- `created_at`

Do not store raw passwords, raw tokens, or reset links.

#### `uploads`

Fields:

- `id`
- `user_id`
- `upload_type`
- `r2_object_key`
- `original_filename_sanitized`
- `content_type`
- `byte_size`
- `sha256`
- `width`
- `height`
- `status`
- `created_at`

#### `outbox_events`

Purpose: reliable async side effects.

Fields:

- `id`
- `event_type`
- `payload_json`
- `status`
- `attempt_count`
- `available_at`
- `created_at`
- `processed_at`

Use this for email sends, provider enrichments, imports, and audit-related side effects when transaction consistency matters.

## 6. Search and Deduplication Strategy

The app's long-term data quality depends on deduplication. External IDs are mandatory.

### Upsert Priority

When adding a media item:

1. Exact external provider ID match wins.
2. Strong cross-provider ID match wins:
   - IMDb ID for movies/series
   - ISBN-13 for books
   - ISRC for tracks
   - Spotify ID for Spotify-backed music
3. Fuzzy match within same `media_type`:
   - normalized title
   - release year/date
   - primary creators
   - provider popularity
4. If confidence is below threshold, create a new record but flag duplicate review candidate.

Never auto-merge low-confidence matches. Media merge is an admin action.

### Search Pipeline

Local search:

- Normalize query.
- Search `media.normalized_title` and `media_titles.normalized_title`.
- Boost exact title matches.
- Boost same release year if query includes year.
- Boost popular and high data quality records.
- Filter by media type when user selects a type.

Provider fallback:

- Query only selected media type providers.
- Use timeout limits.
- Return partial provider errors without failing the whole search.
- Cache provider search results briefly in Redis.

### Indexes

Recommended indexes:

- `media(media_type, release_year)`
- `media_external_ids(provider, external_id)` unique
- `user_media_entries(user_id, media_id)` unique active
- `reviews(user_id, media_id)` unique active
- Trigram index on `media.normalized_title`
- Trigram index on `media_titles.normalized_title`
- `audit_logs(created_at)`
- `audit_logs(actor_user_id, created_at)`
- `import_items(import_job_id, status)`

## 7. External API Strategy

Do not couple the app to one provider's response shape. Use provider adapters returning internal DTOs.

Provider adapter interface:

```text
search(query, media_type, limit, market=None) -> list[ProviderSearchResult]
get_details(provider_id, media_type) -> ProviderMediaDetails
get_seed_page(seed_kind, cursor) -> ProviderSeedPage
```

Every provider adapter must handle:

- API key/token injection from settings
- provider-specific rate limiting
- provider-specific timeout
- `429` handling with backoff
- structured error mapping
- request logging without secrets
- source attribution data

### Movies and Series: TMDB

Use TMDB for movie and series search, details, images, popularity, top-rated, and provider IDs.

Important constraints verified from official docs:

- API key registration is required.
- Images are built from `base_url`, `file_size`, and `file_path`.
- TMDB no longer uses the old 40 requests per 10 seconds limit, but still has upper limits around 40 requests per second and requires respecting `429`.

Recommended usage:

- Seed with TMDB `popular`, `top_rated`, `discover`, and details endpoints.
- Fetch external IDs for IMDb mapping when available.
- Store TMDB movie and TV IDs separately because ID namespaces differ by type.
- Store image paths and generated URLs, not downloaded image binaries in MVP.

### Games: RAWG or IGDB

This is a strategic decision because terms matter.

IGDB:

- Uses Twitch OAuth client credentials.
- Most API requests are POST requests.
- Rate limit is 4 requests per second and up to 8 open requests.
- Official docs state the API is free for non-commercial usage under Twitch terms.

RAWG:

- API key required on every request.
- Free tier has request limits and backlink/attribution requirements.
- RAWG terms include no data redistribution.
- The RAWG API page currently contains mixed commercial language, so verify terms directly before launch if the product will monetize.

Recommendation:

- Build both providers behind the same interface if possible.
- For a commercial product, do not bet the catalog solely on IGDB free usage.
- Use one provider as primary and store secondary IDs opportunistically.
- For MVP speed, RAWG is simpler REST; for richer canonical game data, IGDB is strong but licensing/commercial use must be validated.

### Books: Google Books and Open Library

Google Books:

- Good for public search and volume lookups.
- Public data requests can use an API key.
- Volume IDs are stable inside Google Books.

Open Library:

- Good for open IDs, works/editions, covers, and bulk dumps.
- Official usage guidelines discourage using the API as a bulk/high-traffic backend.
- Identified requests with `User-Agent` and contact email have higher rate limits than anonymous requests.
- For bulk seeding, use Open Library dumps instead of hammering the API.

Recommendation:

- Use Open Library work IDs and ISBNs as dedupe anchors.
- Use Google Books for search coverage and supplemental metadata.
- For classics, use curated work/ISBN lists and Open Library dumps, not bulk single-book API calls.

### Music: Spotify Web API

Spotify is useful but legally constrained.

Important constraints verified from official docs and policy:

- Spotify uses OAuth 2.0 flows.
- Client Credentials works only for non-user resources.
- Authorization Code or PKCE is needed for user-linked imports.
- Rate limits use a rolling window and `429` responses normally include `Retry-After`.
- Spotify content requires attribution and links back to Spotify.
- Metadata and cover art must not be offered as a standalone service.
- Do not build streaming features unless explicitly allowed by Spotify policy.

Recommendation:

- Do not pre-seed a massive music catalog from Spotify.
- Start music with on-demand search and user-added persistence.
- Store minimal metadata needed for the user's library and discovery.
- Store Spotify IDs and links back to Spotify.
- Refresh stale Spotify-derived records periodically.

### Images

MVP:

- Use provider image URLs for media posters/covers where provider terms allow it.
- Store image URL metadata and source attribution.

User-uploaded images:

- Store profile images and user-generated assets in Cloudflare R2.
- R2 supports an S3-compatible API endpoint.
- Use generated object keys, not user filenames.
- Keep buckets private unless there is a specific public CDN strategy.

## 8. Data Seeding Plan

Goal: populate enough high-quality catalog data before production to make common searches fast and reduce external API calls.

Avoid illegal or fragile scraping. "IMDb top 3000" sounds useful, but scraping IMDb or copying proprietary rankings without permission is a legal/data risk. Prefer provider-supported endpoints and licensed/open data.

### Seed Targets

Initial practical target:

- Movies: 3,000 to 5,000
- Series: 1,000 to 2,000
- Games: 2,000 to 5,000
- Books: 2,000 to 5,000
- Music: small curated seed only, otherwise on-demand

Do not over-seed before search, dedupe, and imports are correct. Bad seed data compounds.

### Seed Tables

Use staging before canonical insertion:

- `seed_runs`
- `seed_items`
- `provider_snapshots`

Seed run fields:

- provider
- media_type
- seed_kind
- cursor
- status
- started_at
- finished_at
- total_seen
- total_inserted
- total_updated
- total_failed

Seed item fields:

- seed_run_id
- provider
- external_id
- raw_payload_json
- normalized_payload_json
- status
- error

### Movie/Series Seed

TMDB seed sources:

- popular movies
- top-rated movies
- popular TV
- top-rated TV
- discover endpoints by decade, genre, vote count, and language

Process:

1. Pull paginated seed IDs.
2. Fetch details and external IDs.
3. Normalize to internal media DTO.
4. Upsert by `tmdb_movie`, `tmdb_tv`, and IMDb ID.
5. Store image paths/URLs.
6. Store provider snapshot for debugging.

### Game Seed

RAWG option:

- Use ordering by popularity/rating/metacritic/added where available.
- Respect monthly request limits.
- Store RAWG ID and external store links where allowed.

IGDB option:

- Use APICalypse queries sorted by rating/popularity.
- Keep concurrency below 8 open requests.
- Keep request rate at or below 4 requests per second.

Process:

1. Pull seed pages.
2. Normalize platform-independent game record.
3. Store platform/release details in metadata first, normalize later if needed.
4. Upsert by provider ID and fuzzy match.

### Book Seed

Recommended sources:

- Open Library dumps for bulk-safe metadata.
- Curated classics lists with ISBN/work IDs.
- Google Books details for missing public metadata.

Process:

1. Build curated input list.
2. Map to ISBN-13/Open Library work where possible.
3. Upsert by ISBN and Open Library work ID.
4. Use Google Books volume only as edition-level metadata.

### Music Seed

Recommendation:

- Do not attempt a huge music seed.
- Music catalogs are massive and provider policy sensitive.
- Start with on-demand search plus user-import-driven persistence.

Possible limited seed:

- New releases by market.
- App-curated albums/tracks if policy-compliant.
- User imports through Spotify OAuth.

### Seed Job Rules

Every seed job must be:

- Idempotent
- Cursor-based
- Rate-limited per provider
- Retryable
- Logged
- Interruptible
- Safe to resume

Use advisory locks or Redis locks to prevent two workers seeding the same provider/type at once.

## 9. Authentication and Authorization

### JWT Strategy

Requirements:

- Access token: 15 minutes
- Refresh token: 30 days
- Refresh token rotation
- Refresh token family revocation on reuse
- Logout revokes current refresh token
- Logout all devices revokes all user refresh tokens

Recommended token storage for web:

- Refresh token in `HttpOnly`, `Secure`, `SameSite=Lax` or `Strict` cookie.
- Access token in memory, or also cookie-based with CSRF protections.
- Never store refresh tokens in localStorage.

Access token claims:

- `sub`: user ID
- `role`
- `admin_level`
- `jti`
- `iat`
- `exp`
- `iss`
- `aud`

Validation:

- Pin expected algorithm.
- Validate issuer and audience.
- Use strong signing secret or asymmetric keys.
- Do not put sensitive data in JWT payload.

### Password Storage

Use Argon2id.

Recommended baseline from OWASP:

- Argon2id
- At least 19 MiB memory
- 2 iterations
- parallelism 1

Pepper:

- Store pepper outside the database.
- Local dev can use `.env`.
- Production should use real environment secrets or a secrets manager.
- Rotating a pepper requires forcing password resets unless a more complex migration strategy is built.

Password policy:

- Minimum length: 12 to 15 characters for non-MFA accounts.
- Maximum length: at least 64 characters.
- Allow whitespace and Unicode.
- Do not require arbitrary composition rules.
- Rate-limit login attempts.
- Use generic auth error responses.

### Email Verification

Flow:

1. User registers.
2. Create user and credential.
3. Create single-use hashed verification token with TTL.
4. Send email.
5. Verification endpoint consumes token.

Do not expose whether an email exists in resend flows.

### Password Reset

Flow:

1. User requests reset.
2. Always return generic success response.
3. If user exists, create hashed single-use reset token with short TTL.
4. Send email.
5. Reset endpoint validates token and updates password.
6. Revoke all refresh tokens after password reset.

### Admin Access

Admin authorization:

- `ADMIN` role required for admin routes.
- `admin_level <= required_level`.
- Level `0` only for audit log viewing, admin management, backup settings, and destructive moderation overrides.

Future:

- Require 2FA for all admins.
- Store TOTP secrets encrypted at rest.
- Add recovery codes hashed in DB.
- Require re-authentication for sensitive admin actions.

### Ownership Rules

Every user-owned resource must be scoped by `current_user.id`.

Examples:

- User can update only own library entries.
- User can edit/delete only own reviews/comments unless admin moderation route is used.
- Import jobs are visible only to owner and qualified admins.
- Uploads are visible only to owner unless attached to public profile/review.

Tests must cover cross-user access attempts.

## 10. Rate Limiting and Abuse Control

Use Redis-backed rate limiting.

Rate limit dimensions:

- IP address
- user ID
- auth identifier hash for login attempts
- endpoint group
- provider adapter

Cloudflare IP handling:

- Trust `CF-Connecting-IP` only when the request actually came through Cloudflare.
- Do not blindly trust `X-Forwarded-For`.
- Keep Cloudflare IP ranges updated or enforce that origin only accepts Cloudflare traffic.

Suggested limits:

- Login: strict per IP and per identifier.
- Register: strict per IP.
- Password reset: strict per IP and per email hash.
- Search: moderate per user/IP.
- Provider fallback: stricter than local search.
- Comments/reviews: anti-spam per user.
- Imports: queue-limited per user.

Future:

- reCAPTCHA or Turnstile support behind an abstraction.
- Risk scoring for suspicious auth behavior.

## 11. File Upload and R2 Storage

Use Cloudflare R2 for profile images and future user-generated assets.

Upload rules:

- Authenticated users only.
- Size limit.
- Allowlist extensions.
- Validate MIME type but do not trust it.
- Validate magic bytes/file signatures.
- Decode image and verify dimensions.
- Re-encode images to safe formats.
- Generate object keys server-side.
- Do not preserve user filenames as object keys.
- Store uploads outside app server filesystem.

Recommended profile image flow:

1. User uploads image to API.
2. API checks size and magic bytes.
3. API decodes image.
4. API re-encodes to WebP/JPEG/PNG.
5. API uploads clean image to R2.
6. API stores `uploads` row.
7. API updates user profile image reference.

Direct-to-R2 presigned uploads are possible later, but for MVP server-side validation is simpler and safer.

## 12. Logging and Audit

Use two separate concepts:

- Operational logs: app/server diagnostics.
- Audit logs: user/admin actions with business meaning.

Audit log every important user/admin action:

- Register
- Login success
- Logout
- Refresh token reuse detection
- Email verification
- Password reset request and completion
- Add/update/delete library entry
- Create/update/delete review
- Create/update/delete comment
- Upload profile image
- Start import
- Complete import
- Admin moderation action
- Admin role/level change
- Media merge
- Backup job result

Auth error logs:

- Failed login
- Locked account login attempt
- Invalid/expired refresh token
- Refresh token reuse
- Invalid verification token
- Invalid password reset token

Do not log:

- Passwords
- Raw JWTs
- Raw refresh tokens
- Password reset tokens
- Email verification tokens
- Provider API secrets

Audit log visibility:

- Admin level `0` only.

## 13. Backups

Requirement: nightly auto DB backup at 03:00, email backup SQL file, delete server copy afterward.

Security challenge:

- Plain SQL backups contain user emails, auth metadata, tokens hashes, reviews, logs, and possibly private notes.
- Emailing plaintext SQL is not safe and often breaks on file size.

Recommended production design:

1. Run backup at 03:00 Europe/Istanbul.
2. Dump database to local temp path.
3. Compress backup.
4. Encrypt backup with age/GPG before it leaves the server.
5. Upload encrypted backup to private R2 backup bucket or another backup store.
6. Email only the backup result, checksum, size, and storage reference.
7. Delete local temp files.
8. Retain backups by policy, for example 7 daily, 4 weekly, 6 monthly.
9. Regularly test restore.

If email attachment is mandatory:

- Attach only encrypted backup archives.
- Never email plaintext SQL.
- Keep attachment size limits in mind.

Backup metadata table:

- `id`
- `status`
- `started_at`
- `finished_at`
- `size_bytes`
- `sha256`
- `storage_key`
- `error_message`

## 14. Import Architecture

Importing is a product advantage but can overload providers if implemented naively.

Supported initial import targets:

- Letterboxd CSV
- Steam account/import
- Spotify OAuth import
- Generic CSV template

Future:

- Goodreads CSV-style import
- IMDb ratings export if user supplies a legitimate export
- Trakt import

Import flow:

```text
User uploads/imports data
  -> create import_job
  -> parse rows into import_items
  -> normalize titles and external IDs
  -> match local DB first
  -> batch provider fallback for misses
  -> upsert media idempotently
  -> upsert user library entries
  -> report conflicts and failures
```

Rules:

- Imports are async.
- Imports are idempotent.
- User can cancel pending imports.
- Imports have per-user concurrency limits.
- Provider fallback is batched and rate-limited.
- Imported rows preserve raw payload for debugging.
- Cross-user access is forbidden.

Conflict examples:

- Same media already exists with different status.
- CSV row has ambiguous title.
- Provider returns multiple likely matches.
- Unsupported media type.

Conflict handling:

- Auto-apply high-confidence matches.
- Ask user to resolve ambiguous matches.
- Let user choose overwrite/skip/merge behavior before import.

## 15. API Surface

Use `/api/v1`.

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `POST /api/v1/auth/verify-email`
- `POST /api/v1/auth/resend-verification`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`

### Current User

- `GET /api/v1/me`
- `PATCH /api/v1/me`
- `GET /api/v1/me/library`
- `GET /api/v1/me/imports`
- `GET /api/v1/me/uploads`

### Media

- `GET /api/v1/media/search`
- `GET /api/v1/media/{media_id}`
- `POST /api/v1/media/{media_id}/refresh`
- `POST /api/v1/media/external/add`

`media/external/add` persists a provider result when user adds it.

### Library

- `PUT /api/v1/library/{media_id}`
- `PATCH /api/v1/library/{media_id}`
- `DELETE /api/v1/library/{media_id}`

### Reviews

- `POST /api/v1/media/{media_id}/review`
- `PATCH /api/v1/reviews/{review_id}`
- `DELETE /api/v1/reviews/{review_id}`
- `GET /api/v1/media/{media_id}/reviews`

### Comments

- `POST /api/v1/reviews/{review_id}/comments`
- `PATCH /api/v1/comments/{comment_id}`
- `DELETE /api/v1/comments/{comment_id}`

### Lists

- `POST /api/v1/lists`
- `GET /api/v1/lists/{list_id}`
- `PATCH /api/v1/lists/{list_id}`
- `DELETE /api/v1/lists/{list_id}`
- `POST /api/v1/lists/{list_id}/items`
- `DELETE /api/v1/lists/{list_id}/items/{media_id}`

### Imports

- `POST /api/v1/imports`
- `GET /api/v1/imports/{import_job_id}`
- `POST /api/v1/imports/{import_job_id}/cancel`

### Uploads

- `POST /api/v1/uploads/profile-image`
- `DELETE /api/v1/uploads/{upload_id}`

### Admin

- `GET /api/v1/admin/audit-logs` - level 0
- `GET /api/v1/admin/auth-errors` - level 0
- `GET /api/v1/admin/import-jobs` - level 0 or 1
- `GET /api/v1/admin/provider-health` - level 0 or 1
- `POST /api/v1/admin/media/merge` - level 0 or 1
- `POST /api/v1/admin/users/{user_id}/ban` - level 0 or 1
- `PATCH /api/v1/admin/users/{user_id}/role` - level 0
- `GET /api/v1/admin/backups` - level 0

## 16. Configuration and Secrets

Use `.env` for local development. In production, inject environment variables through the deployment platform or secrets manager.

Never commit real `.env`.

Create `.env.example` later with names but no secrets.

Recommended settings:

```text
APP_ENV=local
APP_NAME=multi-media-library
APP_BASE_URL=http://localhost:8000
API_PREFIX=/api/v1

DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/app
REDIS_URL=redis://localhost:6379/0

JWT_ISSUER=multi-media-library
JWT_AUDIENCE=multi-media-library-web
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=30
JWT_SECRET_KEY=
PASSWORD_PEPPER=

SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=

TMDB_API_KEY=
RAWG_API_KEY=
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
GOOGLE_BOOKS_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
OPEN_LIBRARY_USER_AGENT=
OPEN_LIBRARY_CONTACT_EMAIL=

CLOUDFLARE_R2_ACCOUNT_ID=
CLOUDFLARE_R2_ACCESS_KEY_ID=
CLOUDFLARE_R2_SECRET_ACCESS_KEY=
CLOUDFLARE_R2_BUCKET=
CLOUDFLARE_R2_PUBLIC_BASE_URL=

RATE_LIMIT_ENABLED=true
TRUST_CLOUDFLARE_HEADERS=true

BACKUP_TIMEZONE=Europe/Istanbul
BACKUP_CRON=0 3 * * *
BACKUP_R2_BUCKET=
BACKUP_ENCRYPTION_PUBLIC_KEY=
BACKUP_NOTIFY_EMAIL=
```

## 17. Testing Strategy

Minimum test layers:

- Unit tests for services and normalization logic.
- Repository tests against test PostgreSQL.
- API tests for routers.
- Auth/security tests.
- Ownership tests.
- Import parser tests.
- Provider adapter contract tests using recorded responses or fixtures.
- Migration tests.

Critical security tests:

- User cannot edit another user's library entry.
- User cannot edit another user's review/comment.
- Admin level checks are enforced.
- Banned users cannot create content.
- Refresh token reuse revokes token family.
- Password reset revokes refresh tokens.
- Invalid file magic bytes are rejected.
- Provider API secrets are not logged.

Critical data tests:

- Same TMDB ID cannot create duplicate media.
- Same ISBN cannot create duplicate book.
- Same Spotify track ID cannot create duplicate track.
- Importing same file twice is idempotent.
- Concurrent adds of same external result do not create duplicates.

## 18. Performance and Scalability

Early scaling bottlenecks:

- Search quality and indexes
- External API rate limits
- Import bursts
- Review/comment spam
- Audit log growth
- Image processing

Recommended controls:

- PostgreSQL trigram indexes for local search.
- Redis cache for common search queries.
- Per-provider queue and rate limit.
- Background jobs for enrichment/imports.
- Pagination everywhere.
- Cursor pagination for feeds and admin logs.
- Partition large audit/auth logs later by month.
- Store counts denormalized where needed, but update through reliable events.

Search should prefer local DB results. Provider fallback is a miss path, not the primary path.

## 19. Observability

Add structured JSON logs with request IDs.

Metrics to track:

- API latency by route
- Local search latency
- Provider search latency
- Provider 429 count
- Provider error count
- Queue depth
- Import success/failure rate
- Auth failure rate
- Rate-limit blocks
- Backup success/failure
- Email send failures

Alerts:

- Backup failed
- Provider 429 spike
- Auth failures spike
- Queue stuck
- DB connection pool exhausted
- Error rate above threshold

## 20. Production Hardening

Before production:

- Use HTTPS only.
- Set secure cookies.
- Configure CORS strictly.
- Add security headers.
- Validate Cloudflare proxy trust.
- Use DB migrations with Alembic.
- Remove hardcoded credentials.
- Add `.env.example`.
- Add dependency vulnerability scanning.
- Add CI tests.
- Add backups and restore drills.
- Add admin seed creation command.
- Add audit log access restrictions.
- Add privacy policy and terms.
- Validate external API terms for commercial use.

## 21. Implementation Phases

### Phase 0: Foundation

- Fix config loading from `.env`.
- Fix SQLAlchemy engine setup.
- Add Alembic.
- Add base model conventions.
- Add structured app settings.
- Add test infrastructure.

### Phase 1: Auth and Users

- User model.
- Credential model.
- Argon2id hashing with pepper.
- Register/login/refresh/logout.
- Email verification.
- Password reset.
- Role/admin level model.
- Basic rate limiting.
- Audit/auth logs.

### Phase 2: Media Catalog Core

- Media schema.
- External IDs.
- Titles/aliases.
- Local search.
- Provider abstraction.
- TMDB adapter first.
- Upsert/dedup service.

### Phase 3: Library and Social MVP

- User media entries.
- Reviews.
- Comments.
- Lists.
- Ownership tests.
- Soft deletes.

### Phase 4: Provider Expansion and Seeding

- RAWG or IGDB adapter.
- Google Books adapter.
- Open Library adapter.
- Spotify adapter.
- Seed workers.
- Provider request logging.
- Duplicate candidate review.

### Phase 5: Uploads and R2

- Upload service.
- Profile image upload.
- Magic byte checks.
- Image re-encoding.
- R2 storage.

### Phase 6: Imports

- Import job model.
- Letterboxd CSV parser.
- Generic CSV parser.
- Steam import flow.
- Spotify OAuth import.
- Import conflict UI/API support.

### Phase 7: Admin and Operations

- Admin routes.
- Audit log viewer endpoints.
- Media merge.
- User ban/moderation.
- Backup job.
- Backup metadata.
- Provider health.

### Phase 8: Production Readiness

- CI.
- Docker.
- Deployment config.
- Monitoring.
- Restore drill.
- External API terms review.
- Security review.

## 22. MVP Release Criteria

Do not call it production-ready until:

- Users can register, verify email, log in, refresh, and reset password.
- Passwords use Argon2id plus pepper.
- `.env` controls secrets.
- Local DB search works for seeded media.
- TMDB movie/series search works.
- At least one game provider works.
- At least one book provider works.
- Spotify music search works only within policy constraints.
- Media upsert prevents provider-ID duplicates.
- User library add/update/delete works.
- Reviews and comments work with ownership protections.
- Audit logs exist for auth and content actions.
- Rate limiting works behind Cloudflare.
- Profile image upload validates file content.
- Nightly encrypted backup job exists.
- Restore process has been tested.
- Admin level `0` can inspect logs.

## 23. Key Risks and Decisions

### API Terms Risk

Risk:

- Free APIs may not allow bulk seeding, commercial usage, caching, or redistribution.

Mitigation:

- Store provider attribution.
- Keep provider adapters swappable.
- Avoid scraping.
- Seed only through allowed endpoints/dumps.
- Review terms again before launch.

### Duplicate Media Risk

Risk:

- Imports and provider fallback can create many duplicate records.

Mitigation:

- External IDs table.
- Strong unique constraints.
- Upsert inside transactions.
- Fuzzy duplicate candidate queue.
- Admin merge tooling.

### Backup Privacy Risk

Risk:

- Emailing raw SQL leaks sensitive data.

Mitigation:

- Encrypt backup before it leaves server.
- Prefer private object storage and email notification.
- Test restore.

### Music Scope Risk

Risk:

- Music metadata and Spotify policy can constrain product behavior.

Mitigation:

- Start with on-demand Spotify search.
- Store IDs and minimal metadata.
- Keep linkbacks/attribution.
- Do not build streaming or standalone Spotify metadata product.

### Overbuilding Risk

Risk:

- Multi-media, imports, social, admin, and ingestion is a large surface.

Mitigation:

- Build vertical slices.
- Do movies/series first.
- Build dedupe and ownership tests early.
- Add providers one by one.

## 24. References Checked

Provider and platform docs checked on 2026-07-05:

- TMDB Getting Started: https://developer.themoviedb.org/docs/getting-started
- TMDB Images: https://developer.themoviedb.org/docs/image-basics
- TMDB Rate Limiting: https://developer.themoviedb.org/docs/rate-limiting
- IGDB API Docs: https://api-docs.igdb.com/
- RAWG API Docs: https://rawg.io/apidocs
- Google Books API: https://developers.google.com/books/docs/v1/using
- Open Library API Guidelines: https://openlibrary.org/developers/api
- Spotify Authorization: https://developer.spotify.com/documentation/web-api/concepts/authorization
- Spotify Rate Limits: https://developer.spotify.com/documentation/web-api/concepts/rate-limits
- Spotify Developer Policy: https://developer.spotify.com/policy
- Cloudflare R2 S3 Compatibility: https://developers.cloudflare.com/r2/api/s3/api/
- OWASP Password Storage: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP Authentication: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP File Upload: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Logging: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP JWT: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
