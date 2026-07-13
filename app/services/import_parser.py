from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from app.models.import_job import ImportSource
from app.models.media import LibraryStatus, MediaType


class ImportParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedImportRow:
    row_number: int
    title: str
    media_type: MediaType
    status: LibraryStatus
    rating_value: int | None
    release_year: int | None
    external_provider: str | None
    external_id: str | None
    external_url: str | None
    raw: dict[str, str]

    def as_payload(self) -> dict:
        return {
            "row_number": self.row_number, "title": self.title, "media_type": self.media_type.value,
            "status": self.status.value, "rating_value": self.rating_value, "release_year": self.release_year,
            "external_provider": self.external_provider, "external_id": self.external_id,
            "external_url": self.external_url, "raw": self.raw,
        }


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _reader(content: bytes) -> csv.DictReader:
    if b"\x00" in content:
        raise ImportParseError("CSV files cannot contain NUL bytes")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportParseError("CSV files must be UTF-8 encoded") from error
    try:
        return csv.DictReader(io.StringIO(text), skipinitialspace=True)
    except csv.Error as error:
        raise ImportParseError("The CSV file is malformed") from error


def _rating(value: str | None) -> int | None:
    raw = _clean(value)
    if raw is None:
        return None
    try:
        parsed = float(raw)
    except ValueError as error:
        raise ImportParseError("Ratings must be numeric") from error
    if parsed == 0:
        return None
    if 0 < parsed <= 5:
        return round(parsed * 20)
    if parsed.is_integer() and 1 <= parsed <= 100:
        return int(parsed)
    raise ImportParseError("Ratings must be between 0-5 or 1-100")


def _year(value: str | None) -> int | None:
    raw = _clean(value)
    if raw is None:
        return None
    if not raw.isdigit() or not 1800 <= int(raw) <= 3000:
        raise ImportParseError("Release year must be a four-digit year")
    return int(raw)


def parse_letterboxd_csv(content: bytes, *, max_rows: int) -> list[ParsedImportRow]:
    reader = _reader(content)
    headers = {header.strip().casefold() for header in (reader.fieldnames or []) if header}
    if "name" not in headers:
        raise ImportParseError("Letterboxd CSV must include the Name column")
    rows: list[ParsedImportRow] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            raise ImportParseError(f"An import can contain at most {max_rows} rows")
        row = {str(key).strip().casefold(): value or "" for key, value in raw_row.items() if key}
        title = _clean(row.get("name"))
        if title is None:
            continue
        rows.append(ParsedImportRow(
            row_number=row_number, title=title, media_type=MediaType.MOVIE,
            status=LibraryStatus.COMPLETED if _clean(row.get("watched date")) else LibraryStatus.PLANNED,
            rating_value=_rating(row.get("rating")), release_year=_year(row.get("year")),
            external_provider="imdb" if _clean(row.get("imdb uri")) else None,
            external_id=_clean(row.get("imdb uri")).rsplit("/", 1)[-1] if _clean(row.get("imdb uri")) else None,
            external_url=_clean(row.get("letterboxd uri")), raw={key: value for key, value in row.items()},
        ))
    if not rows:
        raise ImportParseError("The CSV does not contain any importable rows")
    return rows


def parse_generic_csv(content: bytes, *, default_media_type: MediaType | None, max_rows: int) -> list[ParsedImportRow]:
    reader = _reader(content)
    headers = {header.strip().casefold() for header in (reader.fieldnames or []) if header}
    if not ({"title", "name"} & headers):
        raise ImportParseError("Generic CSV must include a title or name column")
    rows: list[ParsedImportRow] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            raise ImportParseError(f"An import can contain at most {max_rows} rows")
        row = {str(key).strip().casefold(): value or "" for key, value in raw_row.items() if key}
        title = _clean(row.get("title") or row.get("name"))
        if title is None:
            continue
        media_type_value = _clean(row.get("media_type") or row.get("type"))
        try:
            media_type = MediaType((media_type_value or (default_media_type.value if default_media_type else "")).upper())
        except ValueError as error:
            raise ImportParseError(f"Row {row_number}: media_type is required and must be valid") from error
        status_value = _clean(row.get("status"))
        try:
            library_status = LibraryStatus((status_value or LibraryStatus.PLANNED.value).upper())
        except ValueError as error:
            raise ImportParseError(f"Row {row_number}: invalid library status") from error
        rows.append(ParsedImportRow(
            row_number=row_number, title=title, media_type=media_type, status=library_status,
            rating_value=_rating(row.get("rating") or row.get("rating_value")), release_year=_year(row.get("year") or row.get("release_year")),
            external_provider=_clean(row.get("external_provider") or row.get("provider")),
            external_id=_clean(row.get("external_id") or row.get("provider_id")), external_url=_clean(row.get("external_url") or row.get("url")),
            raw={key: value for key, value in row.items()},
        ))
    if not rows:
        raise ImportParseError("The CSV does not contain any importable rows")
    return rows


def parse_csv_import(content: bytes, *, source: ImportSource, default_media_type: MediaType | None, max_rows: int) -> list[dict]:
    if source == ImportSource.LETTERBOXD:
        rows = parse_letterboxd_csv(content, max_rows=max_rows)
    elif source == ImportSource.GENERIC:
        rows = parse_generic_csv(content, default_media_type=default_media_type, max_rows=max_rows)
    else:
        raise ImportParseError(f"{source.value.title()} imports must be initiated through their provider connection")
    return [row.as_payload() for row in rows]
