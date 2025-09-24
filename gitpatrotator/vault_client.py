"""HashiCorp Vault client for managing secrets."""

import hvac
import logging
import urllib3
from typing import Dict, Any, Optional
from .config import VaultConfig

# Disable SSL warnings when verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class VaultClient:
    """HashiCorp Vault client for secret management."""
    
    def __init__(self, config: VaultConfig):
        self.config = config
        
        # Configure SSL verification
        verify_ssl = config.verify_ssl
        if config.ca_bundle:
            verify_ssl = config.ca_bundle
            
        logger.debug(f"Vault client SSL config - verify_ssl: {config.verify_ssl}, ca_bundle: {config.ca_bundle}, final verify: {verify_ssl}")
        
        self.client = hvac.Client(
            url=config.url,
            token=config.token,
            timeout=config.timeout,
            verify=verify_ssl
        )
        
        # Set namespace if provided (Vault Enterprise feature)
        if config.namespace:
            self.client.namespace = config.namespace
            # Also set namespace header on the session
            self.client.session.headers['X-Vault-Namespace'] = config.namespace
            logger.info(f"Using Vault namespace: {config.namespace}")
            logger.debug("Set namespace header on session")
        
        # Log SSL configuration
        if not config.verify_ssl:
            logger.warning("SSL certificate verification is DISABLED - this is insecure!")
        elif config.ca_bundle:
            logger.info(f"Using custom CA bundle: {config.ca_bundle}")
        
        logger.info(f"Successfully connected to Vault at {config.url}")
        
        # Verify connection and authentication
        if not self.client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        logger.info(f"Successfully connected to Vault at {config.url}")
    
    def _extract_secret_data_from_response(self, response, kv_version: str) -> Optional[Dict[str, Any]]:
        """Extract secret data from Vault response based on KV version."""
        if hasattr(response, 'json'):
            # Response is a requests.Response object
            data = response.json()
            logger.debug(f"Successfully read secret data structure: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            return data['data']['data'] if kv_version == 'v2' else data['data']
        elif isinstance(response, dict):
            # Response is already a dictionary
            logger.debug(f"Successfully read secret data structure: {list(response.keys())}")
            return response['data']['data'] if kv_version == 'v2' else response['data']
        else:
            logger.error(f"Unexpected response type: {type(response)}")
            return None
    
    def _try_kv_v2_read(self, path: str) -> Optional[Dict[str, Any]]:
        """Try to read secret using KV v2 engine."""
        logger.debug(f"Attempting to read secret from path: {path}")
        logger.debug(f"Mount point: {self.config.mount_path}")
        logger.debug(f"Namespace: {self.config.namespace}")
        logger.debug(f"Full URL would be: {self.client.url}/v1/{self.config.namespace}/{self.config.mount_path}/data/{path}" if self.config.namespace else f"{self.client.url}/v1/{self.config.mount_path}/data/{path}")
        
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path,
            mount_point=self.config.mount_path
        )
        
        return self._extract_secret_data_from_response(response, 'v2')
    
    def _try_kv_v1_read(self, path: str) -> Optional[Dict[str, Any]]:
        """Try to read secret using KV v1 engine as fallback."""
        logger.debug(f"KV v2 failed, trying KV v1 for path: {path}")
        logger.debug(f"KV v1 full URL would be: {self.client.url}/v1/{self.config.namespace}/{self.config.mount_path}/{path}" if self.config.namespace else f"{self.client.url}/v1/{self.config.mount_path}/{path}")
        
        response = self.client.secrets.kv.v1.read_secret(
            path=path,
            mount_point=self.config.mount_path
        )
        
        return self._extract_secret_data_from_response(response, 'v1')
    
    def read_secret(self, path: str) -> Optional[Dict[str, Any]]:
        """Read a secret from Vault KV store."""
        try:
            # Try KV v2 first
            return self._try_kv_v2_read(path)
                
        except hvac.exceptions.InvalidPath:
            try:
                # Fall back to KV v1
                return self._try_kv_v1_read(path)
                    
            except hvac.exceptions.InvalidPath:
                logger.warning(f"Secret not found at path: {path}")
                return None
        except Exception as e:
            logger.error(f"Failed to read secret from {path}: {str(e)}")
            raise
    
    def write_secret(self, path: str, secret: Dict[str, Any]) -> None:
        """Write a secret to Vault KV store."""
        try:
            # Try KV v2 first
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=secret,
                mount_point=self.config.mount_path
            )
            logger.info(f"Successfully wrote secret to {path}")
        except hvac.exceptions.InvalidRequest:
            try:
                # Fall back to KV v1
                self.client.secrets.kv.v1.create_or_update_secret(
                    path=path,
                    secret=secret,
                    mount_point=self.config.mount_path
                )
                logger.info(f"Successfully wrote secret to {path} (KV v1)")
            except Exception as e:
                logger.error(f"Failed to write secret to {path}: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Failed to write secret to {path}: {str(e)}")
            raise
    
    def get_token_data(self, path: str, token_field: str = "token") -> Optional[Dict[str, str]]:
        """Get token data from Vault, expecting specified token field and optional 'username' fields."""
        secret = self.read_secret(path)
        if not secret:
            return None
        
        logger.debug(f"Secret data keys found: {list(secret.keys()) if secret else 'None'}")
        logger.debug(f"Looking for token field: {token_field}")
        logger.debug(f"Secret data values (first 200 chars): {str(secret)[:200] if secret else 'None'}")
            
        if token_field not in secret:
            logger.error(f"Secret at {path} missing required '{token_field}' field. Available fields: {list(secret.keys()) if secret else 'None'}")
            raise ValueError(f"Secret at {path} missing required '{token_field}' field")
        
        return {
            'token': secret[token_field],  # Always return as 'token' regardless of source field name
            'username': secret.get('username', ''),
            'created_at': secret.get('created_at', ''),
            'last_rotated': secret.get('last_rotated', ''),
            'token_id': secret.get('token_id', '')
        }
    
    def store_token_data(self, path: str, token: str, token_field: str = "token", token_id: str = None) -> None:
        """Store token data in Vault, preserving existing secret data but adding only the token field."""
        
        # First, read existing secret data to preserve other fields
        existing_data = self.read_secret(path) or {}
        logger.debug(f"Existing secret data keys: {list(existing_data.keys()) if existing_data else 'None'}")
        
        # Update only the token field - preserve everything else
        data = existing_data.copy()  # Preserve all existing fields
        data[token_field] = token
        
        # Store token ID for cleanup purposes if provided
        if token_id:
            data['token_id'] = token_id
        
        logger.info(f"Updating secret with token field '{token_field}' while preserving {len(existing_data)} existing fields (minimal mode)")
        self.write_secret(path, data)