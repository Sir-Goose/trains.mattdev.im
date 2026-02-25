"""
Station search API endpoints
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.prefetch import prefetch_service
from app.services.station_search import search_stations_unified

router = APIRouter(prefix="/api/stations", tags=["stations"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query("", max_length=100, description="Search query"),
    view: str = Query("departures", pattern="^(departures|arrivals|passing)$")
):
    """
    Station search endpoint for HTMX autocomplete
    Returns HTML fragment with search results
    
    Query params:
        q: Search query (station name or CRS code)
        view: Current board view (departures/arrivals/passing) to preserve
        
    Returns:
        HTML fragment with autocomplete results or empty string
    """
    # Empty query = empty results (no dropdown)
    if not q or len(q.strip()) == 0:
        return HTMLResponse("")
    
    # Perform unified search across National Rail and TfL
    results = await search_stations_unified(q, view=view, limit=10)

    # Warm linked board caches so search-click navigation is faster.
    for result in results:
        provider = (result.get("provider") or "").strip().lower()
        code = (result.get("code") or "").strip()
        if provider == "nr":
            prefetch_service.schedule_nr_board_prefetch(code)
        elif provider == "tfl":
            prefetch_service.schedule_tfl_board_prefetch(code)
    
    # No results = show empty state message
    if not results:
        return templates.TemplateResponse(
            "partials/station_search_empty.html",
            {
                "request": request,
                "query": q
            }
        )
    
    # Return results as HTML fragment
    return templates.TemplateResponse(
        "partials/station_search_results.html",
        {
            "request": request,
            "results": results,
            "view": view
        }
    )
