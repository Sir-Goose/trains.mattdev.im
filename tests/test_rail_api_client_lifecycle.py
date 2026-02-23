import pytest

from app.services.rail_api import RailAPIService


@pytest.mark.asyncio
async def test_async_client_reused_and_closed(monkeypatch):
    created_clients = []

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.is_closed = False
            created_clients.append(self)

        async def aclose(self):
            self.closed = True
            self.is_closed = True

    monkeypatch.setattr('app.services.rail_api.httpx.AsyncClient', DummyAsyncClient)

    service = RailAPIService()

    client_one = await service._get_client()
    client_two = await service._get_client()

    assert client_one is client_two
    assert len(created_clients) == 1

    await service.shutdown()

    assert created_clients[0].closed is True
