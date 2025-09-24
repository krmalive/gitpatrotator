# GitPATRotator CLI Installation Guide

## Step 1: Installation

```bash
# Clone or download the GitPATRotator project
cd gitpatrotator

# Install dependencies
pip install -r requirements.txt

# Install GitPATRotator as a CLI tool
pip install -e .
```LI Installation Guide

## Installation

```bash
# Clone or download the GitPATRotator project
cd gitpatrotator

# Install dependencies
pip install -r requirements.txt

# Install GitPATRotator as a CLI tool
pip install -e .
```

## Verification

After installation, verify that the CLI is working:

```bash
gitpatrotator --version
gitpatrotator --help
```

## Getting Started

1. **Create configuration file:**
   ```bash
   gitpatrotator init --sample
   ```

2. **Edit the `config.yaml` file** with your Vault and token settings

3. **Validate configuration:**
   ```bash
   gitpatrotator validate
   ```

4. **Check token status:**
   ```bash
   gitpatrotator status
   ```

5. **Rotate tokens (dry run first):**
   ```bash
   gitpatrotator rotate --dry-run
   gitpatrotator rotate
   ```

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `gitpatrotator status` | Check expiry status of all tokens |
| `gitpatrotator rotate` | Rotate tokens that need rotation |
| `gitpatrotator rotate --force` | Force rotate all tokens |
| `gitpatrotator rotate --name <token>` | Rotate specific token |
| `gitpatrotator rotate --dry-run` | Test without making changes |
| `gitpatrotator list` | List configured tokens |
| `gitpatrotator validate` | Validate configuration |
| `gitpatrotator update-token --name <name> --token <token>` | Manually update a GitLab token only |
| `gitpatrotator init --sample` | Create sample configuration |

## Troubleshooting

### Command not found
If `gitpatrotator` command is not found after installation:

1. **Check if it's installed:**
   ```bash
   pip list | grep gitpatrotator
   ```

2. **Use alternative syntax:**
   ```bash
   python -m gitpatrotator <command>
   ```

3. **Reinstall:**
   ```bash
   pip uninstall gitpatrotator
   pip install -e .
   ```

### Path Issues on Windows
If you're on Windows and the command isn't found, make sure Python Scripts directory is in your PATH:
- `C:\Users\<username>\AppData\Local\Programs\Python\Python3x\Scripts\`

## Configuration Example

```yaml
vault:
  url: "https://vault.example.com"
  token: "your-vault-token"
  namespace: "your-namespace"  # Optional: for Vault Enterprise
  mount_path: "secret"

tokens:
  # GitHub App (fully automated)
  - name: "github-app-prod"
    type: "github-app"
    vault_path: "tokens/github/app-prod"
    username: "myorg"
    github_app:
      app_id: "123456"
      private_key_path: "/path/to/private-key.pem"
      installation_id: "12345678"
    rotation_interval_days: 1

  # GitLab (fully automated)
  - name: "gitlab-prod" 
    type: "gitlab"
    vault_path: "tokens/gitlab/prod"
    gitlab_url: "https://gitlab.example.com"
    username: "your-username"
    rotation_interval_days: 15
    max_age_days: 60
```

## Environment Variables

- `VAULT_TOKEN`: Override vault token from config
- `VAULT_ADDR`: Override vault URL from config
- `VAULT_NAMESPACE`: Override vault namespace from config (Vault Enterprise)

## Vault Enterprise Configuration

If you're using Vault Enterprise with namespaces, you can configure the namespace in multiple ways:

1. **In configuration file:**
   ```yaml
   vault:
     namespace: "team-a"
   ```

2. **Via environment variable:**
   ```bash
   export VAULT_NAMESPACE="team-a"
   ```

3. **Leave empty for Vault OSS:**
   ```yaml
   vault:
     # No namespace field needed for Vault OSS
   ```

## Support

For issues or questions:
1. Check the configuration with `gitpatrotator validate`
2. Run with verbose logging: `gitpatrotator -v <command>`
3. Review the README.md for detailed documentation
