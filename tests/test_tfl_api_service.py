from app.models.tfl import TflPrediction
from app.services.tfl_api import TflAPIError, TflAPIService
import pytest


def test_auth_params_key_only():
    service = TflAPIService()
    service.app_key = "test-key"
    service.app_id = ""

    assert service._auth_params() == {"app_key": "test-key"}


def test_auth_params_with_app_id():
    service = TflAPIService()
    service.app_key = "test-key"
    service.app_id = "test-id"

    assert service._auth_params() == {"app_key": "test-key", "app_id": "test-id"}


def test_auth_params_raises_without_key():
    service = TflAPIService()
    service.app_key = ""

    try:
        service._auth_params()
    except TflAPIError as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected TflAPIError when app_key is missing")


def test_predictions_for_view_prefers_direction_filter():
    service = TflAPIService()
    outbound = TflPrediction(direction="outbound", destinationName="A", expectedArrival="2026-01-01T12:00:00Z")
    inbound = TflPrediction(direction="inbound", destinationName="B", expectedArrival="2026-01-01T12:01:00Z")
    predictions = [outbound, inbound]

    departures = service.predictions_for_view(predictions, "departures")
    arrivals = service.predictions_for_view(predictions, "arrivals")

    assert len(departures) == 1
    assert departures[0].direction == "outbound"
    assert len(arrivals) == 1
    assert arrivals[0].direction == "inbound"


def test_predictions_for_view_falls_back_to_all():
    service = TflAPIService()
    unknown = TflPrediction(direction=None, destinationName="A", expectedArrival="2026-01-01T12:00:00Z")

    departures = service.predictions_for_view([unknown], "departures")
    arrivals = service.predictions_for_view([unknown], "arrivals")

    assert len(departures) == 1
    assert len(arrivals) == 1


def test_predictions_for_view_keeps_no_direction_services_visible():
    service = TflAPIService()
    outbound = TflPrediction(direction="outbound", destinationName="A", expectedArrival="2026-01-01T12:00:00Z")
    inbound = TflPrediction(direction="inbound", destinationName="B", expectedArrival="2026-01-01T12:01:00Z")
    unknown = TflPrediction(direction=None, destinationName="C", expectedArrival="2026-01-01T12:02:00Z")

    departures = service.predictions_for_view([outbound, inbound, unknown], "departures")
    arrivals = service.predictions_for_view([outbound, inbound, unknown], "arrivals")

    assert len(departures) == 2
    assert len(arrivals) == 2
    assert any(item.destination_name == "C" for item in departures)
    assert any(item.destination_name == "C" for item in arrivals)


def test_prediction_sort_primary_time_to_station():
    service = TflAPIService()
    soon = TflPrediction(destinationName="A", timeToStation=60, expectedArrival="2026-01-01T12:01:00Z")
    later = TflPrediction(destinationName="B", timeToStation=120, expectedArrival="2026-01-01T12:00:30Z")

    sorted_items = sorted([later, soon], key=service._prediction_sort_key)

    assert sorted_items[0].destination_name == "A"


@pytest.mark.asyncio
async def test_resolve_stop_point_id_maps_hub_to_mode_child(monkeypatch):
    service = TflAPIService()

    async def fake_get_json(path: str, params=None):
        assert path == "/StopPoint/HUBBDS"
        return {
            "children": [
                {"id": "910GBONDST", "modes": ["elizabeth-line"]},
                {"id": "940GZZLUBND", "modes": ["tube"]},
            ]
        }

    monkeypatch.setattr(service, "_get_json", fake_get_json)
    resolved = await service.resolve_stop_point_id("HUBBDS")

    assert resolved == "940GZZLUBND"


def test_match_prediction_for_click_prefers_trip_id():
    service = TflAPIService()
    p1 = TflPrediction(
        lineId="victoria",
        destinationNaptanId="940GZZLUGPK",
        tripId="trip-a",
        vehicleId="veh-1",
        expectedArrival="2026-01-01T12:01:00Z",
    )
    p2 = TflPrediction(
        lineId="victoria",
        destinationNaptanId="940GZZLUGPK",
        tripId="trip-b",
        vehicleId="veh-2",
        expectedArrival="2026-01-01T12:02:00Z",
    )

    matched = service._match_prediction_for_click(
        predictions=[p1, p2],
        line_id="victoria",
        to_stop_id="940GZZLUGPK",
        direction=None,
        trip_id="trip-b",
        vehicle_id=None,
        expected_arrival=None,
    )

    assert matched is not None
    assert matched.trip_id == "trip-b"


@pytest.mark.asyncio
async def test_get_service_route_detail_builds_stops_from_fallback(monkeypatch):
    service = TflAPIService()

    async def fake_resolve_stop_point_id(stop_id: str):
        return stop_id

    async def fake_get_predictions_for_stop(stop_point_id: str, use_cache: bool = True):
        return [
            TflPrediction(
                lineId="victoria",
                lineName="Victoria",
                stationName="Brixton Underground Station",
                destinationName="Green Park Underground Station",
                destinationNaptanId="940GZZLUGPK",
                naptanId=stop_point_id,
                direction="inbound",
                expectedArrival="2026-01-01T12:00:00Z",
            )
        ]

    async def fake_get_route_sequence(line_id: str, direction: str, use_cache: bool = True):
        return {}

    async def fake_get_timetable_payload(line_id: str, from_stop_id: str, to_stop_id: str, use_cache: bool = True):
        return {
            "stations": [
                {"id": from_stop_id, "name": "Brixton Underground Station"},
                {"id": to_stop_id, "name": "Green Park Underground Station"},
            ],
            "timetable": {
                "routes": [
                    {
                        "stationIntervals": [
                            {
                                "intervals": [
                                    {"stopId": from_stop_id, "timeToArrival": 0},
                                    {"stopId": to_stop_id, "timeToArrival": 8},
                                ]
                            }
                        ]
                    }
                ]
            },
        }

    monkeypatch.setattr(service, "resolve_stop_point_id", fake_resolve_stop_point_id)
    monkeypatch.setattr(service, "_get_predictions_for_stop", fake_get_predictions_for_stop)
    monkeypatch.setattr(service, "_get_route_sequence", fake_get_route_sequence)
    monkeypatch.setattr(service, "_get_timetable_payload", fake_get_timetable_payload)

    detail = await service.get_service_route_detail(
        line_id="victoria",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        direction="inbound",
    )

    assert detail.line_name == "Victoria"
    assert len(detail.stops) >= 2
    assert detail.stops[0].is_current is True
    assert any(stop.is_destination for stop in detail.stops)


@pytest.mark.asyncio
async def test_search_stop_points_normalizes_station_suffix_for_ranking(monkeypatch):
    service = TflAPIService()
    service.app_key = "test-key"

    async def fake_get_json(path: str, params=None):
        assert path == "/StopPoint/Search"
        return {
            "matches": [
                {"id": "940GZZLUWLO", "name": "Waterloo Underground Station", "modes": ["tube"]},
                {"id": "940GZZLUWRR", "name": "Warren Street Underground Station", "modes": ["tube"]},
                {"id": "940GZZLUEUS", "name": "Euston Underground Station", "modes": ["tube"]},
            ]
        }

    async def fake_resolve_stop_point_id(stop_id: str):
        return stop_id

    monkeypatch.setattr(service, "_get_json", fake_get_json)
    monkeypatch.setattr(service, "resolve_stop_point_id", fake_resolve_stop_point_id)

    results = await service.search_stop_points("waterloo", max_results=5)

    assert results
    assert results[0]["name"] == "Waterloo Underground Station"


@pytest.mark.asyncio
async def test_search_stop_points_formats_tube_station_name(monkeypatch):
    service = TflAPIService()
    service.app_key = "test-key"

    async def fake_get_json(path: str, params=None):
        assert path == "/StopPoint/Search"
        return {
            "matches": [
                {"id": "940GZZLUWLO", "name": "Waterloo", "modes": ["tube"]},
            ]
        }

    async def fake_resolve_stop_point_id(stop_id: str):
        return stop_id

    monkeypatch.setattr(service, "_get_json", fake_get_json)
    monkeypatch.setattr(service, "resolve_stop_point_id", fake_resolve_stop_point_id)

    results = await service.search_stop_points("waterloo", max_results=5)

    assert results
    assert results[0]["name"] == "Waterloo Underground Station"
