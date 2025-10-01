#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Starting build process..."

# Install system dependencies for PostGIS
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    postgresql-client \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    gettext

# Set GDAL environment variables
export GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so
export GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so

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




