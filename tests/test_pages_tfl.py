from fastapi.testclient import TestClient

from app.main import app


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
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [
                {
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
                    "service_url": None,
                    "route_unavailable": False,
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
