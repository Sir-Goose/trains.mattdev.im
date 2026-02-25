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
