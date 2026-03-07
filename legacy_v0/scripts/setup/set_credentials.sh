#!/bin/bash
# DataShark Credential Setup Script
# Source this file to set environment variables in your current shell
#
# Usage:
#   source set_credentials.sh
#
# Note: These credentials are only set for your current shell session
# Add them to your ~/.zshrc or ~/.bashrc to persist across sessions

echo "🦈 Setting up DataShark credentials..."

# Check if credentials are already set
if [[ -n "$REDSHIFT_HOST" ]] && [[ -n "$REDSHIFT_DATABASE" ]]; then
    echo "✅ Credentials already set in environment"
    echo "   Database: $REDSHIFT_DATABASE"
    echo "   Host: $REDSHIFT_HOST"
    echo "   User: $REDSHIFT_USER"
    return 0
fi

# Set credentials (these should already be in your environment)
# If not, uncomment and fill in these lines:
# export REDSHIFT_HOST=your-redshift-host
# export REDSHIFT_PORT=5439
# export REDSHIFT_DATABASE=your-database
# export REDSHIFT_USER=your-username
# export REDSHIFT_PASSWORD=your-password

# Verify credentials are set
if [[ -z "$REDSHIFT_DATABASE" ]]; then
    echo "❌ REDSHIFT_DATABASE not set"
    echo ""
    echo "Please set your credentials:"
    echo "  export REDSHIFT_DATABASE=your-database"
    echo "  export REDSHIFT_HOST=your-redshift-host"
    echo "  export REDSHIFT_PORT=5439"
    echo "  export REDSHIFT_USER=your-username"
    echo "  export REDSHIFT_PASSWORD=<your-password>"
    return 1
fi

echo "✅ Credentials configured"
echo "   Database: $REDSHIFT_DATABASE"
echo "   Host: $REDSHIFT_HOST"
echo "   User: $REDSHIFT_USER"

