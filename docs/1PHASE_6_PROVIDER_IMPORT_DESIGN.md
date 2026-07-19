# Phase 6 provider import design

CSV imports are implemented first because they are user-supplied, auditable, and do not require storing third-party credentials. `STEAM` and `SPOTIFY` are represented as import sources but intentionally cannot be submitted to the CSV endpoint.

## Steam

Add a `connected_provider_accounts` table before implementation. Store the Steam ID and an encrypted, short-lived OAuth/OpenID session reference where applicable; never accept a Steam password. The user starts a provider connection, the callback validates the signed response and user-bound `state`, then a worker reads the public/authorized library through the provider adapter. Persist a stable Steam app ID in `import_items.raw_payload_json`, match `steam_app` external IDs first, and use title matching only as a fallback. Revoke/disconnect deletes the encrypted credential and prevents new jobs, without deleting prior library entries.

## Spotify OAuth

Use Authorization Code with PKCE, not client credentials. Persist encrypted refresh tokens in `connected_provider_accounts`, scoped to the minimum read-only library scopes required by the selected import. Bind and validate a cryptographically random state/PKCE verifier per authenticated user; the callback must never accept a user ID from the browser. The worker paginates saved albums/tracks and playlists under Spotify rate limits, writes Spotify IDs to import items, and uses the existing Spotify media upsert path. Store only minimal metadata and Spotify attribution/linkbacks; never expose provider tokens to the frontend or logs.
