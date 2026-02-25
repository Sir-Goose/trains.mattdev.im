from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services.display_mapper import map_tfl_predictions
from app.services.rail_api import rail_api_service
from app.services.tfl_api import TflAPIError, TflBoardNotFoundError, tfl_api_service

logger = logging.getLogger(__name__)


class PrefetchCoordinator:
    """Background prefetch scheduler with bounded concurrency and in-process dedupe."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.prefetch_max_concurrency)
        self._active_job_keys: set[str] = set()
        self._active_lock = asyncio.Lock()

    @staticmethod
    def _emit(message: str) -> None:
        # Explicit console output requested for operational visibility.
        print(f"[prefetch] {message}", flush=True)
        logger.info(message)

    async def _claim_job(self, job_key: str) -> bool:
        async with self._active_lock:
            if job_key in self._active_job_keys:
                self._emit(f"skip duplicate {job_key}")
                return False
            self._active_job_keys.add(job_key)
            return True

    async def _release_job(self, job_key: str) -> None:
        async with self._active_lock:
            self._active_job_keys.discard(job_key)

    def schedule_nr_service_prefetch(self, crs: str, service_id: str) -> None:
        if not settings.prefetch_enabled or not service_id:
            return

        job_key = f"nr:{crs.upper()}:{service_id}"
        self._emit(f"queued {job_key}")

        async def _runner() -> None:
            await rail_api_service.get_service_route_following_cached(
                crs_code=crs,
                service_id=service_id,
                use_cache=True,
            )

        asyncio.create_task(self._run_job(job_key, _runner))

    def schedule_nr_board_prefetch(self, crs: str) -> None:
        if not settings.prefetch_enabled:
            return

        normalized_crs = (crs or "").strip().upper()
        if len(normalized_crs) != 3 or not normalized_crs.isalpha():
            return

        job_key = f"nr-board:{normalized_crs}"
        self._emit(f"queued {job_key}")

        async def _runner() -> None:
            result = await rail_api_service.get_board(crs_code=normalized_crs, use_cache=True)
            board = result.board
            board_crs = (board.crs or normalized_crs).strip().upper()
            for train in board.trains:
                service_id = (getattr(train, "service_id", None) or "").strip()
                if service_id:
                    self.schedule_nr_service_prefetch(board_crs, service_id)

        asyncio.create_task(self._run_job(job_key, _runner))

    def schedule_tfl_board_prefetch(self, stop_point_id: str) -> None:
        if not settings.prefetch_enabled:
            return

        normalized_stop_id = (stop_point_id or "").strip()
        if not normalized_stop_id:
            return

        job_key = f"tfl-board:{normalized_stop_id.lower()}"
        self._emit(f"queued {job_key}")

        async def _runner() -> None:
            result = await tfl_api_service.get_board(stop_point_id=normalized_stop_id, use_cache=True)
            mapped_rows = map_tfl_predictions(result.board.trains)
            for train in mapped_rows:
                line_id = train.get("line_id")
                from_stop_id = train.get("from_stop_id")
                to_stop_id = train.get("to_stop_id")
                if not line_id or not from_stop_id or not to_stop_id:
                    continue
                expected_arrival = train.get("expected_arrival")
                if expected_arrival is not None and hasattr(expected_arrival, "isoformat"):
                    expected_arrival = expected_arrival.isoformat()
                self.schedule_tfl_service_prefetch(
                    {
                        "line_id": line_id,
                        "from_stop_id": from_stop_id,
                        "to_stop_id": to_stop_id,
                        "direction": train.get("direction"),
                        "trip_id": train.get("trip_id"),
                        "vehicle_id": train.get("vehicle_id"),
                        "expected_arrival": expected_arrival,
                        "station_name": train.get("station_name"),
                        "destination_name": train.get("destination_name"),
                    }
                )

        asyncio.create_task(self._run_job(job_key, _runner))

    def schedule_tfl_service_prefetch(self, params: dict[str, Any]) -> None:
        if not settings.prefetch_enabled:
            return

        line_id = (params.get("line_id") or "").strip().lower()
        from_stop_id = (params.get("from_stop_id") or "").strip()
        to_stop_id = (params.get("to_stop_id") or "").strip()
        if not line_id or not from_stop_id or not to_stop_id:
            return

        trip_id = (params.get("trip_id") or "").strip()
        vehicle_id = (params.get("vehicle_id") or "").strip()
        direction = (params.get("direction") or "").strip().lower()
        expected_arrival = (params.get("expected_arrival") or "").strip()

        job_key = (
            f"tfl:{line_id}:{from_stop_id.lower()}:{to_stop_id.lower()}:"
            f"{direction}:{trip_id}:{vehicle_id}:{expected_arrival}"
        )
        self._emit(f"queued {job_key}")

        async def _runner() -> None:
            await tfl_api_service.get_service_route_detail_cached(
                line_id=line_id,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
                direction=params.get("direction"),
                trip_id=params.get("trip_id"),
                vehicle_id=params.get("vehicle_id"),
                expected_arrival=params.get("expected_arrival"),
                station_name=params.get("station_name"),
                destination_name=params.get("destination_name"),
                use_cache=True,
            )

        asyncio.create_task(self._run_job(job_key, _runner))

    async def _run_job(self, job_key: str, coroutine_factory) -> None:
        claimed = await self._claim_job(job_key)
        if not claimed:
            return

        try:
            async with self._semaphore:
                self._emit(f"start {job_key}")
                try:
                    await asyncio.wait_for(
                        coroutine_factory(),
                        timeout=settings.prefetch_request_timeout_seconds,
                    )
                    self._emit(f"done {job_key}")
                except (TflBoardNotFoundError, TflAPIError):
                    self._emit(f"error(tfl) {job_key}")
                    logger.debug("Prefetch failed for job %s due to TfL upstream miss/error", job_key)
                except TimeoutError:
                    self._emit(f"timeout {job_key}")
                    logger.debug("Prefetch job timed out: %s", job_key)
                except Exception:
                    self._emit(f"error {job_key}")
                    logger.exception("Unhandled prefetch error for job %s", job_key)
        finally:
            await self._release_job(job_key)


prefetch_service = PrefetchCoordinator()
