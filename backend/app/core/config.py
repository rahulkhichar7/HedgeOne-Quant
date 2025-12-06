from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# --- Configuration Class ---
# This class reads all variables from the environment (.env file)
class Settings(BaseSettings):
    # --- CORE PROJECT SETTINGS ---
    PROJECT_NAME: str = "Quant Platform API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # --- DATABASE SETTINGS (PostgreSQL/TimescaleDB) ---
    POSTGRES_USER: str = "quant_user"
    POSTGRES_PASSWORD: str = "quant_password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "quant_db"
    
    # DATABASE_URL is constructed from the above variables but often kept separate in .env for simplicity.
    # We define it here as Optional if you decide to use it manually later.
    DATABASE_URL: Optional[str] = None 

    # --- CACHING SETTINGS (Redis) ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- TRADING BROKER API KEYS (Future Use) ---
    FIRE_D_API_KEY: Optional[str] = None
    FIRE_D_SECRET_KEY: Optional[str] = None
    FIRE_D_REDIRECT_URI: Optional[str] = None
    EXCHANGE_DATA_API_KEY: Optional[str] = None

    # --- AI API KEYS (Future Use) ---
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file='backend/.env',  # Looks for the .env file in the backend directory
        extra='ignore',           # Ignores unknown environment variables
        case_sensitive=True       # Ensures variable names match exactly
    )

# Create an instance of the settings class to be imported throughout the application
settings = Settings()