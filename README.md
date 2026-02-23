# Leatherhead Live - Train Board API

A high-performance FastAPI backend for UK National Rail live departure and arrival boards.

## Features

- **Fast & Async**: Built with FastAPI and async/await for maximum performance
- **Intelligent Caching**: 60-second in-memory cache to reduce API load
- **Multi-Station Support**: Works with any UK station CRS code
- **Type-Safe**: Full Pydantic validation for requests and responses
- **Auto Documentation**: Interactive API docs at `/docs`
- **CORS Enabled**: Ready for frontend integration
- **Clean Architecture**: Modular structure with separation of concerns

## Project Structure

```
LeatherheadLive/
├── app/
│   ├── main.py              # FastAPI application & middleware
│   ├── config.py            # Configuration management
│   ├── models/
│   │   └── board.py         # Pydantic data models
│   ├── services/
│   │   └── rail_api.py      # National Rail API client
│   ├── routers/
│   │   └── boards.py        # API endpoints
│   └── middleware/
│       └── cache.py         # Caching implementation
├── board.py                 # Original script (kept for reference)
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

### Prerequisites

- Python 3.10+
- Virtual environment (recommended)
- National Rail API key (get from https://www.nationalrail.co.uk/100296.aspx)

### Setup

1. **Activate virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or for latest versions:
   ```bash
   pip install fastapi "uvicorn[standard]" httpx python-dotenv pydantic-settings
   ```

3. **Configure API key**:
   
   Your API key is already in the `key` file. Alternatively, you can use a `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env and add your API key
   ```

## Running the Server

### Development Mode

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or run directly:
```bash
python -m app.main
```

### Production Mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The server will start at: **http://localhost:8000**

## API Endpoints

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Available Endpoints

#### 1. Get Full Board
```http
GET /api/boards/{crs_code}
```

Returns complete arrival and departure board for a station.

**Example**:
```bash
curl http://localhost:8000/api/boards/LHD
```

**Response**:
```json
{
  "success": true,
  "cached": false,
  "data": {
    "location_name": "Leatherhead",
    "crs": "LHD",
    "generated_at": "2026-01-31T18:30:00",
    "trains": [
      {
        "scheduled_departure_time": "18:35",
        "estimated_departure_time": "On time",
        "destination_name": "London Waterloo",
        "platform": "2",
        "operator": "South Western Railway",
        "display_status": "On time"
      }
    ]
  }
}
```

#### 2. Get Departures Only
```http
GET /api/boards/{crs_code}/departures
```

Returns only trains departing from the station.

**Example**:
```bash
curl http://localhost:8000/api/boards/LHD/departures
```

#### 3. Get Arrivals Only
```http
GET /api/boards/{crs_code}/arrivals
```

Returns only trains arriving at the station.

**Example**:
```bash
curl http://localhost:8000/api/boards/WAT/arrivals
```

#### 4. Get Passing Through
```http
GET /api/boards/{crs_code}/passing
```

Returns trains that are both arriving and departing (passing through).

**Example**:
```bash
curl http://localhost:8000/api/boards/LHD/passing
```

#### 5. Clear Station Cache
```http
DELETE /api/boards/{crs_code}/cache
```

Clear cached data for a specific station.

**Example**:
```bash
curl -X DELETE http://localhost:8000/api/boards/LHD/cache
```

#### 6. Clear All Cache
```http
DELETE /api/boards/cache/all
```

Clear all cached board data.

**Example**:
```bash
curl -X DELETE http://localhost:8000/api/boards/cache/all
```

#### 7. Health Check
```http
GET /api/health
```

Check API health status.

**Example**:
```bash
curl http://localhost:8000/api/health
```

### Query Parameters

All board endpoints support the following query parameter:

- `use_cache` (boolean, default: true) - Whether to use cached data

**Example**:
```bash
curl "http://localhost:8000/api/boards/LHD?use_cache=false"
```

## Common UK Station CRS Codes

| Station | CRS Code |
|---------|----------|
| Leatherhead | LHD |
| London Waterloo | WAT |
| London Victoria | VIC |
| London Paddington | PAD |
| London King's Cross | KGX |
| London Liverpool Street | LST |
| Brighton | BTN |
| Manchester Piccadilly | MAN |
| Birmingham New Street | BHM |
| Edinburgh Waverley | EDB |

Full list: https://www.nationalrail.co.uk/stations_destinations/48541.aspx

## Configuration

Configuration can be set via environment variables or the `.env` file:

```env
# National Rail API Configuration
RAIL_API_KEY=your_api_key_here

# Cache Configuration (default: 60 seconds)
CACHE_TTL_SECONDS=60

# CORS Configuration
CORS_ORIGINS=["*"]

# Server Configuration
APP_NAME="Leatherhead Live Train Board API"
DEBUG=false
```

## Caching Strategy

The API implements intelligent caching to reduce load on the National Rail API:

- **TTL**: 60 seconds (configurable)
- **Per-Station**: Each station's data is cached independently
- **Automatic Cleanup**: Expired entries are automatically removed
- **Manual Control**: Clear cache via API endpoints when needed

## Error Handling

The API returns appropriate HTTP status codes:

- `200 OK`: Successful request
- `404 Not Found`: Invalid CRS code or no data available
- `500 Internal Server Error`: API or server error

**Example Error Response**:
```json
{
  "success": false,
  "error": "Could not fetch board data for station 'XXX'",
  "detail": "Please check the CRS code is valid."
}
```

## Development

### Running Tests
```bash
pytest
```

### Code Structure

- **Models** (`app/models/board.py`): Pydantic models for data validation
- **Services** (`app/services/rail_api.py`): Business logic & external API calls
- **Routers** (`app/routers/boards.py`): API endpoint definitions
- **Middleware** (`app/middleware/cache.py`): Caching implementation
- **Config** (`app/config.py`): Settings management

## Performance

- **Async/Await**: Non-blocking I/O for high concurrency
- **In-Memory Cache**: Sub-millisecond cache hits
- **HTTP/2 Support**: Via httpx client
- **Connection Pooling**: Reusable HTTP connections

## License

MIT

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation
- [HTTPX](https://www.python-httpx.org/) - Async HTTP client
- [Uvicorn](https://www.uvicorn.org/) - ASGI server
- National Rail API - Live train data
