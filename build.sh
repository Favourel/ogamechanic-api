#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Starting build process..."

# Install system dependencies for PostGIS
echo "Installing system dependencies..."

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Create logs directory if it doesn't exist
echo "Creating logs directory..."
mkdir -p logs

# Set proper permissions
echo "Setting permissions..."
chmod +x build.sh

echo "Build process completed successfully!"




