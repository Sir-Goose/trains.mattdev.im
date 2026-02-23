from fastapi.testclient import TestClient

from app.main import app
from app.models.board import Board
from app.services.rail_api import BoardFetchResult


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
