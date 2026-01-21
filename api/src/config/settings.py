"""
Application settings with configuration validation.

Required configuration must be set via environment variables.
The application will fail fast on startup if required config is missing.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, missing_vars: list[str], feature: Optional[str] = None):
        self.missing_vars = missing_vars
        self.feature = feature
        if feature:
            message = f"Missing required configuration for {feature}: {', '.join(missing_vars)}"
        else:
            message = f"Missing required configuration: {', '.join(missing_vars)}"
        super().__init__(message)


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # Core settings (always required)
    environment: str
    dynamodb_table: str
    aws_region: str
    frontend_url: str
    api_base_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24 * 7

    # Google OAuth (required for authentication)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Pinecone Vector Store (required for knowledge base features)
    pinecone_api_key: str = ""
    pinecone_host: str = ""
    pinecone_index: str = ""

    # Bedrock Embeddings (has sensible defaults)
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    bedrock_embedding_dimension: int = 1024

    # Feature flags
    _validated_features: set = field(default_factory=set)

    # Stripe (optional; only required for billing features)
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter_monthly: str = ""
    stripe_price_starter_annual: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_annual: str = ""

    def validate_core(self) -> None:
        """
        Validate core configuration required for the app to start.

        Raises:
            ConfigValidationError: If required config is missing
        """
        missing = []

        if not self.dynamodb_table:
            missing.append("DYNAMODB_TABLE")
        if not self.aws_region:
            missing.append("AWS_REGION_NAME")
        if not self.jwt_secret or self.jwt_secret == "dev-secret-change-in-production":
            if self.environment != "dev":
                missing.append("JWT_SECRET")

        if missing:
            raise ConfigValidationError(missing, "core application")

    def validate_google_oauth(self) -> None:
        """
        Validate Google OAuth configuration.

        Raises:
            ConfigValidationError: If required config is missing
        """
        if "google_oauth" in self._validated_features:
            return

        missing = []
        if not self.google_client_id:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.google_client_secret:
            missing.append("GOOGLE_CLIENT_SECRET")

        if missing:
            raise ConfigValidationError(missing, "Google OAuth")

        self._validated_features.add("google_oauth")

    def validate_pinecone(self) -> None:
        """
        Validate Pinecone configuration for knowledge base features.

        Raises:
            ConfigValidationError: If required config is missing
        """
        if "pinecone" in self._validated_features:
            return

        missing = []
        if not self.pinecone_api_key:
            missing.append("PINECONE_API_KEY")
        if not self.pinecone_host:
            missing.append("PINECONE_HOST")
        if not self.pinecone_index:
            missing.append("PINECONE_INDEX")

        if missing:
            raise ConfigValidationError(missing, "Pinecone vector store")

        self._validated_features.add("pinecone")

    def is_pinecone_configured(self) -> bool:
        """Check if Pinecone is fully configured without raising an error."""
        return bool(
            self.pinecone_api_key
            and self.pinecone_host
            and self.pinecone_index
        )

    def is_google_oauth_configured(self) -> bool:
        """Check if Google OAuth is fully configured without raising an error."""
        return bool(
            self.google_client_id
            and self.google_client_secret
        )

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Load settings from environment variables.

        Returns:
            Settings instance with values from environment
        """
        environment = os.getenv("ENVIRONMENT", "dev")
        api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

        # Load Google OAuth credentials
        google_client_id = ""
        google_client_secret = ""

        # Try to load from JSON file (local dev only)
        if environment == "dev":
            credentials_patterns = [
                Path(__file__).parent.parent.parent.parent.parent / "client_secret*.json",
            ]

            for pattern in credentials_patterns:
                for cred_file in pattern.parent.glob(pattern.name):
                    try:
                        with open(cred_file) as f:
                            creds = json.load(f)
                            web_creds = creds.get("web", {})
                            google_client_id = web_creds.get("client_id", "")
                            google_client_secret = web_creds.get("client_secret", "")
                            break
                    except Exception as e:
                        log.warning(f"Failed to load credentials from {cred_file}: {e}")

        # Override with env vars if present (Lambda/production)
        google_client_id = os.getenv("GOOGLE_CLIENT_ID", google_client_id)
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", google_client_secret)

        return cls(
            environment=environment,
            dynamodb_table=os.getenv("DYNAMODB_TABLE", "dynamic-agent-builder-main" if environment == "dev" else ""),
            aws_region=os.getenv("AWS_REGION_NAME", "eu-west-2"),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5173" if environment == "dev" else ""),
            api_base_url=api_base_url,
            jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-production" if environment == "dev" else ""),
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_redirect_uri=f"{api_base_url}/auth/callback",
            # Pinecone - no defaults, must be explicitly configured
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            pinecone_host=os.getenv("PINECONE_HOST", ""),
            pinecone_index=os.getenv("PINECONE_INDEX", ""),
            # Bedrock - has sensible defaults
            bedrock_embedding_model=os.getenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"),
            bedrock_embedding_dimension=int(os.getenv("BEDROCK_EMBEDDING_DIMENSION", "1024")),
            # Stripe - optional, used for billing
            stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
            stripe_publishable_key=os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
            stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_starter_monthly=os.getenv("STRIPE_PRICE_STARTER_MONTHLY", ""),
            stripe_price_starter_annual=os.getenv("STRIPE_PRICE_STARTER_ANNUAL", ""),
            stripe_price_pro_monthly=os.getenv("STRIPE_PRICE_PRO_MONTHLY", ""),
            stripe_price_pro_annual=os.getenv("STRIPE_PRICE_PRO_ANNUAL", ""),
        )


# Global settings instance
settings = Settings.from_env()
