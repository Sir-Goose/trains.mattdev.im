"""
Station search API endpoints
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.station_search import search_stations

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
    
    # Perform fuzzy search
    results = search_stations(q, limit=10)
    
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
