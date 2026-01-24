"""
Audit Logging System

Logs security-relevant actions to an SQLite table for compliance and debugging.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import Session

from .database import Base, engine

logger = logging.getLogger(__name__)


class AuditLog(Base):
    """Audit log entry model."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON string


# Audit action constants
class AuditAction:
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    LISTING_CREATED = "listing_created"
    LISTING_UPDATED = "listing_updated"
    LISTING_DELETED = "listing_deleted"
    FIO_REFRESH = "fio_refresh"
    API_KEY_UPDATED = "api_key_updated"


def log_audit(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log an audit event to the database.

    Args:
        db: SQLAlchemy session
        action: The action being logged (use AuditAction constants)
        user_id: ID of the user performing the action (if applicable)
        entity_type: Type of entity being acted upon (e.g., "listing", "user")
        entity_id: ID of the entity being acted upon
        details: Additional details as a dictionary (will be JSON serialized)
    """
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details) if details else None,
        )
        db.add(entry)
        db.commit()
        logger.debug(f"Audit log: {action} by user {user_id} on {entity_type}:{entity_id}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        # Don't raise - audit failures shouldn't break the app
        db.rollback()
