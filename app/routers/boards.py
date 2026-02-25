from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.middleware.cache import cache
from app.models.board import BoardResponse, Train
from app.models.tfl import TflBoardResponse, TflLineStatusSummary, TflPrediction
from app.services.rail_api import (
    BoardFetchResult,
    BoardNotFoundError,
    RailAPIError,
    rail_api_service,
)
from app.services.tfl_api import (
    TflAPIError,
    TflBoardFetchResult,
    TflBoardNotFoundError,
    tfl_api_service,
)

router = APIRouter(prefix="/api/boards", tags=["boards"])


async def fetch_nr_board_or_raise(crs_code: str, use_cache: bool) -> BoardFetchResult:
    try:
        return await rail_api_service.get_board(crs_code, use_cache=use_cache)
    except BoardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RailAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


async def fetch_tfl_board_or_raise(stop_point_id: str, use_cache: bool) -> TflBoardFetchResult:
    try:
        return await tfl_api_service.get_board(stop_point_id, use_cache=use_cache)
    except TflBoardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TflAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/nr/{crs_code}", response_model=BoardResponse)
async def get_nr_board_prefixed(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_nr_board_or_raise(crs_code, use_cache)
    return BoardResponse(success=True, data=result.board, cached=result.from_cache)


@router.get("/{crs_code}", response_model=BoardResponse)
async def get_board(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_nr_board_or_raise(crs_code, use_cache)
    return BoardResponse(success=True, data=result.board, cached=result.from_cache)


@router.get("/{crs_code}/departures", response_model=List[Train])
async def get_departures(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_nr_board_or_raise(crs_code, use_cache)
    return result.board.departures


@router.get("/{crs_code}/arrivals", response_model=List[Train])
async def get_arrivals(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_nr_board_or_raise(crs_code, use_cache)
    return result.board.arrivals


@router.get("/{crs_code}/passing", response_model=List[Train])
async def get_passing_through(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_nr_board_or_raise(crs_code, use_cache)
    return result.board.passing_through


@router.get("/tfl/{stop_point_id}", response_model=TflBoardResponse)
async def get_tfl_board(
    stop_point_id: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_tfl_board_or_raise(stop_point_id, use_cache)
    return TflBoardResponse(success=True, data=result.board, cached=result.from_cache)


@router.get("/tfl/{stop_point_id}/departures", response_model=List[TflPrediction])
async def get_tfl_departures(
    stop_point_id: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_tfl_board_or_raise(stop_point_id, use_cache)
    return tfl_api_service.predictions_for_view(result.board.trains, "departures")


@router.get("/tfl/{stop_point_id}/arrivals", response_model=List[TflPrediction])
async def get_tfl_arrivals(
    stop_point_id: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_tfl_board_or_raise(stop_point_id, use_cache)
    return tfl_api_service.predictions_for_view(result.board.trains, "arrivals")


@router.get("/tfl/{stop_point_id}/status", response_model=List[TflLineStatusSummary])
async def get_tfl_status(
    stop_point_id: str,
    use_cache: bool = Query(True, description="Whether to use cached data"),
):
    result = await fetch_tfl_board_or_raise(stop_point_id, use_cache)
    return result.board.line_status


@router.get("/tfl/{stop_point_id}/passing")
async def get_tfl_passing(stop_point_id: str):
    raise HTTPException(status_code=404, detail="Passing view is not available for TfL boards.")


@router.delete("/{crs_code}/cache")
async def clear_station_cache(crs_code: str):
    rail_api_service.clear_cache(crs_code)
    return {"success": True, "message": f"Cache cleared for station {crs_code.upper()}"}


@router.delete("/cache/all")
async def clear_all_cache():
    size = cache.size()
    cache.clear()
    return {"success": True, "message": f"Cleared {size} cached entries"}
