from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Iterable
from urllib.parse import urlencode

from app.models.board import Train
from app.models.tfl import TflPrediction

DEFAULT_TFL_LINE_COLOR = "#5CC8FF"

TFL_LINE_COLORS_BY_ID = {
    "bakerloo": "#B36305",
    "central": "#E32017",
    "circle": "#FFD300",
    "district": "#00782A",
    "hammersmith-city": "#F3A9BB",
    "hammersmithandcity": "#F3A9BB",
    "jubilee": "#A0A5A9",
    "metropolitan": "#9B0056",
    "northern": "#000000",
    "piccadilly": "#003688",
    "victoria": "#0098D4",
    "waterloo-city": "#95CDBA",
    "waterlooandcity": "#95CDBA",
    "london-overground": "#EE7C0E",
    "overground": "#EE7C0E",
    "liberty": "#61686B",
    "lioness": "#FDB71A",
    "mildmay": "#0055B8",
    "suffragette": "#00A651",
    "weaver": "#78206E",
    "windrush": "#D3222A",
}

TFL_LINE_COLORS_BY_NAME = {
    "bakerloo": "#B36305",
    "central": "#E32017",
    "circle": "#FFD300",
    "district": "#00782A",
    "hammersmith & city": "#F3A9BB",
    "jubilee": "#A0A5A9",
    "metropolitan": "#9B0056",
    "northern": "#000000",
    "piccadilly": "#003688",
    "victoria": "#0098D4",
    "waterloo & city": "#95CDBA",
    "london overground": "#EE7C0E",
    "liberty": "#61686B",
    "lioness": "#FDB71A",
    "mildmay": "#0055B8",
    "suffragette": "#00A651",
    "weaver": "#78206E",
    "windrush": "#D3222A",
}


def _format_hhmm(dt) -> str:
    if not dt:
        return "No information"
    return dt.astimezone(timezone.utc).strftime("%H:%M")


def _normalize_tfl_platform(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    unknown_tokens = {
        "unknown",
        "platform unknown",
        "n/a",
        "na",
        "none",
        "-",
        "?",
    }
    if cleaned.lower() in unknown_tokens:
        return None
    return cleaned


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return f"rgba(92, 200, 255, {alpha})"
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _tfl_line_color(line_id: str | None, line_name: str | None) -> str:
    normalized_id = (line_id or "").strip().lower()
    normalized_name = (line_name or "").strip().lower()
    if normalized_id and normalized_id in TFL_LINE_COLORS_BY_ID:
        return TFL_LINE_COLORS_BY_ID[normalized_id]
    if normalized_name and normalized_name in TFL_LINE_COLORS_BY_NAME:
        return TFL_LINE_COLORS_BY_NAME[normalized_name]
    return DEFAULT_TFL_LINE_COLOR


def map_nr_trains(crs: str, trains: Iterable[Train]) -> list[dict]:
    mapped: list[dict] = []
    for train in trains:
        service_url = f"/service/{crs}/{train.service_id}" if train.service_id else None
        mapped.append(
            {
                "is_cancelled": train.is_cancelled,
                "time_status_class": train.time_status_class,
                "scheduled_departure_time": train.scheduled_departure_time,
                "scheduled_arrival_time": train.scheduled_arrival_time,
                "display_time_departure": train.display_time_departure,
                "display_time_arrival": train.display_time_arrival,
                "destination_name": train.destination_name,
                "destination_via": train.destination_via,
                "destination_via_prefix": "via",
                "origin_name": train.origin_name,
                "platform": train.platform,
                "operator": train.operator,
                "line_name": None,
                "service_id": train.service_id,
                "service_url": service_url,
                "route_unavailable": not bool(service_url),
            }
        )
    return mapped


def map_tfl_predictions(predictions: Iterable[TflPrediction]) -> list[dict]:
    mapped: list[dict] = []
    for prediction in predictions:
        expected = _format_hhmm(prediction.expected_arrival)
        subtitle = prediction.current_location or prediction.towards
        line_id = (prediction.line_id or "").strip().lower()
        from_stop_id = (prediction.naptan_id or "").strip()
        to_stop_id = (prediction.destination_naptan_id or "").strip()
        service_url = None
        if line_id and from_stop_id and to_stop_id:
            query_params: dict[str, str] = {}
            if prediction.direction:
                query_params["direction"] = prediction.direction
            if prediction.trip_id:
                query_params["trip_id"] = prediction.trip_id
            if prediction.vehicle_id:
                query_params["vehicle_id"] = prediction.vehicle_id
            if prediction.expected_arrival:
                query_params["expected_arrival"] = prediction.expected_arrival.isoformat()
            if prediction.station_name:
                query_params["station_name"] = prediction.station_name
            if prediction.destination_name:
                query_params["destination_name"] = prediction.destination_name
            service_url = f"/service/tfl/{line_id}/{from_stop_id}/{to_stop_id}"
            if query_params:
                service_url = f"{service_url}?{urlencode(query_params)}"
        mapped.append(
            {
                "is_cancelled": False,
                "time_status_class": "time-ontime",
                "scheduled_departure_time": expected,
                "scheduled_arrival_time": expected,
                "display_time_departure": expected,
                "display_time_arrival": expected,
                "destination_name": prediction.destination_name,
                "destination_via": subtitle,
                "destination_via_prefix": None,
                "origin_name": prediction.towards,
                "platform": _normalize_tfl_platform(prediction.platform_name),
                "operator": "TfL",
                "line_id": prediction.line_id,
                "line_name": prediction.line_name,
                "expected_arrival": prediction.expected_arrival,
                "time_to_station": prediction.time_to_station,
                "from_stop_id": from_stop_id,
                "to_stop_id": to_stop_id,
                "direction": prediction.direction,
                "trip_id": prediction.trip_id,
                "vehicle_id": prediction.vehicle_id,
                "station_name": prediction.station_name,
                "service_url": service_url,
                "route_unavailable": not bool(service_url),
            }
        )
    return mapped


def group_tfl_trains_by_line(trains: list[dict], line_status: list) -> list[dict]:
    grouped: dict[str, dict] = {}
    grouped_trains: dict[str, list[dict]] = defaultdict(list)

    status_by_line_id: dict[str, object] = {}
    status_by_line_name: dict[str, object] = {}
    for status in line_status or []:
        line_id = getattr(status, "line_id", None)
        line_name = getattr(status, "line_name", None)
        if line_id:
            status_by_line_id[line_id] = status
        if line_name:
            status_by_line_name[line_name.lower()] = status

    def earliest_sort_tuple(rows: list[dict]) -> tuple:
        candidates: list[tuple[int, float]] = []
        for row in rows:
            tts = row.get("time_to_station")
            expected = row.get("expected_arrival")
            if tts is not None:
                candidates.append((int(tts), expected.timestamp() if expected else float("inf")))
            elif expected is not None:
                candidates.append((10**9, expected.timestamp()))

        if candidates:
            return min(candidates)
        return (10**9, float("inf"))

    for train in trains:
        line_name = (train.get("line_name") or "").strip() or "Unknown line"
        line_id = (train.get("line_id") or "").strip() or None
        group_key = line_id or line_name.lower()

        if group_key not in grouped:
            status = status_by_line_id.get(line_id) if line_id else None
            if status is None:
                status = status_by_line_name.get(line_name.lower())
            grouped[group_key] = {
                "line_id": line_id or "unknown",
                "line_name": line_name,
                "line_color": _tfl_line_color(line_id, line_name),
                "status": status,
                "trains": [],
                "next_time_epoch": None,
            }

        grouped_trains[group_key].append(train)

    line_groups: list[dict] = []
    for key, group in grouped.items():
        rows = grouped_trains[key]
        rows.sort(
            key=lambda row: (
                row.get("time_to_station") if row.get("time_to_station") is not None else 10**9,
                row.get("expected_arrival").timestamp() if row.get("expected_arrival") else float("inf"),
            )
        )
        earliest = earliest_sort_tuple(rows)
        group["trains"] = rows
        group["next_time_epoch"] = None if earliest[1] == float("inf") else earliest[1]
        group["line_tint"] = _hex_to_rgba(group["line_color"], 0.12)
        group["line_border_tint"] = _hex_to_rgba(group["line_color"], 0.42)
        line_groups.append(group)

    line_groups.sort(
        key=lambda group: (
            10**9 if group["next_time_epoch"] is None else 0,
            earliest_sort_tuple(group["trains"])[0],
            group["line_name"].lower(),
        )
    )

    return line_groups
