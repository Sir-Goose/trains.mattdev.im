import asyncio

import pytest

from app.config import settings
from app.middleware.cache import cache
from app.models.board import ServiceDetails
from app.services.rail_api import rail_api_service
from app.services.tfl_api import tfl_api_service
from app.services.prefetch import PrefetchCoordinator


def _sample_service_detail(service_id: str = "service-1", crs: str = "LHD") -> ServiceDetails:
    return ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs=crs,
        operator="South Western Railway",
        operatorCode="SW",
        serviceID=service_id,
        origin=[{"locationName": "Dorking", "crs": "DKG"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
    )


@pytest.mark.asyncio
async def test_prefetch_dedup_skips_duplicate_job(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    calls: list[tuple[str, str]] = []

    async def fake_get_service_route_cached(crs_code: str, service_id: str, use_cache: bool = True):
        calls.append((crs_code, service_id))
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_cached",
        fake_get_service_route_cached,
    )
    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_from_timetable",
        lambda *args, **kwargs: asyncio.sleep(0, result=None),
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

    async def fake_get_service_route_cached(crs_code: str, service_id: str, use_cache: bool = True):
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_cached",
        fake_get_service_route_cached,
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
async def test_nr_service_prefetch_board_hit_skips_timetable_fallback(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    service_id = "service-board-hit"
    cache.delete(rail_api_service._service_detail_cache_key(service_id))

    board_calls = 0
    timetable_calls = 0

    async def fake_get_service_route_cached(crs_code: str, service_id: str, use_cache: bool = True):
        nonlocal board_calls
        board_calls += 1
        return _sample_service_detail(service_id=service_id, crs=crs_code)

    async def fake_get_service_route_from_timetable(crs_code: str, service_id: str):
        nonlocal timetable_calls
        timetable_calls += 1
        return None

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_cached",
        fake_get_service_route_cached,
    )
    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_from_timetable",
        fake_get_service_route_from_timetable,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", service_id)
        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert board_calls == 1
    assert timetable_calls == 0


@pytest.mark.asyncio
async def test_nr_service_prefetch_cache_hit_refreshes_service_ttl(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    service_id = "service-cache-hit-touch"
    cache_key = rail_api_service._service_detail_cache_key(service_id)
    detail = _sample_service_detail(service_id=service_id, crs="LHD")
    cache.set(cache_key, detail.model_dump(mode="json", by_alias=True), settings.service_prefetch_ttl_seconds)

    set_calls: list[tuple[str, int | None]] = []
    original_set = cache.set
    timetable_calls = 0

    def tracking_set(key, value, ttl=None):
        set_calls.append((key, ttl))
        return original_set(key, value, ttl)

    async def fake_get_service_route_from_timetable(crs_code: str, service_id: str):
        nonlocal timetable_calls
        timetable_calls += 1
        return None

    monkeypatch.setattr(cache, "set", tracking_set)
    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_from_timetable",
        fake_get_service_route_from_timetable,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", service_id)
        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert timetable_calls == 0
    assert (cache_key, settings.service_prefetch_ttl_seconds) in set_calls


@pytest.mark.asyncio
async def test_nr_service_prefetch_board_miss_timetable_hit_warms_service_cache(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    service_id = "service-timetable-hit"
    cache_key = rail_api_service._service_detail_cache_key(service_id)
    cache.delete(cache_key)

    board_calls = 0
    timetable_calls = 0

    async def fake_get_service_route_cached(crs_code: str, service_id: str, use_cache: bool = True):
        nonlocal board_calls
        board_calls += 1
        return None

    async def fake_get_service_route_from_timetable(crs_code: str, service_id: str):
        nonlocal timetable_calls
        timetable_calls += 1
        return _sample_service_detail(service_id=service_id, crs=crs_code)

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_cached",
        fake_get_service_route_cached,
    )
    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_from_timetable",
        fake_get_service_route_from_timetable,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", service_id)
        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert board_calls == 1
    assert timetable_calls == 1
    cached = cache.get(cache_key)
    assert isinstance(cached, dict)
    assert cached.get("serviceID") == service_id


@pytest.mark.asyncio
async def test_nr_service_prefetch_board_miss_timetable_miss_does_not_cache(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    service_id = "service-timetable-miss"
    cache_key = rail_api_service._service_detail_cache_key(service_id)
    cache.delete(cache_key)

    board_calls = 0
    timetable_calls = 0

    async def fake_get_service_route_cached(crs_code: str, service_id: str, use_cache: bool = True):
        nonlocal board_calls
        board_calls += 1
        return None

    async def fake_get_service_route_from_timetable(crs_code: str, service_id: str):
        nonlocal timetable_calls
        timetable_calls += 1
        return None

    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_cached",
        fake_get_service_route_cached,
    )
    monkeypatch.setattr(
        "app.services.prefetch.rail_api_service.get_service_route_from_timetable",
        fake_get_service_route_from_timetable,
    )

    try:
        coordinator.schedule_nr_service_prefetch("LHD", service_id)
        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert board_calls == 1
    assert timetable_calls == 1
    assert cache.get(cache_key) is None


@pytest.mark.asyncio
async def test_tfl_service_prefetch_cache_hit_refreshes_service_ttl(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()
    params = {
        "line_id": "victoria",
        "from_stop_id": "940GZZLUGPK",
        "to_stop_id": "940GZZLUBXN",
        "direction": "inbound",
        "trip_id": "trip-1",
    }
    cache_key = tfl_api_service._service_detail_cache_key(**params)
    cache.set(
        cache_key,
        {
            "line_id": "victoria",
            "line_name": "Victoria",
            "direction": "inbound",
            "from_stop_id": "940GZZLUGPK",
            "to_stop_id": "940GZZLUBXN",
            "origin_name": "Green Park Underground Station",
            "destination_name": "Brixton Underground Station",
            "resolution_mode": "exact",
            "mode_name": "tube",
            "pulledAt": "2026-01-01T12:00:00+00:00",
            "stops": [],
        },
        settings.service_prefetch_ttl_seconds,
    )

    set_calls: list[tuple[str, int | None]] = []
    original_set = cache.set
    detail_fetch_calls = 0

    def tracking_set(key, value, ttl=None):
        set_calls.append((key, ttl))
        return original_set(key, value, ttl)

    async def fake_get_service_route_detail(**kwargs):
        nonlocal detail_fetch_calls
        detail_fetch_calls += 1
        raise AssertionError("get_service_route_detail should not be called on a warm cache hit")

    monkeypatch.setattr(cache, "set", tracking_set)
    monkeypatch.setattr(
        "app.services.prefetch.tfl_api_service.get_service_route_detail",
        fake_get_service_route_detail,
    )

    try:
        coordinator.schedule_tfl_service_prefetch(params)
        await asyncio.sleep(0.1)
    finally:
        settings.prefetch_enabled = old_enabled

    assert detail_fetch_calls == 0
    assert (cache_key, settings.service_prefetch_ttl_seconds) in set_calls


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


@pytest.mark.asyncio
async def test_tfl_board_prefetch_warms_board_cache(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()

    calls: list[str] = []

    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        calls.append(stop_point_id)
        await asyncio.sleep(0.01)
        return None

    monkeypatch.setattr("app.services.prefetch.tfl_api_service.get_board", fake_get_board)

    try:
        coordinator.schedule_tfl_board_prefetch("940GZZLUGPK")
        await asyncio.sleep(0.05)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == ["940GZZLUGPK"]
