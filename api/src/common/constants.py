"""
Shared constants used across the application.

These constants define thresholds and limits for memory management,
compaction, and other system-wide settings.
"""

# Memory capacity thresholds
CAPACITY_WARNING_THRESHOLD = 0.80  # 80% - warn when memory block approaches limit
COMPACTION_TARGET = 0.50  # 50% - target capacity after compaction

# Pagination defaults
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

# Agent processing limits
MAX_TOOL_ITERATIONS = 10  # Maximum tool calls per message processing
