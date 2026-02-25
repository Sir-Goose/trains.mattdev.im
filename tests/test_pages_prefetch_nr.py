from fastapi.testclient import TestClient

from app.main import app


def test_nr_board_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_board_prefetch_skips_when_board_from_cache(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": True,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures')

    assert response.status_code == 200
    assert calls == []


def test_nr_board_content_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures/content')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_board_refresh_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures/refresh')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]
