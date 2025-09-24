# GitPATRotator

A cross-platform Python application for automatically rotating GitLab and GitHub tokens stored in HashiCorp Vault with **100% automation** - no manual intervention required!

## Features

- **100% Automated Rotation**: Complete automation for both GitHub (via Apps) and GitLab tokens
- **🎨 Professional CLI Interface**: Beautiful ASCII logo and colorized output
- **GitHub Apps Integration**: Fully automated GitHub token rotation using GitHub Apps
- **⚙️ Configurable Token Validity**: Default 30-day validity with customizable periods
- **🕒 Smart Expiry Detection**: Enhanced datetime parsing with timezone support
- **Smart Expiry-Based Rotation**: Automatically rotates tokens before they expire based on configurable intervals
- **Multiple Rotation Triggers**: Support for expiry-based rotation and maximum age limits
- **🏛️ Vault Enterprise Support**: Namespace support and SSL bypass for corporate environments
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Secure Storage**: Uses HashiCorp Vault KV store for token management
- **🔄 Conflict-Free Storage**: Separate Vault paths prevent token ID conflicts
- **Dry Run Mode**: Test rotation logic without making changes
- **Complete API Integration**: Full automation for both GitHub Apps and GitLab token management

## Installation

```bash
# Install GitPATRotator directly from source
pip install -e .
```

After installation, you can use `gitpatrotator` directly as a command-line tool with a beautiful ASCII logo.

📖 **For detailed installation instructions, configuration examples, and troubleshooting**, see [INSTALL.md](INSTALL.md)

## Configuration

GitPATRotator supports **configurable token validity periods** with a default of 30 days for new tokens.

Create a `config.yaml` file:

```yaml
vault:
  url: "https://vault.example.com"
  token: "your-vault-token"  # or use VAULT_TOKEN env var
  namespace: "your-namespace"  # Optional: Vault namespace (Enterprise)
  mount_path: "secret"
  verify_ssl: true  # Set to false for self-signed certificates

tokens:
  # GitHub App (fully automated)
  - name: "github-app-prod"
    type: "github-app"
    vault_path: "tokens/github/app-prod"
    username: "myorg"
    token_field: "gh-pat"  # Custom field name in Vault
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/private-key.pem"
      installation_id: "12345678"
      permissions:
        metadata: "read"  # Start with minimal permissions
    rotation_interval_days: 1   # GitHub App tokens expire in 1 hour
    max_age_days: 1
    
  # GitLab (fully automated)  
  - name: "gitlab-prod"
    type: "gitlab"
    vault_path: "tokens/gitlab/prod"
    gitlab_url: "https://gitlab.example.com"
    username: "your-username"
    token_field: "gl-pat"      # Custom field name in Vault
    rotation_interval_days: 15  # Rotate 15 days before expiry
    max_age_days: 60           # Force rotation after 60 days
    token_validity_days: 90    # New tokens valid for 90 days (optional, defaults to 30)
    scopes:
      - "api"
      - "read_user"
      - "read_repository"
      - "write_repository"
```

📖 **For complete configuration examples with enterprise Vault settings**, see [config.example.yaml](config.example.yaml)

### GitHub App Setup

For fully automated GitHub token rotation, you need to create a GitHub App:

1. **Create GitHub App**:
   - Go to GitHub Settings → Developer Settings → GitHub Apps → New
   - Set **Permissions** (start minimal, expand as needed):
     - Repository permissions: `Metadata: Read`
     - Add more permissions later: `Contents: Read`, `Pull requests: Write`, etc.

2. **Install the App**:
   - Install on your organization/repositories
   - Note the **Installation ID** from the URL: `https://github.com/settings/installations/{INSTALLATION_ID}`

3. **Generate Private Key**:
   - In your GitHub App settings, generate and download the private key (.pem file)
   - Store securely and reference the path in your configuration

4. **Configure GitPATRotator**:
   ```yaml
   github_app:
     app_id: "123456"                    # From GitHub App settings
     private_key_path: "/path/to/key.pem" # Downloaded private key
     installation_id: "12345678"        # From installation URL
     permissions:
       metadata: "read"                  # Start minimal
   ```

5. **Best Practices**:
   - Use separate Vault paths for different token types (prevent conflicts)
   - Start with minimal permissions, expand incrementally
   - Rotate daily due to GitHub's 1-hour token expiry

### Rotation Logic

Tokens are rotated when:
1. **Expiry-based**: Token expires within `rotation_interval_days`
2. **Age-based**: Token is older than `max_age_days` (optional)
3. **Force**: Manual force rotation regardless of expiry

## Usage

```bash
# Check version and see ASCII logo
gitpatrotator --version

# Show help with logo
gitpatrotator --help

# Check token expiry status
gitpatrotator status

# Rotate tokens that need rotation (based on expiry)
gitpatrotator rotate

# Force rotate all tokens regardless of expiry
gitpatrotator rotate --force

# Rotate specific token
gitpatrotator rotate --name github-app-prod

# Dry run (check what would be rotated)
gitpatrotator rotate --dry-run

# Test token connectivity and permissions
gitpatrotator test

# List configured tokens
gitpatrotator list

# Validate configuration
gitpatrotator validate

# Initialize sample configuration
gitpatrotator init --sample

# Manually update a GitLab token only (GitHub App tokens auto-generate)
gitpatrotator update-token --name gitlab-prod --token glpat-xxx
```

### Alternative Usage (if not installed as CLI)

If you prefer not to install the package, you can still use it with:
```bash
python -m gitpatrotator <command>
```

## Environment Variables

- `VAULT_TOKEN`: HashiCorp Vault authentication token
- `VAULT_ADDR`: Vault server URL (overrides config)
- `VAULT_NAMESPACE`: Vault namespace (for Vault Enterprise)
- `GITLAB_TOKEN`: GitLab token for API access (temporary during rotation)

## Troubleshooting

### Installation Issues

#### Linux Installation Problems

If you encounter this error on Linux systems:
```
ERROR: File "setup.py" not found. Directory cannot be installed in editable mode
(A "pyproject.toml" file was found, but editable mode currently requires a setup.py based build.)
```

This happens on older Linux systems with outdated pip versions. **Solution**:

```bash
# 1. Upgrade pip to latest version
pip install --upgrade pip

# 2. Add pip's local bin directory to PATH (if pip was installed to ~/.local/bin)
export PATH="$HOME/.local/bin:$PATH"

# 3. Install modern build tools
pip install build

# 4. Now install GitPATRotator
pip install -e .
```

**Note**: The warning about `~/.local/bin` not being on PATH is normal. Adding it to PATH ensures you use the upgraded pip version.

To make the PATH change permanent, add this line to your `~/.bashrc` or `~/.profile`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### GitHub App Issues
- **Installation ID**: Find it in the URL after installing: `github.com/settings/installations/{ID}`
- **Permissions**: Start with `metadata: read`, add more permissions incrementally
- **Private Key**: Ensure the .pem file path is accessible and properly formatted
- **Token Conflicts**: Use separate `vault_path` for different token types

### Vault Issues
- **SSL Certificates**: Set `verify_ssl: false` for self-signed certificates
- **Namespaces**: Use `namespace` field for Vault Enterprise environments
- **Token Fields**: Use unique `token_field` names (e.g., `gh-pat`, `gl-pat`) to prevent conflicts

### Common Errors
- `Token not found in Vault`: Check `vault_path` and `token_field` configuration
- `GitHub App authentication failed`: Verify `app_id`, `installation_id`, and private key path
- `GitLab API errors`: Ensure token has required scopes and GitLab URL is correct

## Automation Guide

For **production deployment and enterprise configuration**, GitPATRotator includes:

- 🏢 **Vault Enterprise Support**: Namespace configuration and SSL bypass
- 🔐 **GitHub App Integration**: Minimal permissions and automatic installation ID discovery  
- 🚀 **Token Separation**: Best practices for conflict-free Vault storage
- 📋 **Production Examples**: Complete configuration templates in [config.example.yaml](config.example.yaml)
- ⚡ **Enhanced Performance**: Refactored codebase with reduced cognitive complexity

The configuration examples include real-world patterns for:
- Corporate Vault environments with self-signed certificates
- Multiple token types with separate storage paths
- GitHub App permissions and installation setup
- GitLab token lifecycle management