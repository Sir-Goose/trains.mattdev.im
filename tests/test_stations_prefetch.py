from fastapi.testclient import TestClient

from app.main import app


def test_search_prefetches_board_caches(monkeypatch):
    async def fake_search_stations_unified(query: str, view: str = "departures", limit: int = 10):
        return [
            {
                "provider": "nr",
                "name": "Leatherhead",
                "code": "LHD",
                "badge": "National Rail",
                "url": "/board/nr/LHD/departures",
            },
            {
                "provider": "tfl",
                "name": "Waterloo Underground Station",
                "code": "940GZZLUWLO",
                "badge": "TfL Tube",
                "url": "/board/tfl/940GZZLUWLO/departures",
            },
        ]

    nr_calls: list[str] = []
    tfl_calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        nr_calls.append(crs)

    def fake_schedule_tfl_board_prefetch(stop_point_id: str):
        tfl_calls.append(stop_point_id)

    monkeypatch.setattr('app.routers.stations.search_stations_unified', fake_search_stations_unified)
    monkeypatch.setattr('app.routers.stations.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)
    monkeypatch.setattr('app.routers.stations.prefetch_service.schedule_tfl_board_prefetch', fake_schedule_tfl_board_prefetch)

    client = TestClient(app)
    response = client.get('/api/stations/search?q=waterloo&view=departures')

    assert response.status_code == 200
    assert nr_calls == ["LHD"]
    assert tfl_calls == ["940GZZLUWLO"]


def test_search_prefetch_skips_empty_query(monkeypatch):
    nr_calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        nr_calls.append(crs)

    monkeypatch.setattr('app.routers.stations.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)

    client = TestClient(app)
    response = client.get('/api/stations/search?q=')

    assert response.status_code == 200
    assert response.text == ""
    assert nr_calls == []
