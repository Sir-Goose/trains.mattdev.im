from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
from app.services.rail_api import BoardNotFoundError, RailAPIError, rail_api_service
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

def get_trains_for_view(board, view: str):
    """Extract trains for specific view from board object"""
    if view == 'departures':
        return board.departures
    elif view == 'arrivals':
        return board.arrivals
    elif view == 'passing':
        return board.passing_through
    return []

async def get_board_data(crs: str, view: str):
    """
    Fetch board data for a specific view with total train count
    Returns: (trains_for_view, total_trains, station_name, error_flag)
    """
    cache_key = f"board:{crs}"

    try:
        result = await rail_api_service.get_board(crs, use_cache=True)
        board = result.board
        trains_for_view = get_trains_for_view(board, view)
        total_trains = len(board.trains)
        return trains_for_view, total_trains, board.location_name, False
    except BoardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RailAPIError:
        # Upstream failed - try to keep UI alive with cached data
        cached_board = cache.get(cache_key)
        if cached_board:
            trains_for_view = get_trains_for_view(cached_board, view)
            total_trains = len(cached_board.trains)
            return trains_for_view, total_trains, cached_board.location_name, True
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
async def board_search(crs: str, view: Optional[str] = "departures"):
    """Handle CRS search form submission"""
    crs = validate_crs(crs)
    
    # Validate view parameter
    if view not in ['departures', 'arrivals', 'passing']:
        view = 'departures'
    
    return RedirectResponse(url=f"/board/{crs}/{view}", status_code=303)


# Service detail pages disabled - Darwin REST API doesn't support individual service queries
# Would require switching to SOAP API or using a different approach

# @router.get("/service/{service_id}", response_class=HTMLResponse)
# async def service_detail_page(request: Request, service_id: str):
#     """Display detailed information about a specific train service"""
#     service = await rail_api_service.get_service_details(service_id)
#     
#     if not service:
#         # Service has expired from cache - show user-friendly message
#         return templates.TemplateResponse(
#             "errors/service_expired.html",
#             {
#                 "request": request,
#                 "service_id": service_id,
#                 "timestamp": get_timestamp()
#             },
#             status_code=404
#         )
#     
#     return templates.TemplateResponse(
#         "service_detail.html",
#         {
#             "request": request,
#             "service": service,
#             "timestamp": get_timestamp()
#         }
#     )


# @router.get("/service/{service_id}/refresh", response_class=HTMLResponse)
# async def service_detail_refresh(request: Request, service_id: str):
#     """HTMX endpoint to refresh just the service timeline content"""
#     service = await rail_api_service.get_service_details(service_id, use_cache=False)
#     
#     if not service:
#         return HTMLResponse(
#             content="<div class='error-message'>Service no longer available</div>",
#             status_code=200
#         )
#     
#     return templates.TemplateResponse(
#         "partials/service_timeline.html",
#         {
#             "request": request,
#             "service": service,
#             "timestamp": get_timestamp()
#         }
#     )


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
    
    trains, total_trains, station_name, error = await get_board_data(crs, view)
    
    return templates.TemplateResponse(
        "board.html",
        {
            "request": request,
            "crs": crs,
            "station_name": station_name,
            "view": view,
            "trains": trains,
            "total_trains": total_trains,
            "error": error,
            "timestamp": get_timestamp()
        }
    )


@router.get("/board/{crs}/{view}/content", response_class=HTMLResponse)
async def board_content(request: Request, crs: str, view: str):
    """
    HTMX endpoint for tab switching
    Returns tabs (with updated active state) + board content wrapper + search form via OOB swap
    """
    crs = validate_crs(crs)
    
    if view not in ['departures', 'arrivals', 'passing']:
        raise HTTPException(status_code=404, detail="Invalid view")
    
    trains, total_trains, station_name, error = await get_board_data(crs, view)
    
    # Render tabs with updated active state
    tabs_html = templates.get_template("partials/tabs.html").render(
        crs=crs,
        view=view
    )
    
    # Render board content wrapper (with correct hx-get URL for this view)
    board_content_html = templates.get_template("partials/board_content.html").render(
        request=request,
        crs=crs,
        view=view,
        trains=trains,
        error=error,
        timestamp=get_timestamp()
    )
    
    # Render search form with updated view parameter
    search_form_html = templates.get_template("partials/search_form.html").render(
        view=view
    )
    
    # Return tabs + board-content + search-form (all with hx-swap-oob="true")
    # HTMX will swap #tabs, #board-content, and #search-form divs
    return HTMLResponse(content=tabs_html + board_content_html + search_form_html)


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
        trains, total_trains, station_name, error = await get_board_data(crs, view)
        
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
