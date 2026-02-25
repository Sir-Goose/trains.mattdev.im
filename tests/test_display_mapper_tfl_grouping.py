from datetime import datetime, timezone

from app.models.tfl import TflLineStatusSummary
from app.services.display_mapper import group_tfl_trains_by_line


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
