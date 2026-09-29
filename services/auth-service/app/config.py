import os


class Settings:
    service_name = "auth-service"
    database_path = os.getenv("DATABASE_PATH", "/data/auth.db")
    kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    kafka_topic = os.getenv("KAFKA_TOPIC", "user.registered.v1")
    jwt_secret = os.getenv("JWT_SECRET", "local-demo-secret-change-me")
    jwt_ttl_seconds = int(os.getenv("JWT_TTL_SECONDS", "3600"))
    demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"
    cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]


settings = Settings()
