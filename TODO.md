# TODO

## Phase 0 - Foundation

- [x] Fix `app/database.py` to use `create_engine`.
- [x] Move database URL and secrets to `.env`.
- [x] Add `pydantic-settings` based app config.
- [x] Create `.env.example` with safe placeholder values.
- [x] Add Alembic migrations.
- [x] Add base SQLAlchemy model conventions.
- [x] Add pytest test setup.
- [x] Add structured JSON logging.
- [x] Add request ID middleware.

## Phase 1 - Auth and Users

- [x] Create `users` table.
- [x] Create `user_credentials` table.
- [x] Add `USER` and `ADMIN` roles.
- [x] Add admin levels `0`, `1`, `2`.
- [x] Implement Argon2id password hashing.
- [x] Add password pepper from environment.
- [x] Implement register endpoint.
- [x] Implement login endpoint.
- [x] Implement 15-minute access JWTs.
- [x] Implement 30-day rotating refresh tokens.
- [x] Store only hashed refresh tokens.
- [x] Implement logout.
- [x] Implement logout-all.
- [x] Implement email verification tokens.
- [x] Implement password reset tokens.
- [x] Revoke refresh tokens after password reset.
- [x] Add auth error logging.
- [x] Add audit log model.
- [x] Add basic Redis-backed rate limiting.
- [x] Add ownership/permission helpers.
- [x] Add self-only profile update endpoint.
- [x] Add current-password-verified password change with session revocation.

## Phase 2 - Media Catalog

- [x] Create `media` table.
- [x] Create `media_external_ids` table.
- [x] Create `media_titles` table.
- [x] Create `media_images` table.
- [x] Create genre tables.
- [x] Add media type enum.
- [x] Add library status enum.
- [x] Add trigram search indexes.
- [x] Implement media repository.
- [x] Implement media service.
- [x] Implement local media search.
- [x] Build provider adapter base interface.
- [x] Implement TMDB provider adapter.
- [x] Implement provider request logging.
- [x] Implement media upsert by external ID.
- [x] Add duplicate candidate handling.
- [x] Add tests for duplicate prevention.

## Phase 3 - Library and Social MVP

- [x] Create `user_media_entries` table.
- [x] Implement add/update/remove library entry.
- [x] Add unique active library constraint.
- [x] Create `reviews` table.
- [x] Implement create/update/delete review.
- [x] Enforce one active review per user/media.
- [x] Create `comments` table.
- [x] Implement review comments.
- [x] Create `lists` table.
- [x] Create `list_items` table.
- [x] Implement list CRUD.
- [x] Add soft delete support.
- [x] Add cross-user ownership tests.

## Phase 4 - Providers and Seeding

- [ ] Choose primary game provider for MVP.
- [ ] Implement RAWG or IGDB adapter.
- [ ] Implement Google Books adapter.
- [ ] Implement Open Library adapter.
- [ ] Implement Spotify adapter.
- [ ] Add provider-specific rate limits.
- [ ] Add provider backoff on `429`.
- [ ] Create seed run tables.
- [ ] Create idempotent seed worker.
- [ ] Seed TMDB movies.
- [ ] Seed TMDB series.
- [ ] Seed games within provider limits.
- [ ] Seed books from curated/open sources.
- [ ] Keep music mostly on-demand.
- [ ] Add provider attribution fields.

## Phase 5 - Uploads and R2

- [ ] Create `uploads` table.
- [ ] Configure Cloudflare R2 client.
- [ ] Implement profile image upload endpoint.
- [ ] Enforce upload size limit.
- [ ] Validate image magic bytes.
- [ ] Decode and verify image dimensions.
- [ ] Re-encode uploaded images.
- [ ] Generate server-side object keys.
- [ ] Store profile images in R2.
- [ ] Add upload security tests.

## Phase 6 - Imports

- [ ] Create `import_jobs` table.
- [ ] Create `import_items` table.
- [ ] Implement async import worker.
- [ ] Implement Letterboxd CSV parser.
- [ ] Implement generic CSV parser.
- [ ] Add import idempotency.
- [ ] Match imports against local DB first.
- [ ] Add provider fallback for unmatched rows.
- [ ] Add import conflict handling.
- [ ] Add Steam import design.
- [ ] Add Spotify OAuth import design.
- [ ] Add import ownership tests.

## Phase 7 - Admin and Operations

- [ ] Add admin router.
- [ ] Protect admin routes by role and level.
- [ ] Add level-0 audit log endpoint.
- [ ] Add level-0 auth error endpoint.
- [ ] Add media merge endpoint.
- [ ] Add user ban endpoint.
- [ ] Add admin role update endpoint.
- [ ] Add provider health endpoint.
- [ ] Add backup metadata table.
- [ ] Implement nightly encrypted DB backup.
- [ ] Delete local backup temp files after upload/send.
- [ ] Email backup status notification.
- [ ] Test database restore.

## Phase 8 - Production Readiness

- [ ] Add Docker setup.
- [ ] Add CI test workflow.
- [ ] Add dependency vulnerability scanning.
- [ ] Configure strict CORS.
- [ ] Configure secure cookies.
- [ ] Add security headers.
- [ ] Validate Cloudflare IP handling.
- [ ] Add monitoring and alerting.
- [ ] Add privacy policy and terms.
- [ ] Re-check external API terms before launch.
- [ ] Run full security review.
- [ ] Run production restore drill.
