"""Tests for configuration management."""

import pytest
import tempfile
import os
from pathlib import Path

from gitpatrotator.config import ConfigManager, VaultConfig, TokenConfig, Config


class TestConfigManager:
    """Test configuration management functionality."""
    
    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        config_content = """
vault:
  url: "https://vault.example.com"
  token: "test-token"
  mount_path: "secret"

tokens:
  - name: "test-github-app"
    type: "github-app"
    vault_path: "tokens/github/app"
    username: "testorg"
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/key.pem"
      installation_id: "12345678"
  - name: "test-gitlab"
    type: "gitlab"
    vault_path: "tokens/gitlab/test"
    username: "testuser"
    gitlab_url: "https://gitlab.example.com"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            
            try:
                manager = ConfigManager(f.name)
                config = manager.load_config()
                
                assert config.vault.url == "https://vault.example.com"
                assert config.vault.token == "test-token"
                assert config.vault.mount_path == "secret"
                assert len(config.tokens) == 2
                
                github_token = config.tokens[0]
                assert github_token.name == "test-github-app"
                assert github_token.type == "github-app"
                assert github_token.username == "testorg"
                
                gitlab_token = config.tokens[1]
                assert gitlab_token.name == "test-gitlab"
                assert gitlab_token.type == "gitlab"
                assert gitlab_token.gitlab_url == "https://gitlab.example.com"
                
            finally:
                try:
                    os.unlink(f.name)
                except PermissionError:
                    pass  # Windows file locking issue

    def test_config_validation(self):
        """Test configuration validation."""
        config_content = """
vault:
  url: "invalid-url"
  token: "test-token"

tokens:
  - name: "test-github"
    type: "invalid-type"
    vault_path: ""
    username: "testuser"
  - name: "test-gitlab"
    type: "gitlab"
    vault_path: "tokens/gitlab/test"
    username: "testuser"
    # missing gitlab_url
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            
            try:
                manager = ConfigManager(f.name)
                issues = manager.validate_config()
                
                assert len(issues) > 0
                # Check for the actual validation error we get
                assert any("gitlab_url" in issue for issue in issues)
                
            finally:
                try:
                    os.unlink(f.name)
                except PermissionError:
                    pass  # Windows file locking issue
    
    def test_environment_variable_override(self):
        """Test environment variable override for vault settings."""
        config_content = """
vault:
  url: "https://vault.example.com"
  # token intentionally missing

tokens:
  - name: "test-github-app"
    type: "github-app"
    vault_path: "tokens/github/app"
    username: "testorg"
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/key.pem"
      installation_id: "12345678"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            
            try:
                # Set environment variables
                os.environ['VAULT_TOKEN'] = 'env-token'
                os.environ['VAULT_ADDR'] = 'https://vault-env.example.com'
                
                manager = ConfigManager(f.name)
                config = manager.load_config()
                
                assert config.vault.token == 'env-token'
                # URL from config should take precedence when both are set
                assert config.vault.url == 'https://vault.example.com'
                
            finally:
                try:
                    os.unlink(f.name)
                except PermissionError:
                    pass  # Windows file locking issue
                # Clean up environment variables
                os.environ.pop('VAULT_TOKEN', None)
                os.environ.pop('VAULT_ADDR', None)
    
    def test_get_token_config(self):
        """Test getting specific token configuration."""
        config_content = """
vault:
  url: "https://vault.example.com"
  token: "test-token"

tokens:
  - name: "github-app-main"
    type: "github-app"
    vault_path: "tokens/github/app-main"
    username: "testorg"
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/key.pem"
      installation_id: "12345678"
  - name: "gitlab-prod"
    type: "gitlab"
    vault_path: "tokens/gitlab/prod"
    username: "testuser"
    gitlab_url: "https://gitlab.example.com"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            
            try:
                manager = ConfigManager(f.name)
                
                github_config = manager.get_token_config("github-app-main")
                assert github_config is not None
                assert github_config.name == "github-app-main"
                assert github_config.type == "github-app"
                
                gitlab_config = manager.get_token_config("gitlab-prod")
                assert gitlab_config is not None
                assert gitlab_config.name == "gitlab-prod"
                assert gitlab_config.type == "gitlab"
                
                nonexistent = manager.get_token_config("nonexistent")
                assert nonexistent is None
                
            finally:
                try:
                    os.unlink(f.name)
                except PermissionError:
                    pass  # Windows file locking issue
