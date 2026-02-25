from __future__ import annotations

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
                "line_name": prediction.line_name,
                "service_url": None,
                "route_unavailable": False,
            }
        )
    return mapped
