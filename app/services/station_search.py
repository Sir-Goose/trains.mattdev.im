"""
Station search service with fuzzy matching
"""
import logging
from rapidfuzz import fuzz
from functools import lru_cache
import json
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

STATIONS_FILE = Path(__file__).parent.parent / "static" / "data" / "stations.json"
TFL_STATIONS_FILE = Path(__file__).parent.parent / "static" / "data" / "tfl_stations.json"

@lru_cache(maxsize=1)
def load_stations() -> List[Dict]:
    """
    Load stations from JSON file (cached in memory)
    Only loads once, subsequent calls return cached data
    """
    with open(STATIONS_FILE) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_tfl_stations() -> List[Dict]:
    """
    Load local TfL stations index from JSON (cached in memory).
    Returns empty list if file is missing/invalid.
    """
    try:
        with open(TFL_STATIONS_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except FileNotFoundError:
        logger.warning("Local TfL stations file missing at %s", TFL_STATIONS_FILE)
        return []
    except json.JSONDecodeError:
        logger.warning("Local TfL stations file is invalid JSON at %s", TFL_STATIONS_FILE)
        return []


def _format_tfl_search_name(raw_name: str, modes: list[str]) -> str:
    cleaned = (raw_name or "").strip()
    if not cleaned:
        return cleaned

    lower = cleaned.lower()
    if lower.endswith("underground station") or lower.endswith("overground station") or lower.endswith("dlr station"):
        return cleaned

    mode_set = set(modes or [])
    if "tube" in mode_set and "overground" not in mode_set:
        base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
        return f"{base} Underground Station"
    if "overground" in mode_set and "tube" not in mode_set:
        base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
        return f"{base} Overground Station"
    if "dlr" in mode_set and "tube" not in mode_set and "overground" not in mode_set:
        base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
        return f"{base} DLR Station"
    return cleaned


def search_tfl_stations_local(query: str, limit: int = 10) -> List[Dict]:
    """
    Fuzzy search local TfL station index.
    Returns provider-ready search rows.
    """
    if not query or len(query.strip()) == 0:
        return []

    stations = load_tfl_stations()
    query_clean = query.strip()
    query_norm = _normalize_search_text(query_clean) or query_clean.lower()
    scored: List[tuple[Dict, int]] = []

    for station in stations:
        raw_name = (station.get("name") or "").strip()
        station_id = (station.get("id") or "").strip()
        if not raw_name or not station_id:
            continue

        modes = [mode for mode in (station.get("modes") or []) if mode in {"tube", "overground", "dlr"}]
        if not modes:
            continue

        name_norm = _normalize_search_text(raw_name) or raw_name.lower()
        score = fuzz.WRatio(query_norm, name_norm)

        if name_norm == query_norm:
            score += 120
        elif raw_name.lower() == query_clean.lower():
            score += 100

        if name_norm.startswith(query_norm):
            score += 60
        elif any(word.startswith(query_norm) for word in name_norm.split()):
            score += 30
        elif query_norm in name_norm:
            score += 15

        if "tube" in modes:
            score += 5

        scored.append((station, score))

    scored.sort(key=lambda item: (-item[1], (item[0].get("name") or "").lower(), item[0].get("id") or ""))

    results: List[Dict] = []
    for station, _ in scored[:limit]:
        modes = [mode for mode in (station.get("modes") or []) if mode in {"tube", "overground", "dlr"}]
        if "tube" in modes:
            mode_label = "Tube"
        elif "overground" in modes:
            mode_label = "Overground"
        elif "dlr" in modes:
            mode_label = "DLR"
        else:
            mode_label = "TfL"
        station_id = station.get("id")
        display_name = _format_tfl_search_name(station.get("name") or "", modes)
        results.append(
            {
                "provider": "tfl",
                "name": display_name,
                "code": station_id,
                "badge": f"TfL {mode_label}",
                "url": f"/board/tfl/{station_id}/departures",
            }
        )

    return results


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


def _normalize_search_text(value: str) -> str:
    normalized = value.strip().lower()
    suffixes = [
        " underground station",
        " overground station",
        " dlr station",
        " station",
    ]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    return normalized


def _score_unified_result(result: Dict, query: str) -> int:
    query_clean = query.strip()
    if not query_clean:
        return 0

    query_lower = query_clean.lower()
    query_norm = _normalize_search_text(query_clean) or query_lower
    name = (result.get("name") or "").strip()
    name_lower = name.lower()
    name_norm = _normalize_search_text(name) or name_lower

    score = fuzz.WRatio(query_norm, name_norm)

    if name_norm == query_norm:
        score += 120
    elif name_lower == query_lower:
        score += 100

    if name_norm.startswith(query_norm):
        score += 60
    elif any(word.startswith(query_norm) for word in name_norm.split()):
        score += 35
    elif query_norm in name_norm:
        score += 20

    code = (result.get("code") or "").upper()
    if result.get("provider") == "nr" and code and code == query_clean.upper():
        score += 200

    if result.get("provider") == "tfl" and (
        name_lower.endswith("underground station")
        or name_lower.endswith("overground station")
        or name_lower.endswith("dlr station")
    ):
        score += 10

    return score


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

    provider_limit = max(limit, 12)
    nr_results = search_stations(query, limit=provider_limit)
    mapped_nr = [
        {
            "provider": "nr",
            "name": station["stationName"],
            "code": station["crsCode"],
            "badge": f"NR {station['crsCode']}",
            "url": f"/board/nr/{station['crsCode']}/{nr_view}",
        }
        for station in nr_results
    ]

    mapped_tfl = search_tfl_stations_local(query, limit=provider_limit)
    for item in mapped_tfl:
        code = item.get("code")
        if code:
            item["url"] = f"/board/tfl/{code}/{tfl_view}"

    combined = mapped_nr + mapped_tfl
    combined.sort(
        key=lambda result: (
            -_score_unified_result(result, query),
            (result.get("name") or "").lower(),
            result.get("provider") or "",
        )
    )
    return combined[:limit]
