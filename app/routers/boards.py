from typing import List
from fastapi import APIRouter, HTTPException, Query
from app.models.board import Board, Train, BoardResponse
from app.services.rail_api import rail_api_service
from app.middleware.cache import cache


router = APIRouter(prefix="/api/boards", tags=["boards"])


@router.get("/{crs_code}", response_model=BoardResponse)
async def get_board(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data")
):
    """
    Get full arrival and departure board for a station
    
    Args:
        crs_code: Three-letter CRS station code (e.g., 'LHD' for Leatherhead)
        use_cache: Whether to use cached data (default: True)
    
    Returns:
        Board data with all train services
    """
    board = await rail_api_service.get_board(crs_code, use_cache=use_cache)
    
    if not board:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
        )
    
    # Check if data was from cache
    cache_key = f"board:{crs_code.upper()}"
    cached = cache.get(cache_key) is not None
    
    return BoardResponse(
        success=True,
        data=board,
        cached=cached
    )


@router.get("/{crs_code}/departures", response_model=List[Train])
async def get_departures(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data")
):
    """
    Get only departure trains for a station
    
    Args:
        crs_code: Three-letter CRS station code (e.g., 'LHD')
        use_cache: Whether to use cached data (default: True)
    
    Returns:
        List of departing trains
    """
    board = await rail_api_service.get_board(crs_code, use_cache=use_cache)
    
    if not board:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch board data for station '{crs_code}'"
        )
    
    return board.departures


@router.get("/{crs_code}/arrivals", response_model=List[Train])
async def get_arrivals(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data")
):
    """
    Get only arrival trains for a station
    
    Args:
        crs_code: Three-letter CRS station code (e.g., 'LHD')
        use_cache: Whether to use cached data (default: True)
    
    Returns:
        List of arriving trains
    """
    board = await rail_api_service.get_board(crs_code, use_cache=use_cache)
    
    if not board:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch board data for station '{crs_code}'"
        )
    
    return board.arrivals


@router.get("/{crs_code}/passing", response_model=List[Train])
async def get_passing_through(
    crs_code: str,
    use_cache: bool = Query(True, description="Whether to use cached data")
):
    """
    Get trains passing through the station (both arriving and departing)
    
    Args:
        crs_code: Three-letter CRS station code (e.g., 'LHD')
        use_cache: Whether to use cached data (default: True)
    
    Returns:
        List of trains passing through
    """
    board = await rail_api_service.get_board(crs_code, use_cache=use_cache)
    
    if not board:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch board data for station '{crs_code}'"
        )
    
    return board.passing_through


@router.delete("/{crs_code}/cache")
async def clear_station_cache(crs_code: str):
    """
    Clear cached data for a specific station
    
    Args:
        crs_code: Three-letter CRS station code (e.g., 'LHD')
    
    Returns:
        Success message
    """
    rail_api_service.clear_cache(crs_code)
    return {"success": True, "message": f"Cache cleared for station {crs_code.upper()}"}


@router.delete("/cache/all")
async def clear_all_cache():
    """
    Clear all cached board data
    
    Returns:
        Success message with count of cleared entries
    """
    size = cache.size()
    cache.clear()
    return {
        "success": True,
        "message": f"Cleared {size} cached entries"
    }
