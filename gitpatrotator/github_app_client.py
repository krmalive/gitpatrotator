"""GitHub App client for automated token management."""

import time
import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization

try:
    import jwt
except ImportError:
    jwt = None
    import sys
    print("Warning: PyJWT library not found. Install it with: pip install PyJWT>=2.0.0", file=sys.stderr)

logger = logging.getLogger(__name__)

# Constants
GITHUB_API_VERSION = "application/vnd.github.v3+json"


class GitHubAppClient:
    """GitHub App client for managing installation tokens."""
    
    def __init__(self, app_id: str, private_key: str, installation_id: str):
        """Initialize GitHub App client.
        
        Args:
            app_id: GitHub App ID
            private_key: Private key content (PEM format)
            installation_id: Installation ID for the target organization/user
        """
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": GITHUB_API_VERSION,
            "User-Agent": "GitPATRotator-App/1.0"
        })
    
    def _generate_jwt_token(self) -> str:
        """Generate JWT token for GitHub App authentication."""
        if jwt is None:
            raise ImportError("PyJWT library is required for GitHub App authentication. Install with: pip install PyJWT>=2.0.0")
        
        # Load private key
        private_key_obj = serialization.load_pem_private_key(
            self.private_key.encode(),
            password=None
        )
        
        # JWT payload
        now = int(time.time())
        payload = {
            'iat': now - 60,  # Issued at time (60 seconds ago to account for clock skew)
            'exp': now + (10 * 60),  # Expires in 10 minutes (max allowed)
            'iss': self.app_id  # Issuer (App ID)
        }
        
        # Generate JWT
        token = jwt.encode(payload, private_key_obj, algorithm='RS256')
        return token
    
    def get_installation_token(self, permissions: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Get an installation access token.
        
        Args:
            permissions: Optional permissions to request (e.g., {"contents": "read", "metadata": "read"})
            
        Returns:
            Token data with 'token', 'expires_at', etc.
        """
        try:
            # Generate JWT for app authentication
            jwt_token = self._generate_jwt_token()
            
            # Set up headers with JWT
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": GITHUB_API_VERSION
            }
            
            # Prepare request data
            data = {}
            if permissions:
                data['permissions'] = permissions
            
            # Request installation token
            url = f"{self.base_url}/app/installations/{self.installation_id}/access_tokens"
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 201:
                token_data = response.json()
                logger.info(f"Successfully created installation token, expires at: {token_data.get('expires_at')}")
                return token_data
            else:
                logger.error(f"Failed to get installation token: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate installation token: {str(e)}")
            return None
    
    def test_installation_token(self, token: str) -> bool:
        """Test if an installation token is valid."""
        try:
            headers = {
                "Authorization": f"token {token}",
                "Accept": GITHUB_API_VERSION
            }
            
            response = requests.get(f"{self.base_url}/installation/repositories", headers=headers)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to test installation token: {str(e)}")
            return False
    
    def get_app_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the GitHub App."""
        try:
            jwt_token = self._generate_jwt_token()
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": GITHUB_API_VERSION
            }
            
            response = requests.get(f"{self.base_url}/app", headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get app info: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get app info: {str(e)}")
            return None
