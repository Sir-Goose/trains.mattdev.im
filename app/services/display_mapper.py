from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Iterable

from app.models.board import Train
from app.models.tfl import TflPrediction


def _format_hhmm(dt) -> str:
    if not dt:
        return "No information"
    return dt.astimezone(timezone.utc).strftime("%H:%M")


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
                "platform": prediction.platform_name,
                "operator": "TfL",
                "line_id": prediction.line_id,
                "line_name": prediction.line_name,
                "expected_arrival": prediction.expected_arrival,
                "time_to_station": prediction.time_to_station,
                "service_url": None,
                "route_unavailable": False,
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
        line_groups.append(group)

    line_groups.sort(
        key=lambda group: (
            10**9 if group["next_time_epoch"] is None else 0,
            earliest_sort_tuple(group["trains"])[0],
            group["line_name"].lower(),
        )
    )

    return line_groups
