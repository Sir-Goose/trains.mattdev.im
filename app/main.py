from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.routers import boards, pages


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for UK National Rail live departure and arrival boards",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Configure GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Include routers
app.include_router(boards.router)  # JSON API routes
app.include_router(pages.router)   # HTML template routes


# Custom 404 handler
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    # Check if request is for API or HTML
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Not found"}
        )
    else:
        # Extract CRS from URL if available
        path_parts = request.url.path.split("/")
        crs = path_parts[2] if len(path_parts) > 2 else "UNKNOWN"
        
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "crs": crs},
            status_code=404
        )


# Custom 500 handler
@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )
    else:
        return templates.TemplateResponse(
            "errors/500.html",
            {"request": request},
            status_code=500
        )


# Health check endpoint
@app.get("/api/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api_key_configured": bool(settings.rail_api_key),
        "cache_ttl": settings.cache_ttl_seconds
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions"""
    # Check if it's an HTTPException
    if isinstance(exc, HTTPException):
        if exc.status_code == 404:
            return await not_found_handler(request, exc)
        elif exc.status_code == 500:
            return await server_error_handler(request, exc)
    
    # For API routes, return JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "detail": str(exc) if settings.debug else "An unexpected error occurred"
            }
        )
    else:
        # For web routes, return HTML error page
        return templates.TemplateResponse(
            "errors/500.html",
            {"request": request},
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
