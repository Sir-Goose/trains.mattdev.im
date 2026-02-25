from fastapi.testclient import TestClient

from app.main import app
from app.models.board import Board
from app.models.tfl import TflBoard
from app.services.rail_api import BoardFetchResult
from app.services.tfl_api import TflBoardFetchResult


def test_get_board_returns_wrapped_payload(monkeypatch):
    async def fake_get_board(crs_code: str, use_cache: bool = True):
        board = Board(
            locationName='Leatherhead',
            crs=crs_code.upper(),
            generatedAt='2026-01-01T12:00:00+00:00',
            trainServices=[],
        )
        return BoardFetchResult(board=board, from_cache=True)

    monkeypatch.setattr('app.routers.boards.rail_api_service.get_board', fake_get_board)

    client = TestClient(app)
    response = client.get('/api/boards/lhd')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['cached'] is True
    assert payload['data']['crs'] == 'LHD'


def test_get_tfl_board_returns_wrapped_payload(monkeypatch):
    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        board = TflBoard(
            stop_point_id=stop_point_id,
            station_name='Brixton Underground Station',
            generated_at='2026-01-01T12:00:00+00:00',
            pulled_at='2026-01-01T12:00:00+00:00',
            trains=[],
            line_status=[],
        )
        return TflBoardFetchResult(board=board, from_cache=False)

    monkeypatch.setattr('app.routers.boards.tfl_api_service.get_board', fake_get_board)

    client = TestClient(app)
    response = client.get('/api/boards/tfl/940GZZLUBXN')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['cached'] is False
    assert payload['data']['stop_point_id'] == '940GZZLUBXN'


def test_get_tfl_passing_is_not_supported():
    client = TestClient(app)
    response = client.get('/api/boards/tfl/940GZZLUBXN/passing')

    assert response.status_code == 404


def test_get_tfl_departures_filters_outbound(monkeypatch):
    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        board = TflBoard(
            stop_point_id=stop_point_id,
            station_name='Brixton Underground Station',
            generated_at='2026-01-01T12:00:00+00:00',
            pulled_at='2026-01-01T12:00:00+00:00',
            trains=[
                {"direction": "outbound", "destinationName": "Victoria", "expectedArrival": "2026-01-01T12:01:00Z"},
                {"direction": "inbound", "destinationName": "Stockwell", "expectedArrival": "2026-01-01T12:02:00Z"},
            ],
            line_status=[],
        )
        return TflBoardFetchResult(board=board, from_cache=False)

    monkeypatch.setattr('app.routers.boards.tfl_api_service.get_board', fake_get_board)

    client = TestClient(app)
    response = client.get('/api/boards/tfl/940GZZLUBXN/departures')

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]['direction'] == 'outbound'
