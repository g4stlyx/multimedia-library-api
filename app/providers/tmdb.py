from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import date
import requests
from sqlalchemy.orm import Session

from app.models.media import MediaType
from app.providers.base import BaseProviderAdapter, ProviderMediaDetails, ProviderSearchResult, ProviderSeedPage
from app.providers.http import ProviderError, ProviderRateController, ProviderRateLimitError

logger = logging.getLogger(__name__)


def parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def extract_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


class TMDBProviderAdapter(BaseProviderAdapter):
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    def __init__(self, api_key: str | None, db: Session | None = None) -> None:
        self.api_key = api_key
        self.db = db

    def _get_headers_and_params(self, params: dict | None = None) -> tuple[dict, dict]:
        headers = {
            "Accept": "application/json",
        }
        out_params = params.copy() if params else {}
        
        # Support either v3 api_key query param or Bearer Token (if long JWT-like key)
        if self.api_key:
            if len(self.api_key) > 40 and self.api_key.startswith("ey"):
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                out_params["api_key"] = self.api_key
        return headers, out_params

    def _execute_request(self, method: str, path: str, params: dict | None = None) -> requests.Response:
        endpoint = f"{self.BASE_URL}{path}"
        headers, final_params = self._get_headers_and_params(params)

        start_time = time.perf_counter()
        status_code = 500
        rate_limited = False
        duration_ms = 0
        response = None

        try:
            for attempt in range(3):
                ProviderRateController.wait_for_turn("tmdb", 20.0)
                response = requests.request(
                    method=method, url=endpoint, headers=headers, params=final_params, timeout=10,
                )
                if response.status_code != 429 or attempt == 2:
                    break
                retry_after_raw = response.headers.get("Retry-After")
                retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else min(2 ** (attempt + 1), 30)
                time.sleep(retry_after)
            assert response is not None
            status_code = response.status_code
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            if status_code == 429:
                rate_limited = True
                retry_after_raw = response.headers.get("Retry-After")
                retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
                raise ProviderRateLimitError("tmdb", retry_after)

            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if response is not None:
                status_code = response.status_code
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Re-raise rate limit errors
            if status_code == 429:
                raise ProviderRateLimitError("tmdb")
            raise ProviderError(f"TMDB HTTP request failed: {e}") from e
        finally:
            self._log_request(
                path=path,
                params=final_params,
                status_code=status_code,
                duration_ms=duration_ms,
                rate_limited=rate_limited,
            )

    def _log_request(
        self,
        path: str,
        params: dict,
        status_code: int,
        duration_ms: int,
        rate_limited: bool,
    ) -> None:
        if not self.db:
            return

        # Sanitize parameters (exclude API keys/tokens from parameters and endpoint hashes)
        safe_params = {
            k: v for k, v in params.items()
            if "key" not in k.lower() and "token" not in k.lower()
        }
        
        serialized = json.dumps(
            {"provider": "tmdb", "path": path, "params": safe_params},
            sort_keys=True,
        )
        request_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        try:
            from sqlalchemy.orm import sessionmaker
            from app.repositories.media_repository import MediaRepository
            SessionMaker = sessionmaker(bind=self.db.bind)
            log_db = SessionMaker()
            try:
                repo = MediaRepository(log_db)
                repo.log_provider_request(
                    provider="tmdb",
                    endpoint=path,
                    request_hash=request_hash,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    rate_limited=rate_limited,
                )
                log_db.commit()
            finally:
                log_db.close()
        except Exception as e:
            logger.exception("Failed to write provider request log to database: %s", e)

    async def search(
        self,
        query: str,
        media_type: MediaType,
        limit: int = 20,
    ) -> list[ProviderSearchResult]:
        if not self.api_key:
            logger.warning("TMDB API Key is not set, skipping search execution")
            return []

        if media_type == MediaType.MOVIE:
            path = "/search/movie"
        elif media_type == MediaType.SERIES:
            path = "/search/tv"
        else:
            # TMDB only supports Movie and Series catalog matching
            return []

        params = {"query": query}

        # Run blocking HTTP request in a separate thread
        try:
            response = await asyncio.to_thread(self._execute_request, "GET", path, params)
            data = response.json()
        except ProviderError as e:
            logger.error("TMDB search failed: %s", e)
            return []

        results = data.get("results", [])
        search_results: list[ProviderSearchResult] = []

        for item in results[:limit]:
            external_id = str(item.get("id"))
            
            # Map movie vs tv fields
            if media_type == MediaType.MOVIE:
                title = item.get("title", "")
                original_title = item.get("original_title")
                release_date_str = item.get("release_date")
            else:
                title = item.get("name", "")
                original_title = item.get("original_name")
                release_date_str = item.get("first_air_date")

            release_date_obj = parse_date(release_date_str)
            release_year = extract_year(release_date_str)
            
            poster_path = item.get("poster_path")
            backdrop_path = item.get("backdrop_path")

            search_results.append(
                ProviderSearchResult(
                    provider="tmdb",
                    external_id=external_id,
                    media_type=media_type,
                    title=title,
                    original_title=original_title,
                    description=item.get("overview"),
                    release_date=release_date_obj,
                    release_year=release_year,
                    runtime_minutes=None,  # Search results do not contain runtimes
                    primary_language=item.get("original_language"),
                    country_code=None,
                    poster_url=f"{self.IMAGE_BASE_URL}/w500{poster_path}" if poster_path else None,
                    backdrop_url=f"{self.IMAGE_BASE_URL}/original{backdrop_path}" if backdrop_path else None,
                    popularity_score=item.get("popularity"),
                    external_url=f"https://www.themoviedb.org/{'movie' if media_type == MediaType.MOVIE else 'tv'}/{external_id}",
                    attribution_text="Data provided by TMDB",
                    attribution_url="https://www.themoviedb.org/",
                    metadata_json=item,
                )
            )

        return search_results

    async def get_details(
        self,
        external_id: str,
        media_type: MediaType,
    ) -> ProviderMediaDetails:
        if not self.api_key:
            raise ProviderError("TMDB API Key is not set")

        if media_type == MediaType.MOVIE:
            path = f"/movie/{external_id}"
        elif media_type == MediaType.SERIES:
            path = f"/tv/{external_id}"
        else:
            raise ProviderError(f"TMDB does not support media type: {media_type}")

        # Request details, external ids (for IMDb), and alternative titles in one roundtrip
        params = {"append_to_response": "external_ids,alternative_titles"}

        try:
            response = await asyncio.to_thread(self._execute_request, "GET", path, params)
            data = response.json()
        except ProviderError as e:
            logger.error("TMDB get_details failed: %s", e)
            raise

        # Map base fields
        if media_type == MediaType.MOVIE:
            title = data.get("title", "")
            original_title = data.get("original_title")
            release_date_str = data.get("release_date")
            runtime = data.get("runtime")
            
            # Country code
            production_countries = data.get("production_countries", [])
            country_code = production_countries[0].get("iso_3166_1") if production_countries else None
            
            # Alternative titles
            alt_titles_list = data.get("alternative_titles", {}).get("titles", [])
        else:
            title = data.get("name", "")
            original_title = data.get("original_name")
            release_date_str = data.get("first_air_date")
            
            # TV runtimes
            episode_runtimes = data.get("episode_run_time", [])
            runtime = episode_runtimes[0] if episode_runtimes else None

            # Country code
            origin_countries = data.get("origin_country", [])
            country_code = origin_countries[0] if origin_countries else None
            if not country_code:
                prod_countries = data.get("production_countries", [])
                country_code = prod_countries[0].get("iso_3166_1") if prod_countries else None
                
            # Alternative titles
            alt_titles_list = data.get("alternative_titles", {}).get("results", [])

        release_date_obj = parse_date(release_date_str)
        release_year = extract_year(release_date_str)
        
        poster_path = data.get("poster_path")
        backdrop_path = data.get("backdrop_path")

        # Extract IMDb ID if available
        imdb_id = data.get("external_ids", {}).get("imdb_id")
        if imdb_id:
            imdb_id = str(imdb_id).strip()
            if not imdb_id or imdb_id == "None":
                imdb_id = None

        # Extract genre names
        genres = [g.get("name", "") for g in data.get("genres", []) if g.get("name")]

        # Map alternate titles
        alternate_titles = []
        for alt in alt_titles_list:
            alt_title = alt.get("title")
            if alt_title:
                alternate_titles.append({
                    "title": alt_title,
                    "language": alt.get("iso_3166_1", "").lower(),  # TMDB maps titles to ISO countries/regions
                    "region": alt.get("iso_3166_1", "").upper(),
                })

        # Base images array
        images = []
        if poster_path:
            images.append({
                "image_type": "poster",
                "url": f"{self.IMAGE_BASE_URL}/w500{poster_path}",
                "width": 500,
                "height": 750,
            })
        if backdrop_path:
            images.append({
                "image_type": "backdrop",
                "url": f"{self.IMAGE_BASE_URL}/original{backdrop_path}",
                "width": 1920,
                "height": 1080,
            })

        return ProviderMediaDetails(
            provider="tmdb",
            external_id=external_id,
            media_type=media_type,
            title=title,
            original_title=original_title,
            description=data.get("overview"),
            release_date=release_date_obj,
            release_year=release_year,
            runtime_minutes=runtime,
            primary_language=data.get("original_language"),
            country_code=country_code,
            poster_url=f"{self.IMAGE_BASE_URL}/w500{poster_path}" if poster_path else None,
            backdrop_url=f"{self.IMAGE_BASE_URL}/original{backdrop_path}" if backdrop_path else None,
            popularity_score=data.get("popularity"),
            external_url=f"https://www.themoviedb.org/{'movie' if media_type == MediaType.MOVIE else 'tv'}/{external_id}",
            attribution_text="Data provided by TMDB",
            attribution_url="https://www.themoviedb.org/",
            imdb_id=imdb_id,
            genres=genres,
            alternate_titles=alternate_titles,
            images=images,
            metadata_json=data,
        )

    async def get_seed_page(
        self,
        *,
        seed_kind: str,
        media_type: MediaType,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProviderSeedPage:
        if not self.api_key:
            raise ProviderError("TMDB API Key is not set")
        paths = {
            (MediaType.MOVIE, "popular"): "/movie/popular",
            (MediaType.MOVIE, "top_rated"): "/movie/top_rated",
            (MediaType.SERIES, "popular"): "/tv/popular",
            (MediaType.SERIES, "top_rated"): "/tv/top_rated",
        }
        try:
            path = paths[(media_type, seed_kind)]
        except KeyError as error:
            raise ProviderError(f"Unsupported TMDB seed: {media_type.value}/{seed_kind}") from error
        page = max(int(cursor or "1"), 1)
        data = (await asyncio.to_thread(self._execute_request, "GET", path, {"page": page})).json()
        results: list[ProviderSearchResult] = []
        for item in data.get("results", [])[:limit]:
            external_id = item.get("id")
            if external_id is None:
                continue
            title = item.get("title") if media_type == MediaType.MOVIE else item.get("name")
            release = item.get("release_date") if media_type == MediaType.MOVIE else item.get("first_air_date")
            if not title:
                continue
            poster_path, backdrop_path = item.get("poster_path"), item.get("backdrop_path")
            results.append(ProviderSearchResult(provider="tmdb", external_id=str(external_id), media_type=media_type, title=title, original_title=item.get("original_title") if media_type == MediaType.MOVIE else item.get("original_name"), description=item.get("overview"), release_date=parse_date(release), release_year=extract_year(release), primary_language=item.get("original_language"), poster_url=f"{self.IMAGE_BASE_URL}/w500{poster_path}" if poster_path else None, backdrop_url=f"{self.IMAGE_BASE_URL}/original{backdrop_path}" if backdrop_path else None, popularity_score=item.get("popularity"), external_url=f"https://www.themoviedb.org/{'movie' if media_type == MediaType.MOVIE else 'tv'}/{external_id}", attribution_text="Data provided by TMDB", attribution_url="https://www.themoviedb.org/", metadata_json=item))
        return ProviderSeedPage(provider="tmdb", media_type=media_type, seed_kind=seed_kind, cursor=str(page), next_cursor=str(page + 1) if page < int(data.get("total_pages", 0)) else None, results=results)
