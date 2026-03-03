import pytest

from app.middleware.cache import cache
from app.models.board import Board, ServiceDetails
from app.services.rail_api import RailAPIService


def _sample_service_detail() -> ServiceDetails:
    return ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="service-1",
        origin=[{"locationName": "Guildford", "crs": "GLD"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
    )


def test_cache_board_service_hints_stores_lookup_metadata():
    cache.clear()
    service = RailAPIService()
    board = Board(
        locationName="Leatherhead",
        crs="LHD",
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        trainServices=[
            {
                "serviceID": "service-1",
                "sta": "21:10",
                "std": "21:10",
                "origin": [{"locationName": "Guildford", "crs": "GLD"}],
                "destination": [{"locationName": "London Waterloo", "crs": "WAT"}],
                "operator": "South Western Railway",
                "operatorCode": "SW",
                "serviceType": "train",
            }
        ],
    )

    service._cache_board_service_hints(board)
    payload = cache.get(service._service_hint_cache_key("service-1"))

    assert payload is not None
    assert payload["crs"] == "LHD"
    assert payload["scheduled_arrival_time"] == "21:10"
    assert payload["scheduled_departure_time"] == "21:10"
    assert payload["origin_crs"] == "GLD"
    assert payload["destination_crs"] == "WAT"
    assert payload["operator_code"] == "SW"


@pytest.mark.asyncio
async def test_get_service_route_from_timetable_uses_cached_hint(monkeypatch):
    cache.clear()
    service = RailAPIService()

    cache.set(
        service._service_hint_cache_key("service-1"),
        {
            "crs": "LHD",
            "scheduled_arrival_time": "21:10",
            "scheduled_departure_time": "21:10",
            "origin_crs": "GLD",
            "destination_crs": "WAT",
            "operator_code": "SW",
            "operator_name": "South Western Railway",
            "service_type": "train",
            "generated_at": "2026-01-01T12:00:00+00:00",
        },
        600,
    )

    captured = {}

    def fake_find_service_detail(service_id: str, requested_crs: str, hint):
        captured["service_id"] = service_id
        captured["requested_crs"] = requested_crs
        captured["hint"] = hint
        return _sample_service_detail()

    monkeypatch.setattr("app.services.rail_api.nr_timetable_service.find_service_detail", fake_find_service_detail)

    detail = await service.get_service_route_from_timetable("LHD", "service-1")

    assert detail is not None
    assert captured["service_id"] == "service-1"
    assert captured["requested_crs"] == "LHD"
    assert captured["hint"].origin_crs == "GLD"
    assert captured["hint"].destination_crs == "WAT"
    assert captured["hint"].operator_code == "SW"
