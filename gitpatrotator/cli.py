"""Command-line interface for GitPATRotator."""

import click
import logging
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

from . import __version__
from .config import ConfigManager
from .rotator import TokenRotator, TokenRotationError


# ASCII Logo for GitPATRotator
ASCII_LOGO = r"""
   _____ _ _   _____       _______   _____       _        _             
  / ____(_) | |  __ \   /\|__   __| |  __ \     | |      | |            
 | |  __ _| |_| |__) | /  \  | |    | |__) |___ | |_ __ _| |_ ___  _ __  
 | | |_ | | __|  ___/ / /\ \ | |    |  _  // _ \| __/ _` | __/ _ \| '__| 
 | |__| | | |_| |    / ____ \| |    | | \ \ (_) | || (_| | || (_) | |    
  \_____|_|\__|_|   /_/    \_\_|    |_|  \_\___/ \__\__,_|\__\___/|_|    
                                                                         
  🔐 Automated GitHub & GitLab Token Rotation with HashiCorp Vault      
"""


def display_logo():
    """Display the ASCII logo."""
    click.echo(click.style(ASCII_LOGO, fg='cyan', bold=True))


# Configure logging
def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


class GitPATRotatorGroup(click.Group):
    """Custom Click group that displays logo on help."""
    
    def get_help(self, ctx):
        """Override to display logo before help."""
        display_logo()
        return super().get_help(ctx)


def version_callback(ctx, param, value):
    """Custom version callback that displays logo."""
    if not value or ctx.resilient_parsing:
        return
    display_logo()
    click.echo(f"Version: {__version__}")
    click.echo("https://github.com/your-org/gitpatrotator")
    click.echo()
    ctx.exit()


@click.group(cls=GitPATRotatorGroup)
@click.option('--version', is_flag=True, expose_value=False, is_eager=True, 
              callback=version_callback, help='Show version and exit')
@click.option('--config', '-c', help='Path to configuration file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool):
    """GitPATRotator - Rotate GitHub/GitLab PATs stored in HashiCorp Vault."""
    setup_logging(verbose)
    
    # Store config path in context
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config
    ctx.obj['verbose'] = verbose


@cli.command()
@click.option('--name', '-n', help='Name of specific token to rotate')
@click.option('--dry-run', is_flag=True, help='Validate configuration without making changes')
@click.option('--force', '-f', is_flag=True, help='Force rotation even if not needed based on expiry')
@click.pass_context
def rotate(ctx, name: Optional[str], dry_run: bool, force: bool):
    """Rotate tokens (all or specific named token)."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        config = config_manager.load_config()
        rotator = TokenRotator(config)
        
        if name:
            # Rotate specific token
            result = rotator.rotate_token(name, dry_run, force)
            click.echo(json.dumps(result, indent=2))
        else:
            # Rotate all tokens
            results = rotator.rotate_all_tokens(dry_run, force)
            click.echo(json.dumps(results, indent=2))
            
            # Check for any failures
            failed = [r for r in results if r.get('status') == 'error']
            if failed:
                click.echo(f"\n{len(failed)} token(s) failed to rotate", err=True)
                sys.exit(1)
                
    except TokenRotationError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Check expiry status of all tokens."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        config = config_manager.load_config()
        rotator = TokenRotator(config)
        
        results = rotator.check_all_tokens_expiry()
        
        # Display results in a readable format
        click.echo("Token Status Report:")
        click.echo("=" * 60)
        
        for result in results:
            name = result['token_name']
            token_type = result['type']
            
            if result.get('status') == 'error':
                click.echo(f"❌ {name} ({token_type}): {result['message']}")
                continue
            
            # Status indicators
            if result['is_expired']:
                status_icon = "🔴"
                status_text = "EXPIRED"
            elif result['needs_rotation']:
                status_icon = "🟡"
                status_text = "NEEDS ROTATION"
            else:
                status_icon = "🟢"
                status_text = "OK"
            
            click.echo(f"{status_icon} {name} ({token_type}): {status_text}")
            click.echo(f"   Reason: {result['rotation_reason']}")
            
            if result['days_until_expiry'] is not None:
                click.echo(f"   Days until expiry: {result['days_until_expiry']}")
            
            if result['days_since_created'] is not None:
                click.echo(f"   Days since created: {result['days_since_created']}")
            
            click.echo(f"   Rotation interval: {result['rotation_interval_days']} days")
            
            if result['expires_at']:
                click.echo(f"   Expires at: {result['expires_at']}")
            
            click.echo()
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate configuration file."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        issues = config_manager.validate_config()
        
        if not issues:
            click.echo("✓ Configuration is valid")
        else:
            click.echo("Configuration issues found:")
            for issue in issues:
                click.echo(f"  ✗ {issue}")
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def list(ctx):
    """List configured tokens."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        config = config_manager.load_config()
        
        click.echo("Configured tokens:")
        for token in config.tokens:
            click.echo(f"  - {token.name} ({token.type})")
            click.echo(f"    Username: {token.username}")
            click.echo(f"    Vault Path: {token.vault_path}")
            click.echo(f"    Rotation Interval: {token.rotation_interval_days} days")
            if token.max_age_days:
                click.echo(f"    Max Age: {token.max_age_days} days")
            if token.type == 'gitlab':
                click.echo(f"    GitLab URL: {token.gitlab_url}")
            if token.scopes:
                click.echo(f"    Scopes: {', '.join(token.scopes)}")
            click.echo()
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--name', '-n', required=True, help='Name of token to update')
@click.option('--token', '-t', required=True, help='New token value')
@click.pass_context
def update_token(ctx, name: str, token: str):
    """Manually update a token in Vault."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        config = config_manager.load_config()
        rotator = TokenRotator(config)
        
        result = rotator.update_token_manually(name, token)
        click.echo(json.dumps(result, indent=2))
        
    except TokenRotationError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _display_token_test_result(token_name: str, result: Dict[str, Any]) -> None:
    """Display the result of a token test."""
    click.echo(f"Testing token: {token_name}")
    if result.get('current_token_valid'):
        click.echo("  ✓ Token is valid")
        user = result.get('user')
        if user:
            click.echo(f"  ✓ User: {user}")
        perms = result.get('permissions', {})
        for perm, status in perms.items():
            status_icon = "✓" if status else "✗"
            click.echo(f"  {status_icon} {perm}")
    else:
        click.echo("  ✗ Token is invalid")
    click.echo()


def _test_single_token(rotator: 'TokenRotator', token_name: str) -> None:
    """Test a single token and display results."""
    try:
        result = rotator.rotate_token(token_name, dry_run=True)
        _display_token_test_result(token_name, result)
    except Exception as e:
        click.echo(f"Testing token: {token_name}")
        click.echo(f"  ✗ Error testing token: {str(e)}")
        click.echo()


@cli.command()
@click.option('--name', '-n', help='Name of specific token to test')
@click.pass_context
def test(ctx, name: Optional[str]):
    """Test token connectivity and permissions."""
    try:
        config_manager = ConfigManager(ctx.obj['config_path'])
        config = config_manager.load_config()
        rotator = TokenRotator(config)
        
        tokens_to_test = [name] if name else [t.name for t in config.tokens]
        
        for token_name in tokens_to_test:
            _test_single_token(rotator, token_name)
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--sample', is_flag=True, help='Create sample configuration file')
@click.pass_context
def init(ctx, sample: bool):
    """Initialize configuration file."""
    config_path = ctx.obj['config_path'] or 'config.yaml'
    
    if Path(config_path).exists():
        click.echo(f"Configuration file already exists: {config_path}")
        if not click.confirm("Overwrite?"):
            return
    
    sample_config = """vault:
  url: "https://vault.example.com"
  token: "your-vault-token"  # or use VAULT_TOKEN env var
  namespace: "your-namespace"  # Optional: Vault namespace (Enterprise)
  mount_path: "secret"

tokens:
  # GitHub App Installation Token (fully automated rotation)
  - name: "github-app-myorg"
    type: "github-app"
    vault_path: "tokens/github/app-installation"
    username: "myorg"  # Organization or user that installed the app
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/github-app-private-key.pem"
      installation_id: "12345678"
      permissions:
        contents: "read"
        metadata: "read"
        pull_requests: "write"
        issues: "write"
    rotation_interval_days: 1  # GitHub App tokens expire in 1 hour, rotate daily
    max_age_days: 1

  # GitLab Personal Access Token (fully automated rotation)
  - name: "gitlab-prod"
    type: "gitlab"
    vault_path: "tokens/gitlab/prod"
    gitlab_url: "https://gitlab.example.com"
    username: "your-gitlab-username"
    rotation_interval_days: 15  # Rotate 15 days before expiry
    max_age_days: 60           # Force rotation after 60 days
    scopes:
      - "api"
      - "read_user"
      - "read_repository"
      - "write_repository"
"""
    
    with open(config_path, 'w') as f:
        f.write(sample_config)
    
    click.echo(f"Created configuration file: {config_path}")
    click.echo("Please edit the file with your specific settings.")
    click.echo("\nNext steps:")
    click.echo("1. Configure your Vault connection details")
    click.echo("2. Set up GitHub App for automated token rotation")
    click.echo("3. Configure GitLab API access")
    click.echo("4. Run: gitpatrotator validate")
    click.echo("5. Check token status: gitpatrotator status")


if __name__ == '__main__':
    cli()
