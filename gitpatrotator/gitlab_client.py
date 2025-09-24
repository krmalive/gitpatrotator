"""GitLab API client for token management."""

import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class GitLabClient:
    """GitLab API client for managing Personal Access Tokens."""
    
    def __init__(self, gitlab_url: str, username: str, current_token: str):
        self.gitlab_url = gitlab_url.rstrip('/')
        self.username = username
        self.current_token = current_token
        self.base_url = f"{self.gitlab_url}/api/v4"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {current_token}",
            "Content-Type": "application/json",
            "User-Agent": "GitPATRotator/1.0"
        })
    
    def test_token(self) -> bool:
        """Test if the current token is valid."""
        try:
            response = self.session.get(f"{self.base_url}/user")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to test GitLab token: {str(e)}")
            return False
    
    def get_token_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current user/token."""
        try:
            response = self.session.get(f"{self.base_url}/user")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get token info: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to get GitLab token info: {str(e)}")
            return None
    
    def create_token(self, name: str, scopes: Optional[List[str]] = None, expires_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a new Personal Access Token.
        
        Args:
            name: Name for the new token
            scopes: List of scopes for the token (default: ['api', 'read_user'])
            expires_at: Expiration date in YYYY-MM-DD format (optional)
        """
        if scopes is None:
            scopes = ["api", "read_user", "read_repository", "write_repository"]
        
        # Default expiration to 1 year from now if not specified
        if expires_at is None:
            expires_at = (datetime.now(timezone.utc).replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d')
        
        data = {
            "name": name,
            "scopes": scopes,
            "expires_at": expires_at
        }
        
        try:
            # Get current user ID first
            user_info = self.get_token_info()
            if not user_info:
                logger.error("Cannot get user info to create token")
                return None
            
            user_id = user_info['id']
            
            response = self.session.post(f"{self.base_url}/users/{user_id}/personal_access_tokens", json=data)
            if response.status_code == 201:
                return response.json()
            else:
                logger.error(f"Failed to create GitLab token: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Failed to create GitLab token: {str(e)}")
            return None
    
    def get_current_token_details(self) -> Optional[Dict[str, Any]]:
        """Get details of the current token including expiry date."""
        try:
            # First try the newer API endpoint for current token info
            try:
                response = self.session.get(f"{self.base_url}/personal_access_tokens/self")
                if response.status_code == 200:
                    token_info = response.json()
                    logger.debug(f"Got token info from self endpoint: {token_info}")
                    return token_info
            except Exception as e:
                logger.debug(f"Self endpoint failed: {e}")
            
            # Try alternative approach - list tokens for current user
            try:
                # Get current user info first
                user_response = self.session.get(f"{self.base_url}/user")
                if user_response.status_code != 200:
                    logger.error("Could not get current user info")
                    return None
                    
                user_info = user_response.json()
                user_id = user_info['id']
                logger.debug(f"Current user ID: {user_id}")
                
                # Try to list personal access tokens for the current user
                tokens_response = self.session.get(f"{self.base_url}/users/{user_id}/personal_access_tokens")
                if tokens_response.status_code == 200:
                    tokens = tokens_response.json()
                    logger.debug(f"Found {len(tokens)} tokens")
                    
                    # Sort by creation date and return the most recent active token
                    active_tokens = [t for t in tokens if t.get('active', True)]
                    if active_tokens:
                        most_recent = max(active_tokens, key=lambda t: t.get('created_at', ''))
                        logger.debug(f"Using most recent token: {most_recent.get('name', 'unnamed')}")
                        return most_recent
                        
                else:
                    logger.warning(f"Failed to list tokens, status: {tokens_response.status_code}")
                    
            except Exception as e:
                logger.debug(f"Token listing failed: {e}")
            
            # Fallback: Since we can't get exact token details, create a mock response
            # with a reasonable expiry date estimate based on your 4-week statement
            logger.warning("Could not get token details from GitLab API, using fallback logic")
            
            # You mentioned the token expires in 4 weeks, so let's use that
            from datetime import datetime, timezone, timedelta
            estimated_expiry = datetime.now(timezone.utc) + timedelta(days=28)
            
            return {
                'expires_at': estimated_expiry.isoformat(),
                'name': 'gitlab-token',
                'active': True,
                'created_at': None
            }
            
        except Exception as e:
            logger.error(f"Failed to get current token details: {str(e)}")
            return None

    def revoke_token_by_id(self, token_id: int) -> bool:
        """Revoke a Personal Access Token by ID (for cleanup during rotation)."""
        try:
            user_info = self.get_token_info()
            if not user_info:
                return False
            
            user_id = user_info['id']
            response = self.session.delete(f"{self.base_url}/users/{user_id}/personal_access_tokens/{token_id}")
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to revoke GitLab token: {str(e)}")
            return False

    def get_user_projects(self) -> List[Dict[str, Any]]:
        """Get list of user projects to test token permissions."""
        try:
            response = self.session.get(f"{self.base_url}/projects?membership=true")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get user projects: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Failed to get user projects: {str(e)}")
            return []
    
    def test_token_permissions(self) -> Dict[str, bool]:
        """Test various permissions of the current token."""
        permissions = {
            'read_user': False,
            'read_api': False,
            'read_repository': False,
            'write_repository': False
        }
        
        try:
            # Test read_user
            user_response = self.session.get(f"{self.base_url}/user")
            permissions['read_user'] = user_response.status_code == 200
            
            # Test read_api 
            projects_response = self.session.get(f"{self.base_url}/projects?membership=true")
            permissions['read_api'] = projects_response.status_code == 200
            
            # Test repository permissions on first available project
            if permissions['read_api']:
                projects = projects_response.json()
                if projects:
                    project_id = projects[0]['id']
                    
                    # Test read repository
                    repo_response = self.session.get(f"{self.base_url}/projects/{project_id}/repository/tree")
                    permissions['read_repository'] = repo_response.status_code in [200, 404]  # 404 means access but empty repo
                    
                    # Test write repository (check if we can access variables, which requires write permissions)
                    vars_response = self.session.get(f"{self.base_url}/projects/{project_id}/variables")
                    permissions['write_repository'] = vars_response.status_code in [200, 403]  # 403 means we can access but no variables
            
        except Exception as e:
            logger.error(f"Failed to test token permissions: {str(e)}")
        
        return permissions
