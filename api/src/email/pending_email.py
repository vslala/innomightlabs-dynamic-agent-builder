"""Pending email model and repository for failed email retry."""
import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional, List
from enum import Enum

from src.db import get_dynamodb_resource
from src.config import settings

log = logging.getLogger(__name__)


class EmailType(Enum):
    """Email type identifiers."""

    WELCOME = "welcome"
    SUBSCRIPTION_CONFIRMED = "subscription_confirmed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    PAYMENT_FAILED = "payment_failed"


@dataclass
class PendingEmail:
    """Model for emails that failed to send and need retry."""

    email_id: str  # Unique ID for this email
    to_email: str
    email_type: str  # EmailType enum value
    subject: str
    template_variables: dict
    created_at: int  # Unix timestamp
    ttl: int  # Unix timestamp for DynamoDB TTL (1 day after created_at)
    retry_count: int = 0
    last_error: Optional[str] = None

    def to_dynamodb_item(self) -> dict:
        """Convert to DynamoDB item format."""
        return {
            "pk": f"PENDING_EMAIL#{self.email_id}",
            "sk": f"PENDING_EMAIL#{self.email_id}",
            "email_id": self.email_id,
            "to_email": self.to_email,
            "email_type": self.email_type,
            "subject": self.subject,
            "template_variables": self.template_variables,
            "created_at": str(self.created_at),  # Convert to string for GSI compatibility
            "ttl": self.ttl,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "PendingEmail":
        """Create from DynamoDB item."""
        return cls(
            email_id=item["email_id"],
            to_email=item["to_email"],
            email_type=item["email_type"],
            subject=item["subject"],
            template_variables=item["template_variables"],
            created_at=int(item["created_at"]),  # Convert string back to int
            ttl=item["ttl"],
            retry_count=item.get("retry_count", 0),
            last_error=item.get("last_error"),
        )


class PendingEmailRepository:
    """Repository for managing pending emails in DynamoDB."""

    def __init__(self):
        """Initialize repository with DynamoDB resource."""
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def create(self, pending_email: PendingEmail) -> None:
        """
        Save pending email to DynamoDB.

        Args:
            pending_email: PendingEmail instance to save
        """
        try:
            self.table.put_item(Item=pending_email.to_dynamodb_item())
            log.info(f"Created pending email: {pending_email.email_id}")
        except Exception as e:
            log.error(f"Failed to create pending email {pending_email.email_id}: {e}")
            raise

    def get(self, email_id: str) -> Optional[PendingEmail]:
        """
        Get pending email by ID.

        Args:
            email_id: Unique email identifier

        Returns:
            PendingEmail if found, None otherwise
        """
        try:
            response = self.table.get_item(
                Key={
                    "pk": f"PENDING_EMAIL#{email_id}",
                    "sk": f"PENDING_EMAIL#{email_id}",
                }
            )
            item = response.get("Item")
            if item:
                return PendingEmail.from_dynamodb_item(item)
            return None
        except Exception as e:
            log.error(f"Failed to get pending email {email_id}: {e}")
            return None

    def list_all(self, limit: int = 100) -> List[PendingEmail]:
        """
        List all pending emails (for retry processing).

        Args:
            limit: Maximum number of emails to return

        Returns:
            List of PendingEmail instances
        """
        try:
            # Scan for all pending emails
            # Note: In production, consider using a GSI for more efficient querying
            response = self.table.scan(
                FilterExpression="begins_with(pk, :pk_prefix)",
                ExpressionAttributeValues={":pk_prefix": "PENDING_EMAIL#"},
                Limit=limit,
            )

            pending_emails = []
            for item in response.get("Items", []):
                try:
                    pending_emails.append(PendingEmail.from_dynamodb_item(item))
                except Exception as e:
                    log.error(f"Failed to parse pending email item: {e}")
                    continue

            log.info(f"Found {len(pending_emails)} pending emails")
            return pending_emails

        except Exception as e:
            log.error(f"Failed to list pending emails: {e}")
            return []

    def delete(self, email_id: str) -> None:
        """
        Delete pending email from DynamoDB.

        Args:
            email_id: Unique email identifier
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"PENDING_EMAIL#{email_id}",
                    "sk": f"PENDING_EMAIL#{email_id}",
                }
            )
            log.info(f"Deleted pending email: {email_id}")
        except Exception as e:
            log.error(f"Failed to delete pending email {email_id}: {e}")
            raise

    def update_retry(self, email_id: str, error_message: str) -> None:
        """
        Increment retry count and update error message.

        Args:
            email_id: Unique email identifier
            error_message: Error message from failed attempt
        """
        try:
            self.table.update_item(
                Key={
                    "pk": f"PENDING_EMAIL#{email_id}",
                    "sk": f"PENDING_EMAIL#{email_id}",
                },
                UpdateExpression="SET retry_count = retry_count + :inc, last_error = :error",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":error": error_message,
                },
            )
            log.info(f"Updated retry count for pending email: {email_id}")
        except Exception as e:
            log.error(f"Failed to update pending email {email_id}: {e}")
            raise


def create_pending_email(
    to_email: str,
    email_type: EmailType,
    subject: str,
    template_variables: dict,
) -> PendingEmail:
    """
    Create a pending email instance with proper TTL.

    Args:
        to_email: Recipient email address
        email_type: Type of email (EmailType enum)
        subject: Email subject line
        template_variables: Template variables for email

    Returns:
        PendingEmail instance ready to save
    """
    import uuid

    now = int(time.time())
    ttl = now + (24 * 60 * 60)  # 1 day from now

    return PendingEmail(
        email_id=str(uuid.uuid4()),
        to_email=to_email,
        email_type=email_type.value,
        subject=subject,
        template_variables=template_variables,
        created_at=now,
        ttl=ttl,
        retry_count=0,
    )
