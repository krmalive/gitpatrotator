"""Token expiry and rotation scheduling utilities."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .config import TokenConfig


logger = logging.getLogger(__name__)


@dataclass
class TokenStatus:
    """Token status information."""
    is_valid: bool
    is_expired: bool
    days_until_expiry: Optional[int]
    days_since_created: Optional[int]
    needs_rotation: bool
    rotation_reason: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    last_rotated: Optional[datetime] = None


class TokenExpiryChecker:
    """Utility class for checking token expiry and rotation needs."""
    
    @staticmethod
    def parse_datetime(date_str: str) -> Optional[datetime]:
        """Parse datetime string in various formats."""
        if not date_str:
            return None
        
        # Try using Python's built-in ISO format parser first (Python 3.7+)
        try:
            # This handles most ISO formats including timezone offsets
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
        
        # Fallback to manual parsing for older formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",      # ISO format with microseconds
            "%Y-%m-%dT%H:%M:%SZ",         # ISO format
            "%Y-%m-%dT%H:%M:%S",          # ISO format without Z
            "%Y-%m-%d %H:%M:%S",          # Space separated
            "%Y-%m-%d",                   # Date only
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Assume UTC if no timezone info
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        
        logger.warning(f"Could not parse datetime: {date_str}")
        return None
    
    @staticmethod
    def _parse_vault_dates(vault_data: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        """Parse dates from vault data."""
        expires_at = None
        created_at = None
        last_rotated = None
        
        if vault_data.get('expires_at'):
            expires_at = TokenExpiryChecker.parse_datetime(vault_data['expires_at'])
        
        if vault_data.get('created_at'):
            created_at = TokenExpiryChecker.parse_datetime(vault_data['created_at'])
        
        if vault_data.get('last_rotated'):
            last_rotated = TokenExpiryChecker.parse_datetime(vault_data['last_rotated'])
        
        return expires_at, created_at, last_rotated
    
    @staticmethod
    def _get_gitlab_expiry_info(expires_at: Optional[datetime], created_at: Optional[datetime], gitlab_client) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get expiry information from GitLab API if not available in Vault."""
        if expires_at or not gitlab_client:
            return expires_at, created_at
        
        try:
            logger.info("No expiry information in Vault, checking GitLab API...")
            token_details = gitlab_client.get_current_token_details()
            
            if not token_details:
                return expires_at, created_at
            
            if token_details.get('expires_at'):
                expires_at = TokenExpiryChecker.parse_datetime(token_details['expires_at'])
                logger.info(f"Found expiry date from GitLab API: {expires_at}")
            
            if not created_at and token_details.get('created_at'):
                created_at = TokenExpiryChecker.parse_datetime(token_details['created_at'])
                
        except Exception as e:
            logger.warning(f"Could not get expiry info from GitLab API: {str(e)}")
        
        return expires_at, created_at
    
    @staticmethod
    def _normalize_datetime_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Normalize datetime to UTC timezone."""
        if not dt:
            return dt
        
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        else:
            return dt.replace(tzinfo=timezone.utc)
    
    @staticmethod
    def _calculate_rotation_needs(token_config: TokenConfig, expires_at: Optional[datetime], 
                                created_at: Optional[datetime], now: datetime) -> Tuple[bool, str]:
        """Determine if rotation is needed and the reason."""
        days_until_expiry = None
        days_since_created = None
        
        if expires_at:
            days_until_expiry = (expires_at - now).days
        
        if created_at:
            days_since_created = (now - created_at).days
        
        # Check if token is expired
        if expires_at and expires_at <= now:
            return True, "Token has expired"
        
        # Check if token expires soon
        if days_until_expiry is not None and days_until_expiry <= token_config.rotation_interval_days:
            return True, f"Token expires in {days_until_expiry} days (threshold: {token_config.rotation_interval_days} days)"
        
        # Check if token exceeds max age
        if (token_config.max_age_days and days_since_created is not None 
            and days_since_created >= token_config.max_age_days):
            return True, f"Token is {days_since_created} days old (max age: {token_config.max_age_days} days)"
        
        return False, "Token is current"
    
    @staticmethod
    def get_token_status(token_config: TokenConfig, vault_data: Dict[str, Any], gitlab_client=None) -> TokenStatus:
        """Analyze token status and determine if rotation is needed."""
        now = datetime.now(timezone.utc)
        
        # Parse dates from vault data
        expires_at, created_at, last_rotated = TokenExpiryChecker._parse_vault_dates(vault_data)
        
        # Get expiry info from GitLab API if needed
        if token_config.type == 'gitlab':
            expires_at, created_at = TokenExpiryChecker._get_gitlab_expiry_info(expires_at, created_at, gitlab_client)
        
        # Use last_rotated as created_at if created_at is not available
        if not created_at and last_rotated:
            created_at = last_rotated
        
        # Normalize all datetimes to UTC for consistent calculations
        expires_at = TokenExpiryChecker._normalize_datetime_to_utc(expires_at)
        created_at = TokenExpiryChecker._normalize_datetime_to_utc(created_at)
        
        # Calculate days
        days_until_expiry = (expires_at - now).days if expires_at else None
        days_since_created = (now - created_at).days if created_at else None
        
        # Determine if token is expired
        is_expired = expires_at is not None and expires_at <= now
        
        # Determine if rotation is needed and why
        needs_rotation, rotation_reason = TokenExpiryChecker._calculate_rotation_needs(
            token_config, expires_at, created_at, now
        )
        
        return TokenStatus(
            is_valid=not is_expired,
            is_expired=is_expired,
            days_until_expiry=days_until_expiry,
            days_since_created=days_since_created,
            needs_rotation=needs_rotation,
            rotation_reason=rotation_reason,
            expires_at=expires_at,
            created_at=created_at,
            last_rotated=last_rotated
        )
    
    @staticmethod
    def should_rotate_token(token_config: TokenConfig, vault_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Simplified check if token should be rotated."""
        status = TokenExpiryChecker.get_token_status(token_config, vault_data)
        return status.needs_rotation, status.rotation_reason