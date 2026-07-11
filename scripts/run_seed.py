"""Run one idempotent provider seed page from a dedicated worker/cron process.

Example: python -m scripts.run_seed --provider tmdb --media-type MOVIE --seed-kind popular --cursor 1 --limit 2
"""
from __future__ import annotations

import argparse
import asyncio

from app.models.media import MediaType
from app.workers.seed_worker import run_seed_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed one media provider page")
    parser.add_argument("--provider", choices=("tmdb", "rawg", "google_books", "open_library"), required=True)
    parser.add_argument("--media-type", choices=[item.value for item in MediaType], required=True)
    parser.add_argument("--seed-kind", required=True)
    parser.add_argument("--cursor")
    parser.add_argument("--limit", type=int, default=20, choices=range(1, 41))
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    run = await run_seed_page(
        provider=args.provider,
        media_type=MediaType(args.media_type),
        seed_kind=args.seed_kind,
        cursor=args.cursor,
        limit=args.limit,
    )
    print(f"seed_run={run.id} status={run.status.value} inserted={run.total_inserted} updated={run.total_updated} failed={run.total_failed}")


if __name__ == "__main__":
    asyncio.run(main())
