"""Configuration management for GitPATRotator."""

import os
import yaml
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VaultConfig:
    """Vault configuration settings."""
    url: str
    token: Optional[str] = None
    mount_path: str = "secret"
    namespace: Optional[str] = None  # Vault namespace (for Vault Enterprise)
    timeout: int = 30
    verify_ssl: bool = True  # Set to False to disable SSL verification
    ca_bundle: Optional[str] = None  # Path to CA bundle file


@dataclass
class GitHubAppConfig:
    """GitHub App configuration for automated token rotation."""
    app_id: str
    private_key_path: str  # Path to private key file
    installation_id: str
    permissions: Optional[Dict[str, str]] = None  # e.g., {"contents": "read", "metadata": "read"}


@dataclass
class TokenConfig:
    """Token configuration for rotation."""
    name: str
    type: str  # 'github', 'gitlab', or 'github-app'
    vault_path: str
    username: str
    gitlab_url: Optional[str] = None  # Required for GitLab tokens
    github_app: Optional[GitHubAppConfig] = None  # Required for GitHub App tokens
    scopes: Optional[List[str]] = None
    rotation_interval_days: int = 30  # Days before expiry to rotate
    max_age_days: Optional[int] = None  # Maximum age before forced rotation
    token_field: str = "token"  # Name of the field containing the token in Vault
    token_validity_days: int = 30  # Days the new token remains valid (default: 30)


@dataclass
class Config:
    """Main configuration class."""
    vault: VaultConfig
    tokens: List[TokenConfig]


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self._config: Optional[Config] = None
    
    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        possible_paths = [
            "config.yaml",
            "config.yml", 
            os.path.expanduser("~/.gitpatrotator/config.yaml"),
            os.path.expanduser("~/.config/gitpatrotator/config.yaml"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Return default path if none found
        return "config.yaml"
    
    def load_config(self) -> Config:
        """Load configuration from file."""
        if self._config:
            return self._config
            
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Parse vault config
        vault_data = data.get('vault', {})
        vault_config = VaultConfig(
            url=vault_data.get('url') or os.getenv('VAULT_ADDR'),
            token=vault_data.get('token') or os.getenv('VAULT_TOKEN'),
            mount_path=vault_data.get('mount_path', 'secret'),
            namespace=vault_data.get('namespace'),
            timeout=vault_data.get('timeout', 30),
            verify_ssl=vault_data.get('verify_ssl', True),
            ca_bundle=vault_data.get('ca_bundle')
        )
        
        if not vault_config.url:
            raise ValueError("Vault URL must be specified in config or VAULT_ADDR environment variable")
        
        if not vault_config.token:
            raise ValueError("Vault token must be specified in config or VAULT_TOKEN environment variable")
        
        # Parse token configs
        tokens_data = data.get('tokens', [])
        tokens = []
        
        for token_data in tokens_data:
            # Parse GitHub App config if present
            github_app_config = None
            if token_data.get('github_app'):
                app_data = token_data['github_app']
                github_app_config = GitHubAppConfig(
                    app_id=app_data['app_id'],
                    private_key_path=app_data['private_key_path'],
                    installation_id=app_data['installation_id'],
                    permissions=app_data.get('permissions')
                )
            
            token_config = TokenConfig(
                name=token_data['name'],
                type=token_data['type'],
                vault_path=token_data['vault_path'],
                username=token_data['username'],
                gitlab_url=token_data.get('gitlab_url'),
                github_app=github_app_config,
                scopes=token_data.get('scopes'),
                rotation_interval_days=token_data.get('rotation_interval_days', 30),
                max_age_days=token_data.get('max_age_days'),
                token_field=token_data.get('token_field', 'token'),
                token_validity_days=token_data.get('token_validity_days', 30)
            )
            
            # Validate GitLab tokens have URL
            if token_config.type == 'gitlab' and not token_config.gitlab_url:
                raise ValueError(f"GitLab tokens require 'gitlab_url' field: {token_config.name}")
            
            # Validate GitHub App tokens have app config
            if token_config.type == 'github-app' and not token_config.github_app:
                raise ValueError(f"GitHub App tokens require 'github_app' configuration: {token_config.name}")
            
            tokens.append(token_config)
        
        self._config = Config(vault=vault_config, tokens=tokens)
        return self._config
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        try:
            config = self.load_config()
        except Exception as e:
            return [f"Failed to load config: {str(e)}"]
        
        # Validate vault config
        issues.extend(self._validate_vault_config(config.vault))
        
        # Validate token configs
        issues.extend(self._validate_token_configs(config.tokens))
        
        return issues
    
    def _validate_vault_config(self, vault_config: VaultConfig) -> List[str]:
        """Validate vault configuration."""
        issues = []
        if not vault_config.url.startswith(('http://', 'https://')):
            issues.append("Vault URL must start with http:// or https://")
        return issues
    
    def _validate_token_configs(self, tokens: List[TokenConfig]) -> List[str]:
        """Validate token configurations."""
        issues = []
        token_names = set()
        
        for token in tokens:
            issues.extend(self._validate_single_token(token, token_names))
        
        return issues
    
    def _validate_single_token(self, token: TokenConfig, token_names: set) -> List[str]:
        """Validate a single token configuration."""
        issues = []
        
        # Check for duplicate names
        if token.name in token_names:
            issues.append(f"Duplicate token name: {token.name}")
        token_names.add(token.name)
        
        # Validate token type
        if token.type not in ['gitlab', 'github-app']:
            issues.append(f"Invalid token type '{token.type}' for token '{token.name}'. Must be 'gitlab' or 'github-app'")
        
        # Validate required fields
        issues.extend(self._validate_token_required_fields(token))
        
        # Validate numeric fields
        issues.extend(self._validate_token_numeric_fields(token))
        
        return issues
    
    def _validate_token_required_fields(self, token: TokenConfig) -> List[str]:
        """Validate required fields for a token."""
        issues = []
        
        if not token.vault_path:
            issues.append(f"Token '{token.name}' missing vault_path")
        
        if not token.username:
            issues.append(f"Token '{token.name}' missing username")
        
        # Validate type-specific fields
        if token.type == 'github-app':
            issues.extend(self._validate_github_app_fields(token))
        
        return issues
    
    def _validate_github_app_fields(self, token: TokenConfig) -> List[str]:
        """Validate GitHub App specific fields."""
        issues = []
        
        if not token.github_app:
            issues.append(f"GitHub App token '{token.name}' missing github_app configuration")
            return issues
        
        # Validate required GitHub App fields
        required_fields = [
            ('app_id', 'app_id'),
            ('private_key_path', 'private_key_path'),
            ('installation_id', 'installation_id')
        ]
        
        for field_name, config_name in required_fields:
            if not getattr(token.github_app, field_name):
                issues.append(f"GitHub App token '{token.name}' missing {config_name}")
        
        # Validate private key file exists
        if token.github_app.private_key_path and not os.path.exists(token.github_app.private_key_path):
            issues.append(f"GitHub App token '{token.name}' private key file not found: {token.github_app.private_key_path}")
        
        return issues
    
    def _validate_token_numeric_fields(self, token: TokenConfig) -> List[str]:
        """Validate numeric fields for a token."""
        issues = []
        
        if token.rotation_interval_days <= 0:
            issues.append(f"Token '{token.name}' rotation_interval_days must be positive")
        
        if token.max_age_days is not None and token.max_age_days <= 0:
            issues.append(f"Token '{token.name}' max_age_days must be positive")
        
        if token.token_validity_days <= 0:
            issues.append(f"Token '{token.name}' token_validity_days must be positive")
        
        return issues
    
    def get_token_config(self, name: str) -> Optional[TokenConfig]:
        """Get token configuration by name."""
        config = self.load_config()
        for token in config.tokens:
            if token.name == name:
                return token
        return None
    
    def list_token_names(self) -> List[str]:
        """Get list of configured token names."""
        config = self.load_config()
        return [token.name for token in config.tokens]
