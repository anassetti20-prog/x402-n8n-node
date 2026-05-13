#!/bin/bash
# GitHub Repository Setup Script
# Run this when you have a working GitHub token with 'repo' scope
# 1. Go to https://github.com/settings/tokens
# 2. Generate a new classic PAT with 'repo' scope
# 3. Run: export GITHUB_TOKEN=ghp_xxx
# 4. Run this script

cd /root/x402-api

echo "=== Setting up GitHub Repository ==="

# Configure git
git config user.name "Anas Setti"
git config user.email "anassetti20-prog@users.noreply.github.com"

# Create .gitignore
cat > .gitignore << 'IGNORE'
__pycache__/
*.pyc
venv/
.env
.wallet_key.enc
.env.enc
.encryption_key.secure
*.egg-info/
dist/
build/
IGNORE

# Re-init git
rm -rf .git
git init
git branch -m main
git add -A
git commit -m "Initial commit: x402 Halal Screening API"

# Create repo on GitHub
if command -v gh &>/dev/null; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token
  gh repo create anassetti20-prog/x402-halal-api --public --source=. --push --remote=origin
else
  curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/user/repos \
    -d '{"name":"x402-halal-api","description":"First Halal Crypto Screening API with x402 micropayments","private":false}'
  git remote add origin https://github.com/anassetti20-prog/x402-halal-api.git
  git push -u origin main
fi

echo "=== Done! ==="
echo "Repository: https://github.com/anassetti20-prog/x402-halal-api"