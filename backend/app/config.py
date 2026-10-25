from functools import lru_cache
import os
from pydantic import BaseModel, field_validator

class Settings(BaseModel):
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./orbit.db')
    jwt_secret: str = os.getenv('JWT_SECRET', 'orbit-development-secret-change-me')
    cors_origins: str = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000')
    jwt_algorithm: str = os.getenv('JWT_ALGORITHM', 'HS256')
    access_token_expire_minutes: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '1440'))
    p_init: float = float(os.getenv('BKT_P_INIT', '0.3'))
    p_transit: float = float(os.getenv('BKT_P_TRANSIT', '0.1'))
    p_slip: float = float(os.getenv('BKT_P_SLIP', '0.1'))
    p_guess: float = float(os.getenv('BKT_P_GUESS', '0.2'))
    w1: float = float(os.getenv('ROADMAP_W1', '0.5'))
    w2: float = float(os.getenv('ROADMAP_W2', '0.3'))
    w3: float = float(os.getenv('ROADMAP_W3', '0.2'))
    dkt_min_interactions: int = int(os.getenv('DKT_MIN_INTERACTIONS', '50'))
    retention_half_life_days: float = float(os.getenv('RETENTION_HALF_LIFE_DAYS', '14'))
    retention_threshold: float = float(os.getenv('RETENTION_THRESHOLD', '0.7'))
    edge_confidence_gap_threshold: float = float(os.getenv('EDGE_CONFIDENCE_GAP_THRESHOLD', '0.15'))
    edge_review_threshold: float = float(os.getenv('EDGE_REVIEW_THRESHOLD', '0.6'))
    dkt_hidden_size: int = int(os.getenv('DKT_HIDDEN_SIZE', '24'))
    dkt_learning_rate: float = float(os.getenv('DKT_LEARNING_RATE', '0.05'))
    dkt_checkpoint_path: str | None = os.getenv('DKT_CHECKPOINT_PATH')
    admin_emails: str = os.getenv('ADMIN_EMAILS', 'demo@orbit.dev')

    @field_validator('p_init', 'p_transit', 'p_slip', 'p_guess', 'w1', 'w2', 'w3')
    @classmethod
    def probability_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError('probability and weight parameters must be between 0 and 1')
        return value

    @field_validator('w3')
    @classmethod
    def weights_sum_to_one(cls, value: float, info):
        # The complete sum is checked in validate_weights after construction.
        return value

    def admin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(',') if email.strip()}

    def cors_origin_set(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    def validate_weights(self) -> None:
        if abs((self.w1 + self.w2 + self.w3) - 1.0) > 1e-6:
            raise ValueError('ROADMAP_W1 + ROADMAP_W2 + ROADMAP_W3 must equal 1.0')

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_weights()
    return settings
