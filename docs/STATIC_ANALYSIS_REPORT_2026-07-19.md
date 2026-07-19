# Static Analysis Findings Report

**Date:** 2026-07-19  
**Scope:** Next.js frontend (`src/`) and FastAPI backend (`multimedia-library-api/`), with emphasis on backend security controls.  
**Method:** Manual static code and configuration review, targeted pattern search, and frontend ESLint. This was not a penetration test or a production configuration review.

## Executive summary

> **Remediation status (2026-07-19):** The four High findings have been implemented after this assessment. The tracked Medium/Low backlog is maintained in [STATIC_ANALYSIS_REMEDIATION_TODO.md](STATIC_ANALYSIS_REMEDIATION_TODO.md). The findings below remain the assessment snapshot and rationale for the changes.

No confirmed Critical finding was identified. The authentication foundation is good: Argon2id password hashing, signed access tokens with issuer/audience checks, refresh-token rotation/reuse detection, live-user authorization checks, and owner/admin authorization are present.

The main risk is operational exposure rather than a broken authentication primitive. A newly registered but unverified account can invoke expensive provider-backed operations, multipart limits are applied only after FastAPI has parsed the request, and long-running imports/backups are executed inside API processes. The backup workflow also has a deterministic state bug that prevents later backups from being triggered.

| Severity | Count | Primary themes |
| --- | ---: | --- |
| Critical | 0 | No confirmed critical issue |
| High | 4 | Upload DoS, abuse controls, broken backup state, non-durable jobs |
| Medium | 9 | Proxy trust, secret separation, data integrity, performance, contract drift |
| Low | 4 | Security headers/docs, rate-limit implementation, maintainability debt |

## High

### H-01 — Multipart size limits occur after the request is accepted

**Areas:** Security, stability, performance  
**Evidence:** [uploads.py](../app/routers/uploads.py#L25) reads at most `max_bytes + 1`, and [imports.py](../app/routers/imports.py#L24) does the same. However, `UploadFile` is created after Starlette/FastAPI has parsed the multipart body. No global `Content-Length` or streaming ASGI/proxy limit is configured in [main.py](../app/main.py#L24).

An authenticated attacker can submit a very large multipart body with an allowed part type. The application discovers the excess only after the server has received and potentially spooled it, enabling temporary-disk, memory, bandwidth, and worker exhaustion. The per-part `content-length` check is optional and cannot serve as the global guard.

**Remediation:** Enforce a maximum request body size at the reverse proxy and ASGI layer before multipart parsing; reject absent or excessive `Content-Length` where applicable. Keep the current byte-read and image-decode limits as defence in depth. Add oversized streaming-upload tests.

### H-02 — Unverified accounts can spend provider quota; high-cost media endpoints lack rate limits

**Areas:** Security, availability, cost control  
**Evidence:** Registration issues a complete token pair in [auth_service.py](../app/services/auth_service.py#L122), while [permissions.py](../app/core/permissions.py#L52) only checks active/banned status—not `email_verified_at`. Provider-backed `/media/search` and `/media/external/add` have no `rate_limit` dependency in [media.py](../app/routers/media.py#L32) and [media.py](../app/routers/media.py#L92). They make remote provider calls and may persist catalog data.

Email verification is therefore informational rather than a control. An attacker can automate registrations and use unverified accounts to consume provider API quota, create catalog churn, and load the API/database. The existing IP limiter alone is not sufficient for this path, particularly in a distributed deployment.

**Remediation:** Decide explicitly which pre-verification operations are allowed. For this product, require a verified email for provider search/import/add, uploads, social writes, and other quota-consuming actions. Add per-account and per-provider rate limits to search/add, plus a bounded registration-abuse control (CAPTCHA/risk signal or verified-email gate). Instrument provider calls by user and return `429` before making external requests.

### H-03 — Triggering one backup can permanently block subsequent backups

**Areas:** Quality, stability  
**Evidence:** The trigger creates and commits a `pending` record in [admin.py](../app/routers/admin.py#L322). The scheduled task then calls `BackupService.run_backup`, which creates a *second* pending record in [backup_service.py](../app/services/backup_service.py#L46). The trigger rejects whenever any pending record exists in [admin.py](../app/routers/admin.py#L314).

The original record is never transitioned to success or failure. After the first trigger, it remains pending indefinitely and all later triggers return `409`.

**Remediation:** Create exactly one backup record and pass its ID into the worker; the worker must load and transition that record. Add a unique/locking strategy for an active backup and a recovery policy for stale `pending` records. Add an integration test that triggers two sequential backups.

### H-04 — Imports and backups run as in-process, non-durable API background work

**Areas:** Quality, stability, architecture  
**Evidence:** Imports schedule `BackgroundTasks` and pass the request session to the task in [imports.py](../app/routers/imports.py#L45). The worker itself labels this an API fallback to be replaced by a queue consumer in [import_worker.py](../app/workers/import_worker.py#L16). Backups use `BackgroundTasks` in [admin.py](../app/routers/admin.py#L326); the async backup function performs synchronous `pg_dump`, compression, encryption, object storage, and SMTP work in [backup_service.py](../app/services/backup_service.py#L41).

Tasks are lost on API restart, are not coordinated across replicas, have no retry/lease/recovery model, and compete with request handling. The backup's blocking work runs inside an `async` task and can block the event loop. Imports may remain `PENDING`/`PROCESSING` forever after a restart.

**Remediation:** Move imports, backups, and seeding to a durable worker/queue with its own database sessions, idempotency keys, retry policy, leases/heartbeats, and stale-job reconciliation. Until then, make the functions synchronous so Starlette runs them in its thread pool, do not share request sessions, and place strict concurrency limits around work.

## Medium

### M-01 — Cloudflare client-IP trust is spoofable if the origin is reachable

**Areas:** Security  
**Evidence:** [rate_limit.py](../app/core/rate_limit.py#L81) accepts `CF-Connecting-IP` whenever `TRUST_CLOUDFLARE_HEADERS=true`, without verifying that the direct peer is Cloudflare.

If the origin can be reached directly, an attacker can supply arbitrary header values and bypass IP-based throttling. This is conditional on deployment topology but is a common production misconfiguration.

**Remediation:** Restrict origin ingress to Cloudflare IP ranges/security groups. At the proxy, strip inbound forwarding headers and inject trusted values. Only enable this setting when the network boundary guarantees it; otherwise derive the address from trusted proxy middleware with an allowlist.

### M-02 — Backup encryption falls back to the JWT signing secret

**Areas:** Security, key management  
**Evidence:** [backup_service.py](../app/services/backup_service.py#L35) derives the Fernet key from `backup_encryption_key or jwt_secret_key`; the backup key is optional in [config.py](../app/core/config.py#L69).

Compromise or rotation of the JWT key also compromises or can make historical backups unreadable. This violates key separation and makes incident response more damaging.

**Remediation:** Require a dedicated, versioned backup encryption key outside local/test; reject startup when it is absent. Store a key ID alongside backup metadata and document a key-rotation/re-encryption process.

### M-03 — Soft-deleted media can be searched and attached to user content

**Areas:** Quality, data integrity  
**Evidence:** [media_repository.py](../app/repositories/media_repository.py#L18) `get_by_id`, `get_by_external_id`, and `search_local` do not filter `Media.deleted_at`. In contrast, the detail service explicitly rejects deleted media in [media_service.py](../app/services/media_service.py#L45). Library, review, and list services use `get_by_id` before creating references.

After an admin merge/soft-delete, a user can receive a deleted item from search or attach it using its ID; the resulting media detail then returns `404`. Provider upsert can also return the deleted record rather than restore or replace it.

**Remediation:** Make active-only retrieval the repository default and add explicit `include_deleted` methods for administration. Apply `deleted_at IS NULL` consistently to local search and external-ID lookup. Add regression coverage for a merged media record.

### M-04 — Social/list payloads are unbounded, and text rendering has no defined storage policy

**Areas:** Security, stability, maintainability  
**Evidence:** Comment bodies only have a minimum in [comment.py](../app/schemas/comment.py#L12); review bodies in [review.py](../app/schemas/review.py#L12), list descriptions in [list.py](../app/schemas/list.py#L43), and private notes in [library.py](../app/schemas/library.py#L17) have no maximum.

Large JSON requests are held in application memory and stored in `Text` fields without a product-level policy. This permits database bloat and request-memory pressure. React currently escapes the reviewed text sinks, but a future rich-text/HTML rendering change would have no sanitization boundary.

**Remediation:** Define product limits (for example, comments 5k, reviews 20k, notes/descriptions 10k characters), enforce them in Pydantic and at the edge, and retain plain text unless a vetted Markdown/sanitization pipeline is introduced. Add truncation/rejection tests.

### M-05 — `followers` visibility is offered but no follower authorization model exists

**Areas:** Quality, product correctness  
**Evidence:** The frontend presents a `followers` option in [lists-dashboard.tsx](../../src/components/social/lists-dashboard.tsx#L11). The backend supports it as a string pattern in [list.py](../app/schemas/list.py#L44) and [review.py](../app/schemas/review.py#L14), but list/review repositories only return public items or the owner's items; there is no follower model or relationship.

In practice, a `followers` item is hidden from every non-owner rather than visible to followers. This silently breaks the privacy/product contract.

**Remediation:** Either remove/deprecate `followers` until a follower graph and policy exist, or implement the graph, indexes, centralized visibility predicate, and tests for owner/follower/non-follower/admin behavior. Use a database enum/check constraint rather than free-form strings.

### M-06 — Relationship serialization produces likely N+1 query patterns

**Areas:** Performance, scalability  
**Evidence:** List, review, and library repositories return ORM entities without eager loading ([list_repository.py](../app/repositories/list_repository.py#L23), [review_repository.py](../app/repositories/review_repository.py#L27), [library_repository.py](../app/repositories/library_repository.py#L34)), while response schemas serialize nested `items`, `media`, and `genres` ([list.py](../app/schemas/list.py#L56), [library.py](../app/schemas/library.py#L39), [media.py](../app/schemas/media.py#L14)).

At the current maximum page sizes, serialization can issue one query per parent and per nested media/genre collection. This will degrade rapidly under real catalog and social data.

**Remediation:** Add endpoint-specific `selectinload`/`joinedload` query plans, enforce pagination at the UI/API contract boundary, and add query-count tests. Do not globally eager-load every relationship.

### M-07 — Media upsert and list positioning have unresolved concurrency races

**Areas:** Quality, data integrity  
**Evidence:** Media upsert performs check-then-insert around unique external IDs in [media_service.py](../app/services/media_service.py#L217). List insertion derives `max(position) + 1` in [list_repository.py](../app/repositories/list_repository.py#L78), then inserts under a uniqueness constraint.

Concurrent requests can produce integrity errors/500s. List reorder also accepts a non-permutation `media_ids` payload, allowing duplicates/omissions and inconsistent positions.

**Remediation:** Use database-aware upserts or catch/reload on uniqueness conflicts for media. Serialize list mutations (row lock/version) and validate that a reorder request is an exact, duplicate-free permutation of the list's items. Return a domain `409`, not a generic `500`.

### M-08 — Backend/frontend media contract drift breaks duplicate-candidate selection

**Areas:** Quality, maintainability  
**Evidence:** The frontend expects `Media.metadata_json` and reads `duplicate_candidates` via `any` in [media-merge/page.tsx](../../src/app/admin/media-merge/page.tsx#L51) and [types/index.ts](../../src/types/index.ts#L10). The admin endpoint declares `list[MediaPublic]` in [admin.py](../app/routers/admin.py#L248), while `MediaPublic` does not expose `metadata_json` in [media.py](../app/schemas/media.py#L17).

Pydantic response serialization omits this undeclared field, so the UI cannot retrieve the duplicate candidates it relies on. This is also a signal that API contract ownership is split and not tested end-to-end.

**Remediation:** Introduce an explicit admin-only duplicate-candidate DTO containing only the required candidate IDs/reason, generate or validate TypeScript contracts from the API schema, and add a router/UI contract test. Replace `any` with the DTO type.

### M-09 — The frontend quality gate is currently failing

**Areas:** Quality, maintainability  
**Evidence:** `npm run lint` reports 20 errors and 8 warnings: explicit `any` types, invalid state-setting patterns in admin-page effects, missing effect dependencies, unused values, and an unoptimized `img`. The affected admin routes include audit logs, auth errors, backups, media merge, and moderation.

This means the administrative surface lacks a reliable static quality gate and contains patterns prone to repeated fetches/stale closures/cascading renders.

**Remediation:** Make lint zero-warning/error in CI. Type admin API responses, make loaders stable with `useCallback` or restructure effects, and add route-level tests for loading/filter/polling behavior.

## Low

### L-01 — Production API documentation/schema remain publicly enabled

**Areas:** Security hardening  
**Evidence:** [main.py](../app/main.py#L24) creates `FastAPI` with default docs/OpenAPI routes and includes a comment that production docs must be disabled.

This exposes route names, schemas, and authentication conventions to unauthenticated callers. It is not an authorization bypass, but reduces attacker discovery cost.

**Remediation:** Set `docs_url`, `redoc_url`, and `openapi_url` to `None` in production, or protect an internal documentation route.

### L-02 — No explicit browser security-header policy is configured

**Areas:** Frontend security hardening  
**Evidence:** [next.config.ts](../../next.config.ts#L3) configures image patterns and rewrites but no response headers; the reviewed frontend has no CSP/transport/frame/referrer policy configuration.

React's default escaping and the reviewed HTTPS-only external-link validation reduce present XSS risk, but there is no defence-in-depth browser policy.

**Remediation:** Configure a tested CSP (start report-only if needed), `Strict-Transport-Security` at TLS termination, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and `frame-ancestors`/`X-Frame-Options`. Ensure the API reverse proxy has an equivalent policy where applicable.

### L-03 — Rate limiter clients are created per request and expiry is not atomic

**Areas:** Performance, reliability  
**Evidence:** `get_rate_limiter` returns a new `RedisRateLimiter` for each request in [rate_limit.py](../app/core/rate_limit.py#L91), producing a new Redis client/pool on first use. `INCR` and `EXPIRE` are separate calls in [rate_limit.py](../app/core/rate_limit.py#L42).

Under traffic this increases connection/pool churn. A failure between increment and expiry can leave a key without a TTL, producing an unnecessarily permanent limit for that key.

**Remediation:** Keep a process-level Redis client initialized during application lifespan and use an atomic Lua script or `MULTI/EXEC`/`SET ... NX EX` pattern that guarantees expiry.

### L-04 — Transaction ownership and code ownership are diffuse

**Areas:** Maintainability, architecture  
**Evidence:** Routers own authorization and exception translation, services commit internally, repositories mutate and flush, and background tasks are introduced in routers. For example, [library.py](../app/routers/library.py#L84) authorizes then calls a service that commits internally; [backup_service.py](../app/services/backup_service.py#L46) independently creates/commits workflow state.

This split makes multi-step transactions, retries, observability, and test isolation difficult—the duplicate-backup defect is an example. `TODO.md` also lists production security/CORS/Docker verification as outstanding work.

**Remediation:** Establish module owners and an application-service boundary: request handlers should validate/authorize, application services should own one transaction and state transition, repositories should not commit, and workers should own asynchronous workflow execution. Publish a concise ADR for this boundary.

## Prioritized remediation sequence

1. Add edge/ASGI request limits; gate expensive/mutating operations behind verified email; add provider endpoint/account quotas.
2. Fix backup to use one state record, then move backups/imports to durable workers with stale-job recovery.
3. Correct soft-delete queries and add concurrency-safe upsert/list mutation behavior.
4. Establish explicit DTOs and contract tests for admin/media APIs; make the frontend lint gate clean.
5. Harden deployment boundaries: trusted proxy configuration, dedicated backup key, production docs policy, and security headers.

## Validation notes

- `npm run lint` was executed and failed with **20 errors / 8 warnings**; the failures are captured in M-09.
- Backend tests could not start because the checked-in virtual environment points to a missing interpreter (`C:\\Users\\sefa_\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`). Recreate the venv from `requirements.txt` and run `pytest` in CI; no test-result claim is made here.
- No code was changed as part of this analysis; this document is the only artifact added.
