"""Core token rotation functionality."""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .config import Config, TokenConfig
from .vault_client import VaultClient
from .github_app_client import GitHubAppClient
from .gitlab_client import GitLabClient
from .expiry_checker import TokenExpiryChecker, TokenStatus


logger = logging.getLogger(__name__)


class TokenRotationError(Exception):
    """Exception raised during token rotation."""
    pass


class TokenRotator:
    """Main class for rotating GitHub and GitLab tokens."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vault_client = VaultClient(config.vault)
    
    def rotate_token(self, token_name: str, dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
        """Rotate a specific token by name.
        
        Args:
            token_name: Name of the token to rotate
            dry_run: If True, only validate without making changes
            force: If True, rotate even if not needed based on expiry
            
        Returns:
            Dictionary with rotation results and metadata
        """
        token_config = self._find_token_config(token_name)
        logger.info(f"Starting rotation check for token: {token_name} (type: {token_config.type})")
        
        # Get current token data and status
        current_data = self.vault_client.get_token_data(token_config.vault_path, token_config.token_field)
        if not current_data:
            raise TokenRotationError(f"No existing token found in Vault at {token_config.vault_path}")
        
        # Create GitLab client for expiry checking if it's a GitLab token
        gitlab_client = None
        if token_config.type == 'gitlab':
            from .gitlab_client import GitLabClient
            gitlab_client = GitLabClient(token_config.gitlab_url, token_config.username, current_data['token'])
        
        token_status = TokenExpiryChecker.get_token_status(token_config, current_data, gitlab_client)
        
        # Check if rotation is needed
        if not self._should_rotate_token(force, token_status, dry_run):
            return self._create_no_rotation_response(token_name, token_config, token_status)
        
        # Log rotation mode
        self._log_rotation_mode(dry_run, force)
        
        try:
            return self._perform_token_rotation(token_config, dry_run, token_status)
        except Exception as e:
            logger.error(f"Failed to rotate token {token_name}: {str(e)}")
            raise TokenRotationError(f"Token rotation failed: {str(e)}")
    
    def _find_token_config(self, token_name: str) -> TokenConfig:
        """Find token configuration by name."""
        for token in self.config.tokens:
            if token.name == token_name:
                return token
        raise TokenRotationError(f"Token configuration not found: {token_name}")
    
    def _should_rotate_token(self, force: bool, token_status: TokenStatus, dry_run: bool) -> bool:
        """Determine if token should be rotated."""
        return force or token_status.needs_rotation or dry_run
    
    def _create_no_rotation_response(self, token_name: str, token_config: TokenConfig, token_status: TokenStatus) -> Dict[str, Any]:
        """Create response for when rotation is not needed."""
        logger.info(f"Token {token_name} does not need rotation: {token_status.rotation_reason}")
        return {
            "status": "no_rotation_needed",
            "token_name": token_name,
            "type": token_config.type,
            "rotation_reason": token_status.rotation_reason,
            "days_until_expiry": token_status.days_until_expiry,
            "days_since_created": token_status.days_since_created,
            "expires_at": token_status.expires_at.isoformat() if token_status.expires_at else None,
            "message": f"Token rotation not required: {token_status.rotation_reason}"
        }
    
    def _log_rotation_mode(self, dry_run: bool, force: bool) -> None:
        """Log the current rotation mode."""
        if dry_run:
            logger.info("DRY RUN mode - no changes will be made")
        if force:
            logger.info("FORCE mode - rotating regardless of expiry status")
    
    def _perform_token_rotation(self, token_config: TokenConfig, dry_run: bool, token_status: TokenStatus) -> Dict[str, Any]:
        """Perform the actual token rotation based on type."""
        if token_config.type == "github-app":
            return self._rotate_github_app_token(token_config, dry_run, token_status)
        elif token_config.type == "gitlab":
            return self._rotate_gitlab_token(token_config, dry_run, token_status)
        else:
            raise TokenRotationError(f"Unsupported token type: {token_config.type}")
    
    def _validate_current_gitlab_token(self, token_config: TokenConfig, current_data: Dict[str, Any]) -> GitLabClient:
        """Validate current GitLab token and return client."""
        current_token = current_data['token']
        gitlab_client = GitLabClient(token_config.gitlab_url, token_config.username, current_token)
        
        if not gitlab_client.test_token():
            raise TokenRotationError("Current GitLab token is invalid or expired")
        
        token_info = gitlab_client.get_token_info()
        if not token_info:
            raise TokenRotationError("Failed to get GitLab token information")
        
        logger.info(f"Current GitLab token is valid for user: {token_info.get('username')}")
        return gitlab_client
    
    def _handle_gitlab_dry_run(self, token_config: TokenConfig, gitlab_client: GitLabClient, token_status: TokenStatus) -> Dict[str, Any]:
        """Handle dry run for GitLab token rotation."""
        token_info = gitlab_client.get_token_info()
        permissions = gitlab_client.test_token_permissions()
        
        return {
            "status": "dry_run_success",
            "token_name": token_config.name,
            "type": "gitlab",
            "current_token_valid": True,
            "user": token_info.get('username'),
            "permissions": permissions,
            "rotation_needed": token_status.needs_rotation,
            "rotation_reason": token_status.rotation_reason,
            "days_until_expiry": token_status.days_until_expiry,
            "days_since_created": token_status.days_since_created,
            "expires_at": token_status.expires_at.isoformat() if token_status.expires_at else None,
            "message": "Dry run completed successfully - no changes made"
        }
    
    def _create_new_gitlab_token(self, token_config: TokenConfig, gitlab_client: GitLabClient) -> Dict[str, Any]:
        """Create and validate new GitLab token."""
        from datetime import timedelta
        
        scopes = token_config.scopes or ["api", "read_user", "read_repository", "write_repository"]
        expires_at = (datetime.now(timezone.utc) + timedelta(days=token_config.token_validity_days)).strftime('%Y-%m-%d')
        
        new_token_data = gitlab_client.create_token(
            name=f"{token_config.name}-token",
            scopes=scopes,
            expires_at=expires_at
        )
        
        if not new_token_data:
            raise TokenRotationError("Failed to create new GitLab token")
        
        # Test new token
        new_gitlab_client = GitLabClient(token_config.gitlab_url, token_config.username, new_token_data['token'])
        if not new_gitlab_client.test_token():
            raise TokenRotationError("New GitLab token is not working")
        
        return new_token_data
    
    def _revoke_old_gitlab_token(self, gitlab_client: GitLabClient, current_data: Dict[str, Any]) -> None:
        """Revoke old GitLab token for cleanup."""
        old_token_id = current_data.get('token_id')
        if not old_token_id:
            logger.info("No old token ID found for revocation")
            return
        
        try:
            revoked = gitlab_client.revoke_token_by_id(int(old_token_id))
            if revoked:
                logger.info(f"Successfully revoked old GitLab token ID: {old_token_id}")
            else:
                logger.warning(f"Failed to revoke old GitLab token ID: {old_token_id}")
        except Exception as e:
            logger.warning(f"Error revoking old token: {str(e)}")
    
    def _rotate_gitlab_token(self, token_config: TokenConfig, dry_run: bool, token_status: TokenStatus) -> Dict[str, Any]:
        """Rotate a GitLab token."""
        # Get current token from Vault
        current_data = self.vault_client.get_token_data(token_config.vault_path, token_config.token_field)
        if not current_data:
            raise TokenRotationError(f"No existing token found in Vault at {token_config.vault_path}")
        
        # Validate current token and get client
        gitlab_client = self._validate_current_gitlab_token(token_config, current_data)
        
        # Handle dry run
        if dry_run:
            return self._handle_gitlab_dry_run(token_config, gitlab_client, token_status)
        
        # Create new token
        new_token_data = self._create_new_gitlab_token(token_config, gitlab_client)
        
        # Store new token in Vault
        self.vault_client.store_token_data(
            token_config.vault_path,
            new_token_data['token'],
            token_config.token_field,
            str(new_token_data.get('id', ''))
        )
        
        # Revoke old token
        self._revoke_old_gitlab_token(gitlab_client, current_data)
        
        logger.info(f"Successfully rotated GitLab token: {token_config.name}")
        
        # Get user info for response
        token_info = gitlab_client.get_token_info()
        
        return {
            "status": "success",
            "token_name": token_config.name,
            "type": "gitlab",
            "user": token_info.get('username') if token_info else None,
            "new_expires_at": new_token_data.get('expires_at'),
            "message": "GitLab token rotated successfully"
        }
    
    def _rotate_github_app_token(self, token_config: TokenConfig, dry_run: bool, token_status: TokenStatus) -> Dict[str, Any]:
        """Rotate a GitHub App installation token."""
        # Read private key
        try:
            with open(token_config.github_app.private_key_path, 'r') as f:
                private_key = f.read()
        except Exception as e:
            raise TokenRotationError(f"Failed to read GitHub App private key: {str(e)}")
        
        # Initialize GitHub App client
        app_client = GitHubAppClient(
            token_config.github_app.app_id,
            private_key,
            token_config.github_app.installation_id
        )
        
        # Test app configuration
        app_info = app_client.get_app_info()
        if not app_info:
            raise TokenRotationError("Failed to authenticate with GitHub App")
        
        logger.info(f"GitHub App '{app_info.get('name')}' authenticated successfully")
        
        if dry_run:
            return {
                "status": "dry_run_success",
                "token_name": token_config.name,
                "type": "github-app",
                "app_name": app_info.get('name'),
                "app_id": token_config.github_app.app_id,
                "installation_id": token_config.github_app.installation_id,
                "rotation_needed": token_status.needs_rotation,
                "rotation_reason": token_status.rotation_reason,
                "message": "Dry run completed successfully - GitHub App can generate tokens automatically"
            }
        
        # Generate new installation token
        permissions = token_config.github_app.permissions or {"contents": "read", "metadata": "read"}
        new_token_data = app_client.get_installation_token(permissions)
        
        if not new_token_data:
            raise TokenRotationError("Failed to generate GitHub App installation token")
        
        new_token = new_token_data['token']
        
        # Test new token
        if not app_client.test_installation_token(new_token):
            raise TokenRotationError("New GitHub App installation token is not working")
        
        # Store new token in Vault
        self.vault_client.store_token_data(
            token_config.vault_path,
            new_token,
            token_config.token_field
        )
        
        logger.info(f"Successfully rotated GitHub App token: {token_config.name}")
        
        return {
            "status": "success",
            "token_name": token_config.name,
            "type": "github-app",
            "app_name": app_info.get('name'),
            "new_expires_at": new_token_data.get('expires_at'),
            "message": "GitHub App installation token rotated successfully"
        }
    
    def rotate_all_tokens(self, dry_run: bool = False, force: bool = False) -> List[Dict[str, Any]]:
        """Rotate all configured tokens.
        
        Args:
            dry_run: If True, only validate without making changes
            force: If True, rotate even if not needed based on expiry
            
        Returns:
            List of rotation results for each token
        """
        results = []
        
        for token_config in self.config.tokens:
            try:
                result = self.rotate_token(token_config.name, dry_run, force)
                results.append(result)
            except Exception as e:
                results.append({
                    "status": "error",
                    "token_name": token_config.name,
                    "type": token_config.type,
                    "error": str(e),
                    "message": f"Failed to rotate token: {str(e)}"
                })
        
        return results
    
    def update_token_manually(self, token_name: str, new_token: str) -> Dict[str, Any]:
        """Manually update a token in Vault (useful for GitHub tokens).
        
        Args:
            token_name: Name of the token to update
            new_token: The new token value
            
        Returns:
            Dictionary with update results
        """
        token_config = None
        for token in self.config.tokens:
            if token.name == token_name:
                token_config = token
                break
        
        if not token_config:
            raise TokenRotationError(f"Token configuration not found: {token_name}")
        
        # Test new token
        if token_config.type == "github-app":
            # For GitHub App tokens, we don't manually update - they're generated automatically
            raise TokenRotationError("GitHub App tokens cannot be updated manually - they are generated automatically")
        elif token_config.type == "gitlab":
            client = GitLabClient(token_config.gitlab_url, token_config.username, new_token)
        else:
            raise TokenRotationError(f"Unsupported token type: {token_config.type}")
        
        if not client.test_token():
            raise TokenRotationError("New token is invalid or not working")
        
        # Store new token
        self.vault_client.store_token_data(
            token_config.vault_path,
            new_token,
            token_config.token_field
        )
        
        logger.info(f"Successfully updated token manually: {token_name}")
        
        return {
            "status": "success",
            "token_name": token_name,
            "type": token_config.type,
            "message": "Token updated manually and stored in Vault"
        }
    
    def check_all_tokens_expiry(self) -> List[Dict[str, Any]]:
        """Check expiry status of all configured tokens without rotating.
        
        Returns:
            List of token status information
        """
        results = []
        
        for token_config in self.config.tokens:
            try:
                # Get current token data from Vault
                current_data = self.vault_client.get_token_data(token_config.vault_path, token_config.token_field)
                if not current_data:
                    results.append({
                        "token_name": token_config.name,
                        "type": token_config.type,
                        "status": "error",
                        "message": f"No token found in Vault at {token_config.vault_path}"
                    })
                    continue
                
                # Check token status
                # Create GitLab client for expiry checking if it's a GitLab token
                gitlab_client = None
                if token_config.type == 'gitlab':
                    from .gitlab_client import GitLabClient
                    gitlab_client = GitLabClient(token_config.gitlab_url, token_config.username, current_data['token'])
                
                token_status = TokenExpiryChecker.get_token_status(token_config, current_data, gitlab_client)
                
                result = {
                    "token_name": token_config.name,
                    "type": token_config.type,
                    "is_valid": token_status.is_valid,
                    "is_expired": token_status.is_expired,
                    "needs_rotation": token_status.needs_rotation,
                    "rotation_reason": token_status.rotation_reason,
                    "days_until_expiry": token_status.days_until_expiry,
                    "days_since_created": token_status.days_since_created,
                    "rotation_interval_days": token_config.rotation_interval_days,
                    "max_age_days": token_config.max_age_days,
                    "expires_at": token_status.expires_at.isoformat() if token_status.expires_at else None,
                    "created_at": token_status.created_at.isoformat() if token_status.created_at else None,
                    "last_rotated": token_status.last_rotated.isoformat() if token_status.last_rotated else None
                }
                
                results.append(result)
                
            except Exception as e:
                results.append({
                    "token_name": token_config.name,
                    "type": token_config.type,
                    "status": "error",
                    "message": f"Failed to check token status: {str(e)}"
                })
        
        return results
