# Static Analysis Remediation Backlog

This backlog tracks the Medium and Low findings from [the 2026-07-19 static-analysis report](STATIC_ANALYSIS_REPORT_2026-07-19.md). High findings are addressed separately in the implementation change that introduced this file.

## Medium priority

- [ ] **M-01: Trusted proxy boundary** — Restrict origin ingress to Cloudflare, strip client-supplied forwarding headers at the edge, and replace the boolean `TRUST_CLOUDFLARE_HEADERS` switch with an allowlisted trusted-proxy configuration. Add direct-origin spoofing integration coverage.

- [ ] **M-02: Dedicated backup key management** — Require a distinct backup encryption key outside local/test, persist a key ID with every backup, and document rotation/re-encryption. Do not reuse JWT key material.

- [ ] **M-03: Soft-delete query policy** — Make active-only media lookups the default; expose explicit admin-only include-deleted queries. Add merge/search/library regression tests.

- [ ] **M-04: Text/request bounds** — Define and enforce length limits for comments, reviews, lists, and private notes at the DTO and edge layers. Keep content plain text unless a vetted sanitization pipeline is introduced.

- [ ] **M-05: Followers visibility** — Either remove `followers` from the public API/UI until it exists, or implement a follower graph, a centralized visibility policy, database constraints, and owner/follower/non-follower tests.

- [ ] **M-06: ORM query plans** — Add endpoint-specific eager loading and query-count tests for nested media, genres, lists, reviews, and library responses.

- [ ] **M-07: Concurrent writes** — Use conflict-safe media upserts, transactional list position allocation/reordering, and exact-permutation validation. Map conflicts to `409` responses.

- [ ] **M-08: API contract ownership** — Add an explicit admin duplicate-candidate DTO, remove frontend `any` casts, and generate or validate frontend contracts from the OpenAPI schema in CI.

- [ ] **M-09: Frontend quality gate** — Resolve the current ESLint errors/warnings, stabilize admin-page effects/loaders, and add route-level tests for filtering, polling, and error states.

## Low priority

- [ ] **L-01: Production API docs policy** — Disable or protect OpenAPI/Swagger/ReDoc in production; document the operational access path.

- [ ] **L-02: Browser security headers** — Add a tested CSP, HSTS at TLS termination, `X-Content-Type-Options`, `Referrer-Policy`, and anti-framing policy for web/API responses.

- [ ] **L-03: Rate limiter lifecycle and atomicity** — Manage one Redis client through application lifespan and use an atomic counter/expiry operation.

- [ ] **L-04: Transaction/code ownership boundary** — Adopt an ADR that makes application services the sole transaction boundary, keeps repositories commit-free, assigns module ownership, and separates request handlers from worker orchestration.

## Definition of done

For each item: implementation, focused regression tests, observability/operational notes where relevant, and a clean frontend/backend CI run are required before marking it complete.
