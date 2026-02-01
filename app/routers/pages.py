from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
from app.services.rail_api import rail_api_service
from app.middleware.cache import cache

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_timestamp() -> str:
    """Get current timestamp in HH:MM:SS format"""
    return datetime.now().strftime("%H:%M:%S")

def validate_crs(crs: str) -> str:
    """Validate and normalize CRS code"""
    if not crs or len(crs) != 3 or not crs.isalpha():
        raise HTTPException(status_code=404, detail="Invalid CRS code")
    return crs.upper()

async def get_board_data(crs: str, view: str):
    """
    Fetch board data for a specific view
    Returns: (trains, station_name, error_flag)
    """
    try:
        board = await rail_api_service.get_board(crs, use_cache=True)
        
        if not board:
            # Try to get from cache one more time
            cache_key = f"board:{crs}"
            board = cache.get(cache_key)
            if not board:
                raise HTTPException(status_code=404, detail=f"Station {crs} not found")
        
        # Get appropriate train list based on view
        if view == 'departures':
            trains = board.departures
        elif view == 'arrivals':
            trains = board.arrivals
        elif view == 'passing':
            trains = board.passing_through
        else:
            trains = []
        
        return trains, board.location_name, False
        
    except HTTPException:
        raise
    except Exception as e:
        # API error - try to return cached data
        cache_key = f"board:{crs}"
        cached_board = cache.get(cache_key)
        
        if cached_board:
            if view == 'departures':
                trains = cached_board.departures
            elif view == 'arrivals':
                trains = cached_board.arrivals
            elif view == 'passing':
                trains = cached_board.passing_through
            else:
                trains = []
            return trains, cached_board.location_name, True  # error flag
        else:
            raise HTTPException(status_code=500, detail="Service temporarily unavailable")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Homepage with station list and search"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "timestamp": get_timestamp()
        }
    )


@router.get("/board", response_class=RedirectResponse)
async def board_search(crs: str):
    """Handle CRS search form submission"""
    crs = validate_crs(crs)
    return RedirectResponse(url=f"/board/{crs}/departures", status_code=303)


@router.get("/board/{crs}", response_class=RedirectResponse)
async def board_redirect(crs: str):
    """Redirect /board/{crs} to /board/{crs}/departures"""
    crs = validate_crs(crs)
    return RedirectResponse(url=f"/board/{crs}/departures", status_code=307)


@router.get("/board/{crs}/{view}", response_class=HTMLResponse)
async def board_view(request: Request, crs: str, view: str):
    """
    Main board page
    view: 'departures' | 'arrivals' | 'passing'
    """
    crs = validate_crs(crs)
    
    if view not in ['departures', 'arrivals', 'passing']:
        raise HTTPException(status_code=404, detail="Invalid view")
    
    trains, station_name, error = await get_board_data(crs, view)
    
    return templates.TemplateResponse(
        "board.html",
        {
            "request": request,
            "crs": crs,
            "station_name": station_name,
            "view": view,
            "trains": trains,
            "error": error,
            "timestamp": get_timestamp()
        }
    )


@router.get("/board/{crs}/{view}/content", response_class=HTMLResponse)
async def board_content(request: Request, crs: str, view: str):
    """
    HTMX endpoint for tab switching
    Returns just the table partial
    """
    crs = validate_crs(crs)
    
    if view not in ['departures', 'arrivals', 'passing']:
        raise HTTPException(status_code=404, detail="Invalid view")
    
    trains, station_name, error = await get_board_data(crs, view)
    
    return templates.TemplateResponse(
        f"partials/{view}_table.html",
        {
            "request": request,
            "trains": trains,
            "error": error,
            "timestamp": get_timestamp()
        }
    )


@router.get("/board/{crs}/{view}/refresh", response_class=HTMLResponse)
async def board_refresh(request: Request, crs: str, view: str):
    """
    HTMX auto-refresh endpoint
    Returns just the table partial
    If error, returns 204 No Content to keep stale data
    """
    crs = validate_crs(crs)
    
    if view not in ['departures', 'arrivals', 'passing']:
        return HTMLResponse(status_code=204)
    
    try:
        trains, station_name, error = await get_board_data(crs, view)
        
        return templates.TemplateResponse(
            f"partials/{view}_table.html",
            {
                "request": request,
                "trains": trains,
                "error": error,
                "timestamp": get_timestamp()
            }
        )
    except Exception:
        # Return 204 No Content to keep existing content on error
        return HTMLResponse(status_code=204)
