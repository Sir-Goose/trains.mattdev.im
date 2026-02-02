"""
Station search service with fuzzy matching
"""
from rapidfuzz import fuzz, process
from functools import lru_cache
import json
from pathlib import Path
from typing import List, Dict

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
    Fuzzy search stations by name or CRS code
    
    Args:
        query: Search query (station name or CRS code)
        limit: Maximum number of results to return
        
    Returns:
        List of station dicts sorted by relevance
        
    Examples:
        search_stations("leath") -> [{"stationName": "Leatherhead", "crsCode": "LHD", ...}]
        search_stations("LHD") -> [{"stationName": "Leatherhead", "crsCode": "LHD", ...}]
        search_stations("london") -> [{"stationName": "London Waterloo", ...}, ...]
    """
    if not query or len(query.strip()) == 0:
        return []
    
    stations = load_stations()
    query = query.strip()
    
    # If query looks like CRS code (3 letters), prioritize exact CRS matches
    if len(query) == 3 and query.isalpha():
        crs_query = query.upper()
        exact_crs = [s for s in stations if s['crsCode'] == crs_query]
        if exact_crs:
            return exact_crs  # Return immediately if exact CRS match
    
    # Fuzzy search on station names using RapidFuzz
    # partial_ratio allows substring matching ("leath" matches "Leatherhead")
    station_names = [s['stationName'] for s in stations]
    
    matches = process.extract(
        query,
        station_names,
        scorer=fuzz.partial_ratio,  # Substring-based fuzzy matching
        limit=limit * 2  # Get more candidates, filter below
    )
    
    # Filter by minimum score and map back to full station objects
    results = []
    for name, score, idx in matches:
        if score >= 60:  # Minimum similarity threshold (0-100 scale)
            results.append(stations[idx])
        
        if len(results) >= limit:
            break
    
    return results[:limit]


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
