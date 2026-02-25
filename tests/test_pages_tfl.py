from fastapi.testclient import TestClient

from app.main import app
from app.models.tfl_service import TflServiceDetail, TflServiceStop


def test_legacy_board_route_redirects_to_nr():
    client = TestClient(app)
    response = client.get('/board/LHD/departures', follow_redirects=False)

    assert response.status_code == 307
    assert response.headers['location'] == '/board/nr/LHD/departures'


def test_tfl_passing_route_returns_not_found():
    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUBXN/passing')

    assert response.status_code == 404


def test_tfl_board_page_renders_provider_badge(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [],
            "line_groups": [],
            "total_trains": 0,
            "station_name": "Brixton Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUBXN/departures')

    assert response.status_code == 200
    assert 'TfL' in response.text


def test_tfl_board_page_does_not_prefix_location_with_via(monkeypatch):
    row = {
        "is_cancelled": False,
        "time_status_class": "time-ontime",
        "scheduled_departure_time": "10:21",
        "scheduled_arrival_time": "10:21",
        "display_time_departure": "10:21",
        "display_time_arrival": "10:21",
        "destination_name": "Walthamstow Central Underground Station",
        "destination_via": "Approaching Green Park",
        "destination_via_prefix": None,
        "origin_name": "Northbound",
        "platform": "Platform 3",
        "operator": "TfL",
        "line_name": "Victoria",
        "line_id": "victoria",
        "service_url": None,
        "route_unavailable": False,
    }

    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [row],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "status": None,
                    "trains": [row],
                    "next_time_epoch": 0,
                }
            ],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "10:20:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/HUBGPK/departures')

    assert response.status_code == 200
    assert 'Approaching Green Park' in response.text
    assert 'via Approaching Green Park' not in response.text


def test_tfl_board_page_renders_grouped_line_sections(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "status": None,
                    "trains": [
                        {
                            "is_cancelled": False,
                            "time_status_class": "time-ontime",
                            "display_time_departure": "10:21",
                            "display_time_arrival": "10:21",
                            "destination_name": "Walthamstow Central Underground Station",
                            "destination_via": "Approaching Green Park",
                            "destination_via_prefix": None,
                            "origin_name": "Northbound",
                            "platform": "Platform 3",
                            "operator": "TfL",
                            "line_name": "Victoria",
                            "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                            "route_unavailable": False,
                        }
                    ],
                    "next_time_epoch": 0,
                },
                {
                    "line_id": "jubilee",
                    "line_name": "Jubilee",
                    "status": None,
                    "trains": [
                        {
                            "is_cancelled": False,
                            "time_status_class": "time-ontime",
                            "display_time_departure": "10:22",
                            "display_time_arrival": "10:22",
                            "destination_name": "Stratford Underground Station",
                            "destination_via": "Between Bond Street and Green Park",
                            "destination_via_prefix": None,
                            "origin_name": "Southbound",
                            "platform": "Platform 6",
                            "operator": "TfL",
                            "line_name": "Jubilee",
                            "service_url": "/service/tfl/jubilee/940GZZLUGPK/940GZZLUSTD",
                            "route_unavailable": False,
                        }
                    ],
                    "next_time_epoch": 1,
                },
            ],
            "total_trains": 2,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "10:20:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/HUBGPK/departures')

    assert response.status_code == 200
    assert 'tfl-line-group-title' in response.text
    assert '>Victoria<' in response.text
    assert '>Jubilee<' in response.text
    assert '/service/tfl/victoria/' in response.text


def test_tfl_service_detail_page_renders_timeline(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[
            TflServiceStop(
                stop_id="940GZZLUBXN",
                stop_name="Brixton Underground Station",
                arrival_display="Due",
                departure_display="Due",
                is_current=True,
            ),
            TflServiceStop(
                stop_id="940GZZLUGPK",
                stop_name="Green Park Underground Station",
                arrival_display="8 min (10:29)",
                departure_display="8 min (10:29)",
                is_destination=True,
            ),
        ],
    )

    async def fake_get_service_route_detail(**kwargs):
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail', fake_get_service_route_detail)

    client = TestClient(app)
    response = client.get('/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK?direction=northbound')

    assert response.status_code == 200
    assert 'Brixton Underground Station' in response.text
    assert 'Green Park Underground Station' in response.text
    assert 'Exact match' in response.text
