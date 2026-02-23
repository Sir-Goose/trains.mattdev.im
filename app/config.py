import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and configuration"""
    
    # API Configuration
    rail_api_base_url: str = "https://api1.raildata.org.uk/1010-live-arrival-and-departure-boards-arr-and-dep1_1/LDBWS/api/20220120"
    rail_api_key: str = ""
    rail_api_num_rows: int = 150  # Maximum trains to return
    rail_api_time_window: int = 120  # Time window in minutes (2 hours)
    
    # Cache Configuration
    cache_ttl_seconds: int = 60
    cache_backend: str = "memory"  # "memory" or "sqlite"
    cache_sqlite_path: str = "/tmp/leatherheadlive_cache.sqlite3"
    
    # CORS Configuration
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # Server Configuration
    app_name: str = "Leatherhead Live Train Board API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Try to load API key from 'key' file if not set via environment
        if not self.rail_api_key:
            # Try multiple possible locations for the key file
            possible_paths = [
                Path(__file__).parent.parent / "key",  # Project root (relative to app/)
                Path.cwd() / "key",  # Current working directory
                Path(__file__).resolve().parent.parent / "key",  # Resolved absolute path
            ]
            
            for key_file in possible_paths:
                if key_file.exists():
                    self.rail_api_key = key_file.read_text().strip()
                    break
            
            if not self.rail_api_key:
                raise FileNotFoundError(
                    "API key not found. Please create a 'key' file in the project root or set RAIL_API_KEY environment variable."
                )


# Global settings instance
settings = Settings()
