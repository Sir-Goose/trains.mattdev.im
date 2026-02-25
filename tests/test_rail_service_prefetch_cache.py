from app.middleware.cache import cache
from app.models.board import ServiceDetails
from app.services.rail_api import RailAPIService
import pytest


@pytest.mark.asyncio
async def test_get_service_route_following_cached_reuses_cached_value(monkeypatch):
    cache.clear()
    service = RailAPIService()

    detail = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="service-1",
        origin=[{"locationName": "Dorking", "crs": "DKG"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
    )

    calls = 0

    async def fake_get_service_route_following(*args, **kwargs):
        nonlocal calls
        calls += 1
        return detail

    monkeypatch.setattr(service, "get_service_route_following", fake_get_service_route_following)

    first = await service.get_service_route_following_cached("LHD", "service-1", use_cache=True)
    second = await service.get_service_route_following_cached("LHD", "service-1", use_cache=True)

    assert first is not None
    assert second is not None
    assert calls == 1
