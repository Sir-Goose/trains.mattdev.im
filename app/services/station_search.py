"""
Station search service with fuzzy matching
"""
import logging
from rapidfuzz import fuzz, process
from functools import lru_cache
import json
from pathlib import Path
from typing import List, Dict

from app.services.tfl_api import TflAPIError, tfl_api_service

logger = logging.getLogger(__name__)

STATIONS_FILE = Path(__file__).parent.parent / "static" / "data" / "stations.json"

@lru_cache(maxsize=1)
def load_stations() -> List[Dict]:
    """
    Load stations from JSON file (cached in memory)
    Only loads once, subsequent calls return cached data
    """
    with open(STATIONS_FILE) as f:
        return json.load(f)


def search_stations(query: str, limit: int = 10) -> List[Dict]:
    """
    Fuzzy search stations by name or CRS code with position-aware ranking
    
    Args:
        query: Search query (station name or CRS code)
        limit: Maximum number of results to return
        
    Returns:
        List of station dicts sorted by relevance
        
    Examples:
        search_stations("leath") -> [{"stationName": "Leatherhead", "crsCode": "LHD", ...}]
        search_stations("LHD") -> [{"stationName": "Leatherhead", "crsCode": "LHD", ...}]
        search_stations("london") -> [{"stationName": "London Waterloo", ...}, ...]
        search_stations("lea") -> [{"stationName": "Leagrave", ...}, {"stationName": "Lea Bridge", ...}, ...]
        
    Ranking algorithm:
        - Uses WRatio for position-aware fuzzy matching
        - +100 bonus for exact CRS code match (ensures CRS matches rank first)
        - +40 bonus if station name starts with query (case-insensitive)
        - +20 bonus if any word in station name starts with query
        - Sorts by composite score (desc), then alphabetically
    """
    if not query or len(query.strip()) == 0:
        return []
    
    stations = load_stations()
    query = query.strip()
    query_lower = query.lower()
    query_upper = query.upper()
    
    # Calculate scores for all stations with position and CRS bonuses
    scored_stations = []
    
    for station in stations:
        station_name = station['stationName']
        station_lower = station_name.lower()
        
        # Base fuzzy score using WRatio (position-aware)
        base_score = fuzz.WRatio(query, station_name)
        
        # Position bonuses
        position_bonus = 0
        
        # +40 if station name starts with query
        if station_lower.startswith(query_lower):
            position_bonus = 40
        # +20 if any word in station name starts with query
        elif any(word.startswith(query_lower) for word in station_lower.split()):
            position_bonus = 20
        
        # CRS code exact match gets massive bonus
        crs_bonus = 0
        if station['crsCode'] == query_upper:
            crs_bonus = 100
        
        # Composite score (capped at 200 to accommodate CRS bonus)
        composite_score = min(base_score + position_bonus + crs_bonus, 200)
        
        # Only include stations above minimum threshold
        if composite_score >= 50:  # Lowered threshold to catch more fuzzy matches
            scored_stations.append((station, composite_score, station_name))
    
    # Sort by composite score (desc), then alphabetically by station name
    scored_stations.sort(key=lambda x: (-x[1], x[2]))
    
    # Return top results
    return [station for station, score, name in scored_stations[:limit]]


def get_station_by_crs(crs_code: str) -> Dict | None:
    """
    Get station details by exact CRS code
    
    Args:
        crs_code: 3-letter CRS code (case-insensitive)
        
    Returns:
        Station dict or None if not found
    """
    stations = load_stations()
    crs_upper = crs_code.upper()
    return next((s for s in stations if s['crsCode'] == crs_upper), None)


async def search_stations_unified(query: str, view: str, limit: int = 10) -> List[Dict]:
    """
    Unified station search across National Rail and TfL.

    Returns result items with fields:
    - name
    - badge
    - url
    - provider
    """
    if not query or len(query.strip()) == 0:
        return []

    nr_view = view if view in {"departures", "arrivals", "passing"} else "departures"
    tfl_view = view if view in {"departures", "arrivals"} else "departures"

    nr_limit = max(1, limit // 2)
    tfl_limit = max(1, limit - nr_limit)

    nr_results = search_stations(query, limit=limit)
    mapped_nr = [
        {
            "provider": "nr",
            "name": station["stationName"],
            "badge": f"NR {station['crsCode']}",
            "url": f"/board/nr/{station['crsCode']}/{nr_view}",
        }
        for station in nr_results
    ]

    mapped_tfl: List[Dict] = []
    try:
        mapped_tfl = await tfl_api_service.search_stop_points(query, max_results=max(limit, 12))
        for item in mapped_tfl:
            code = item.get("code")
            if code:
                item["url"] = f"/board/tfl/{code}/{tfl_view}"
    except TflAPIError as exc:
        logger.warning("TfL search unavailable, returning NR-only results: %s", exc)
        mapped_tfl = []

    nr_slice = mapped_nr[:nr_limit]
    tfl_slice = mapped_tfl[:tfl_limit]

    combined: List[Dict] = []
    while (nr_slice or tfl_slice) and len(combined) < limit:
        if nr_slice:
            combined.append(nr_slice.pop(0))
            if len(combined) >= limit:
                break
        if tfl_slice:
            combined.append(tfl_slice.pop(0))

    if len(combined) < limit:
        combined.extend(mapped_nr[nr_limit : limit])
    if len(combined) < limit:
        combined.extend(mapped_tfl[tfl_limit : limit])

    return combined[:limit]
