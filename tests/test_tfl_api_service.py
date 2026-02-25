from app.models.tfl import TflPrediction
from app.services.tfl_api import TflAPIError, TflAPIService


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


def test_prediction_sort_primary_time_to_station():
    service = TflAPIService()
    soon = TflPrediction(destinationName="A", timeToStation=60, expectedArrival="2026-01-01T12:01:00Z")
    later = TflPrediction(destinationName="B", timeToStation=120, expectedArrival="2026-01-01T12:00:30Z")

    sorted_items = sorted([later, soon], key=service._prediction_sort_key)

    assert sorted_items[0].destination_name == "A"
