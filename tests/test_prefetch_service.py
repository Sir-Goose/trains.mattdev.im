import asyncio

import pytest

from app.config import settings
from app.models.board import Board
from app.models.tfl import TflBoard
from app.services.rail_api import BoardFetchResult
from app.services.tfl_api import TflBoardFetchResult
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
    service_calls: list[tuple[str, str]] = []

    async def fake_get_board(crs_code: str, use_cache: bool = True):
        calls.append(crs_code)
        await asyncio.sleep(0.01)
        board = Board(
            locationName="Leatherhead",
            crs=crs_code,
            generatedAt="2026-01-01T12:00:00+00:00",
            trainServices=[{"serviceID": "service-1"}],
        )
        return BoardFetchResult(board=board, from_cache=True)

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        service_calls.append((crs, service_id))

    monkeypatch.setattr("app.services.prefetch.rail_api_service.get_board", fake_get_board)
    monkeypatch.setattr(coordinator, "schedule_nr_service_prefetch", fake_schedule_nr_service_prefetch)

    try:
        coordinator.schedule_nr_board_prefetch("LHD")
        await asyncio.sleep(0.05)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == ["LHD"]
    assert service_calls == [("LHD", "service-1")]


@pytest.mark.asyncio
async def test_tfl_board_prefetch_warms_service_prefetch(monkeypatch):
    old_enabled = settings.prefetch_enabled
    settings.prefetch_enabled = True
    coordinator = PrefetchCoordinator()

    calls: list[str] = []
    service_calls: list[dict] = []

    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        calls.append(stop_point_id)
        await asyncio.sleep(0.01)
        board = TflBoard(
            stop_point_id=stop_point_id,
            station_name="Green Park Underground Station",
            generated_at="2026-01-01T12:00:00+00:00",
            pulled_at="2026-01-01T12:00:00+00:00",
            trains=[
                {
                    "lineId": "victoria",
                    "lineName": "Victoria",
                    "naptanId": stop_point_id,
                    "destinationNaptanId": "940GZZLUBXN",
                    "destinationName": "Brixton Underground Station",
                    "stationName": "Green Park Underground Station",
                    "expectedArrival": "2026-01-01T12:02:00Z",
                }
            ],
            line_status=[],
        )
        return TflBoardFetchResult(board=board, from_cache=True)

    def fake_schedule_tfl_service_prefetch(params: dict):
        service_calls.append(params)

    monkeypatch.setattr("app.services.prefetch.tfl_api_service.get_board", fake_get_board)
    monkeypatch.setattr(coordinator, "schedule_tfl_service_prefetch", fake_schedule_tfl_service_prefetch)

    try:
        coordinator.schedule_tfl_board_prefetch("940GZZLUGPK")
        await asyncio.sleep(0.05)
    finally:
        settings.prefetch_enabled = old_enabled

    assert calls == ["940GZZLUGPK"]
    assert len(service_calls) == 1
    assert service_calls[0]["line_id"] == "victoria"
