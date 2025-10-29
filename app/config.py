# app/config.py - Configuration
import os

class Config:
    """Application configuration"""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    VERSION = os.getenv('APP_VERSION', '0.1.0')

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    # Redis
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    REDIS_DB = int(os.getenv('REDIS_DB', 0))

    # Session
    SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', 3600))  # 1 hour

    # Adaptive Testing
    DEFAULT_CONCEPTS = int(os.getenv('DEFAULT_CONCEPTS', 5))
    MAX_QUESTIONS = int(os.getenv('MAX_QUESTIONS', 50))
    MIN_QUESTIONS = int(os.getenv('MIN_QUESTIONS', 5))

    # External API (Tier 3 - Source of Truth)
    EXTERNAL_API_URL = os.getenv('EXTERNAL_API_URL', 'https://api.example.com')
    EXTERNAL_API_KEY = os.getenv('EXTERNAL_API_KEY', '')
    EXTERNAL_API_TIMEOUT = int(os.getenv('EXTERNAL_API_TIMEOUT', 30))  # seconds

    # Cache Configuration
    REDIS_QUESTION_POOL_TTL = int(os.getenv('REDIS_QUESTION_POOL_TTL', 86400))  # 24 hours
    SUPABASE_CACHE_EXPIRY = int(os.getenv('SUPABASE_CACHE_EXPIRY', 604800))  # 7 days
