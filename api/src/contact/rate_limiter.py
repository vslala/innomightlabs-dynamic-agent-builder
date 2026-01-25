"""Rate limiting for contact form submissions using DynamoDB TTL."""
import hashlib
import time
import logging
from typing import Optional

from src.db import get_dynamodb_resource
from src.config import settings

log = logging.getLogger(__name__)


def _hash_ip(ip_address: str) -> str:
    """Hash IP address for privacy."""
    return hashlib.sha256(ip_address.encode()).hexdigest()[:16]


def check_rate_limit(ip_address: str, window_seconds: int = 300) -> tuple[bool, Optional[int]]:
    """
    Check if IP address has exceeded rate limit.

    Args:
        ip_address: Client IP address
        window_seconds: Rate limit window in seconds (default: 5 minutes)

    Returns:
        Tuple of (is_allowed, seconds_until_allowed)
        - is_allowed: True if submission is allowed, False if rate limited
        - seconds_until_allowed: None if allowed, otherwise seconds to wait
    """
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    ip_hash = _hash_ip(ip_address)
    pk = f"RATE_LIMIT#CONTACT#{ip_hash}"
    sk = f"RATE_LIMIT#CONTACT"

    try:
        # Check if rate limit entry exists
        response = table.get_item(Key={"pk": pk, "sk": sk})
        item = response.get("Item")

        if item:
            # Rate limit active
            ttl = item.get("ttl", 0)
            now = int(time.time())
            seconds_remaining = max(0, ttl - now)

            log.info(f"Rate limit active for IP hash {ip_hash}, {seconds_remaining}s remaining")
            return False, seconds_remaining

        # No active rate limit, allow submission
        return True, None

    except Exception as e:
        log.error(f"Error checking rate limit: {e}")
        # On error, allow submission (fail open)
        return True, None


def record_submission(ip_address: str, window_seconds: int = 300) -> None:
    """
    Record a submission to enforce rate limit.

    Args:
        ip_address: Client IP address
        window_seconds: Rate limit window in seconds (default: 5 minutes)
    """
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    ip_hash = _hash_ip(ip_address)
    pk = f"RATE_LIMIT#CONTACT#{ip_hash}"
    sk = f"RATE_LIMIT#CONTACT"

    now = int(time.time())
    ttl = now + window_seconds

    try:
        table.put_item(Item={
            "pk": pk,
            "sk": sk,
            "ip_hash": ip_hash,
            "submitted_at": now,
            "ttl": ttl,
        })
        log.info(f"Recorded submission for IP hash {ip_hash}, expires in {window_seconds}s")
    except Exception as e:
        log.error(f"Error recording submission: {e}")
        # Non-critical, continue even if recording fails
