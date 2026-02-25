from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Awaitable

import httpx

from app.config import settings

OUTPUT_FILE = Path(__file__).parent.parent / "static" / "data" / "tfl_stations.json"
DEFAULT_MODES = ["tube", "overground"]
PAGE_SIZE = 1000


def normalize_station_name(value: str) -> str:
    normalized = (value or "").strip().lower()
    suffixes = [
        " underground station",
        " overground station",
        " station",
    ]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    return normalized


def _format_station_name(raw_name: str, modes: list[str]) -> str:
    cleaned = (raw_name or "").strip()
    if not cleaned:
        return cleaned

    lower = cleaned.lower()
    if lower.endswith("underground station") or lower.endswith("overground station"):
        return cleaned

    mode_set = set(modes or [])
    if "tube" in mode_set and "overground" not in mode_set:
        base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
        return f"{base} Underground Station"
    if "overground" in mode_set and "tube" not in mode_set:
        base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
        return f"{base} Overground Station"
    return cleaned


def _choose_better_name(current: str, new: str, modes: list[str]) -> str:
    current_fmt = _format_station_name(current, modes)
    new_fmt = _format_station_name(new, modes)
    current_station = current_fmt.lower().endswith("station")
    new_station = new_fmt.lower().endswith("station")

    if new_station and not current_station:
        return new_fmt
    if current_station and not new_station:
        return current_fmt
    if len(new_fmt) > len(current_fmt):
        return new_fmt
    return current_fmt


def station_record_from_stop(stop: dict, allowed_modes: set[str]) -> dict | None:
    modes = [mode for mode in (stop.get("modes") or []) if mode in allowed_modes]
    if not modes:
        return None

    stop_type = (stop.get("stopType") or "").lower()
    if "entrance" in stop_type:
        return None

    station_id = (stop.get("stationNaptan") or stop.get("naptanId") or stop.get("id") or "").strip()
    if not station_id:
        return None
    if station_id.upper().startswith("HUB"):
        return None

    name = (stop.get("commonName") or stop.get("name") or "").strip()
    if not name:
        return None

    name = _format_station_name(name, modes)
    record = {
        "id": station_id,
        "name": name,
        "name_normalized": normalize_station_name(name),
        "modes": sorted(set(modes)),
    }
    if stop.get("lat") is not None:
        record["lat"] = stop.get("lat")
    if stop.get("lon") is not None:
        record["lon"] = stop.get("lon")
    return record


def merge_station_records(existing: dict, incoming: dict) -> dict:
    merged_modes = sorted(set((existing.get("modes") or []) + (incoming.get("modes") or [])))
    merged_name = _choose_better_name(existing.get("name") or "", incoming.get("name") or "", merged_modes)
    merged = {
        "id": existing["id"],
        "name": merged_name,
        "name_normalized": normalize_station_name(merged_name),
        "modes": merged_modes,
    }
    lat = existing.get("lat", incoming.get("lat"))
    lon = existing.get("lon", incoming.get("lon"))
    if lat is not None:
        merged["lat"] = lat
    if lon is not None:
        merged["lon"] = lon
    return merged


def extract_station_records(payload: dict, modes: list[str]) -> list[dict]:
    allowed_modes = set(modes)
    stop_points = payload.get("stopPoints") or []
    records: list[dict] = []
    for stop in stop_points:
        record = station_record_from_stop(stop, allowed_modes)
        if record:
            records.append(record)
    return records


async def fetch_mode_page(
    client: httpx.AsyncClient,
    base_url: str,
    modes: list[str],
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict:
    params: dict[str, str | int] = {"page": page, "pageSize": page_size}
    if settings.tfl_app_key:
        params["app_key"] = settings.tfl_app_key
    if settings.tfl_app_id:
        params["app_id"] = settings.tfl_app_id

    mode_param = ",".join(modes)
    response = await client.get(f"{base_url.rstrip('/')}/StopPoint/Mode/{mode_param}", params=params)
    response.raise_for_status()
    return response.json()


async def build_tfl_station_index(
    fetcher: Callable[[int], Awaitable[dict]],
    modes: list[str],
) -> list[dict]:
    stations_by_id: dict[str, dict] = {}
    page = 1
    previous_count = -1

    while True:
        payload = await fetcher(page)
        extracted = extract_station_records(payload, modes)

        for record in extracted:
            station_id = record["id"]
            existing = stations_by_id.get(station_id)
            if existing is None:
                stations_by_id[station_id] = record
            else:
                stations_by_id[station_id] = merge_station_records(existing, record)

        total = payload.get("total")
        page_size = payload.get("pageSize") or PAGE_SIZE
        if not extracted:
            break
        if len(stations_by_id) == previous_count:
            break
        if isinstance(total, int) and page * int(page_size) >= total:
            break

        previous_count = len(stations_by_id)
        page += 1

    return sorted(stations_by_id.values(), key=lambda item: (item.get("name_normalized") or "", item["id"]))


async def refresh_tfl_stations(output_file: Path = OUTPUT_FILE, modes: list[str] | None = None) -> int:
    target_modes = modes or DEFAULT_MODES
    base_url = settings.tfl_api_base_url
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def fetcher(page: int) -> dict:
            return await fetch_mode_page(client, base_url, target_modes, page)

        records = await build_tfl_station_index(fetcher, target_modes)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    return len(records)


def main() -> None:
    total = asyncio.run(refresh_tfl_stations())
    print(f"Wrote {total} TfL stations to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
