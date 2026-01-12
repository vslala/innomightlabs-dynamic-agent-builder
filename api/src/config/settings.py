import os
import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Settings:
    environment: str
    dynamodb_table: str
    aws_region: str
    frontend_url: str
    api_base_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("ENVIRONMENT", "dev")
        api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

        # Load Google OAuth credentials
        google_client_id = ""
        google_client_secret = ""

        # Try to load from JSON file (local dev)
        credentials_patterns = [
            Path(__file__).parent.parent.parent.parent.parent / "client_secret*.json",
        ]

        for pattern in credentials_patterns:
            for cred_file in pattern.parent.glob(pattern.name):
                with open(cred_file) as f:
                    creds = json.load(f)
                    web_creds = creds.get("web", {})
                    google_client_id = web_creds.get("client_id", "")
                    google_client_secret = web_creds.get("client_secret", "")
                    break

        # Override with env vars if present (Lambda)
        google_client_id = os.getenv("GOOGLE_CLIENT_ID", google_client_id)
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", google_client_secret)

        return cls(
            environment=environment,
            dynamodb_table=os.getenv("DYNAMODB_TABLE", "dynamic-agent-builder-main"),
            aws_region=os.getenv("AWS_REGION_NAME", "eu-west-2"),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5173"),
            api_base_url=api_base_url,
            jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-production"),
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_redirect_uri=f"{api_base_url}/auth/callback",
        )


settings = Settings.from_env()
