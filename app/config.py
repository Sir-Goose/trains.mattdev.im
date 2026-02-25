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

    # TfL API Configuration
    tfl_api_base_url: str = "https://api.tfl.gov.uk"
    tfl_app_key: str = ""
    tfl_app_id: str = ""
    tfl_modes: list[str] = ["tube", "overground"]
    
    # Cache Configuration
    cache_ttl_seconds: int = 60
    cache_backend: str = "memory"  # "memory" or "sqlite"
    cache_sqlite_path: str = "/tmp/trains_mattdev_im_cache.sqlite3"
    
    # CORS Configuration
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # Server Configuration
    app_name: str = "trains.mattdev.im Train Board API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Allow TFL_API_KEY as an alias for TFL_APP_KEY for shell compatibility.
        if not self.tfl_app_key:
            self.tfl_app_key = os.getenv("TFL_APP_KEY") or os.getenv("TFL_API_KEY", "")

        # Try to load TfL key from local file if not set via environment.
        if not self.tfl_app_key:
            self.tfl_app_key = self._load_key_from_file("tfl_key")
        
        # Try to load API key from 'key' file if not set via environment
        if not self.rail_api_key:
            self.rail_api_key = self._load_key_from_file("key")
            
            if not self.rail_api_key:
                raise FileNotFoundError(
                    "API key not found. Please create a 'key' file in the project root or set RAIL_API_KEY environment variable."
                )

    @staticmethod
    def _load_key_from_file(filename: str) -> str:
        """Load API key from project root or current working directory."""
        possible_paths = [
            Path(__file__).parent.parent / filename,  # Project root (relative to app/)
            Path.cwd() / filename,  # Current working directory
            Path(__file__).resolve().parent.parent / filename,  # Resolved absolute path
        ]

        for key_file in possible_paths:
            if key_file.exists():
                value = key_file.read_text().strip()
                if value:
                    return value

        return ""


# Global settings instance
settings = Settings()
