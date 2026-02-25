from datetime import datetime, timezone

from app.models.tfl import TflLineStatusSummary
from app.models.tfl import TflPrediction
from app.services.display_mapper import group_tfl_trains_by_line, map_tfl_predictions


def test_group_tfl_trains_by_line_groups_and_sorts_soonest_first():
    trains = [
        {
            "line_id": "jubilee",
            "line_name": "Jubilee",
            "time_to_station": 180,
            "expected_arrival": datetime(2026, 1, 1, 10, 23, tzinfo=timezone.utc),
        },
        {
            "line_id": "victoria",
            "line_name": "Victoria",
            "time_to_station": 60,
            "expected_arrival": datetime(2026, 1, 1, 10, 21, tzinfo=timezone.utc),
        },
        {
            "line_id": "victoria",
            "line_name": "Victoria",
            "time_to_station": 120,
            "expected_arrival": datetime(2026, 1, 1, 10, 22, tzinfo=timezone.utc),
        },
    ]

    status = [
        TflLineStatusSummary(
            line_id="victoria",
            line_name="Victoria",
            status_severity=10,
            status_description="Good Service",
            reason=None,
        )
    ]

    groups = group_tfl_trains_by_line(trains, status)

    assert len(groups) == 2
    assert groups[0]["line_name"] == "Victoria"
    assert groups[1]["line_name"] == "Jubilee"
    assert groups[0]["status"].status_description == "Good Service"
    assert groups[0]["line_color"] == "#0098D4"
    assert groups[1]["line_color"] == "#A0A5A9"


def test_group_tfl_trains_by_line_handles_unknown_line_last():
    trains = [
        {
            "line_id": "victoria",
            "line_name": "Victoria",
            "time_to_station": 60,
            "expected_arrival": datetime(2026, 1, 1, 10, 21, tzinfo=timezone.utc),
        },
        {
            "line_id": None,
            "line_name": None,
            "time_to_station": None,
            "expected_arrival": None,
        },
    ]

    groups = group_tfl_trains_by_line(trains, [])

    assert groups[0]["line_name"] == "Victoria"
    assert groups[-1]["line_name"] == "Unknown line"
    assert groups[-1]["line_color"] == "#5CC8FF"


def test_map_tfl_predictions_builds_service_url():
    prediction = TflPrediction(
        lineId="victoria",
        lineName="Victoria",
        naptanId="940GZZLUBXN",
        destinationNaptanId="940GZZLUGPK",
        direction="northbound",
        destinationName="Walthamstow Central Underground Station",
        stationName="Brixton Underground Station",
        tripId="trip-1",
        vehicleId="veh-1",
        expectedArrival="2026-01-01T12:00:00Z",
    )

    mapped = map_tfl_predictions([prediction])[0]

    assert mapped["service_url"] is not None
    assert "/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK" in mapped["service_url"]
    assert "trip_id=trip-1" in mapped["service_url"]
    assert mapped["route_unavailable"] is False


def test_map_tfl_predictions_normalizes_unknown_platform_to_none():
    prediction = TflPrediction(
        lineId="mildmay",
        lineName="Mildmay",
        naptanId="910GACTNCTL",
        destinationNaptanId="910GCLPHMJC",
        destinationName="Clapham Junction Rail Station",
        platformName="Unknown",
        expectedArrival="2026-01-01T12:00:00Z",
    )

    mapped = map_tfl_predictions([prediction])[0]

    assert mapped["platform"] is None
