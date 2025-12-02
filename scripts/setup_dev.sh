#!/bin/bash
# Development environment setup script

set -e

echo "🚀 Setting up VivaAI development environment..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cat > .env << EOF
# Required for production
VIVA_HMAC_SECRET=DEVELOPMENT-ONLY-CHANGE-ME-min-32-chars

# Optional: Rate limiting configuration
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
RATE_LIMIT_BURST=10

# Optional: Environment
ENVIRONMENT=development
EOF
    echo "✅ Created .env file with development defaults"
else
    echo "✅ .env file already exists"
fi

# Install pre-commit hooks
if [ -f .pre-commit-config.yaml ]; then
    echo "🔧 Installing pre-commit hooks..."
    uv run pre-commit install || echo "⚠️  pre-commit not installed, skipping hooks"
fi

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "  1. Review and update .env file with your configuration"
echo "  2. Run 'make test' to verify installation"
echo "  3. Run 'make help' to see available commands"
echo ""

