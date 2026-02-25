import asyncio

import pytest

from app.config import settings
from app.services.prefetch import PrefetchCoordinator


@pytest.mark.asyncio
async def test_prefetch_dedup_skips_duplicate_job(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    calls: list[tuple[str, str]] = []

    async def fake_get_service_route_following_cached(crs_code: str, service_id: str, use_cache: bool = True):
        calls.append((crs_code, service_id))
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_following_cached",
        fake_get_service_route_following_cached,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", "service-1")
        coordinator.schedule_nr_service_prefetch("LHD", "service-1")

        await asyncio.sleep(0.15)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == [("LHD", "service-1")]


@pytest.mark.asyncio
async def test_prefetch_releases_job_key_on_failure(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    calls = 0

    async def fake_get_service_route_following_cached(crs_code: str, service_id: str, use_cache: bool = True):
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_following_cached",
        fake_get_service_route_following_cached,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", "service-1")
        await asyncio.sleep(0.1)
        coordinator.schedule_nr_service_prefetch("LHD", "service-1")

        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == 2


@pytest.mark.asyncio
async def test_prefetch_respects_global_concurrency_limit(monkeypatch):
    old_limit = settings.prefetch_max_concurrency
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    settings.prefetch_max_concurrency = 1
    coordinator = PrefetchCoordinator()

    running = 0
    max_running = 0

    async def fake_get_service_route_detail_cached(**kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.05)
        running -= 1

    monkeypatch.setattr(
        "app.services.prefetch.tfl_api_service.get_service_route_detail_cached",
        fake_get_service_route_detail_cached,
    )

    try:
        coordinator.schedule_tfl_service_prefetch(
            {
                "line_id": "victoria",
                "from_stop_id": "940GZZLUGPK",
                "to_stop_id": "940GZZLUBXN",
            }
        )
        coordinator.schedule_tfl_service_prefetch(
            {
                "line_id": "victoria",
                "from_stop_id": "940GZZLUGPK",
                "to_stop_id": "940GZZLUSKW",
            }
        )

        await asyncio.sleep(0.2)
    finally:
        settings.prefetch_max_concurrency = old_limit
        settings.prefetch_enabled = old_enabled

    assert max_running == 1


@pytest.mark.asyncio
async def test_nr_board_prefetch_warms_board_cache(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()

    calls: list[str] = []

    async def fake_get_board(crs_code: str, use_cache: bool = True):
        calls.append(crs_code)
        await asyncio.sleep(0.01)
        return None

    monkeypatch.setattr("app.services.prefetch.rail_api_service.get_board", fake_get_board)

    try:
        coordinator.schedule_nr_board_prefetch("LHD")
        await asyncio.sleep(0.05)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == ["LHD"]
