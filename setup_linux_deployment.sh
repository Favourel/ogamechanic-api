#!/bin/bash

# OGameMechanic Linux Deployment Setup Script
# This script creates systemd service files for Django, Celery Worker, and Celery Beat
# Run with: sudo ./setup_linux_deployment.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

print_info "OGameMechanic Linux Deployment Setup"
print_info "====================================="
echo ""

# Get project directory
if [ -z "$1" ]; then
    DEFAULT_PROJECT_DIR=$(pwd)
    read -p "Enter project directory [default: $DEFAULT_PROJECT_DIR]: " PROJECT_DIR
    PROJECT_DIR=${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}
else
    PROJECT_DIR="$1"
fi

# Validate project directory
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory does not exist: $PROJECT_DIR"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/manage.py" ]; then
    print_error "manage.py not found in $PROJECT_DIR. Is this a Django project?"
    exit 1
fi

print_info "Project directory: $PROJECT_DIR"

# Get user to run services
if [ -z "$2" ]; then
    DEFAULT_USER=$(logname 2>/dev/null || echo "$SUDO_USER")
    read -p "Enter user to run services [default: $DEFAULT_USER]: " SERVICE_USER
    SERVICE_USER=${SERVICE_USER:-$DEFAULT_USER}
else
    SERVICE_USER="$2"
fi

# Validate user exists
if ! id "$SERVICE_USER" &>/dev/null; then
    print_error "User does not exist: $SERVICE_USER"
    exit 1
fi

print_info "Service user: $SERVICE_USER"

# Get Gunicorn workers
read -p "Enter number of Gunicorn workers [default: 4]: " GUNICORN_WORKERS
GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}

print_info "Gunicorn workers: $GUNICORN_WORKERS"

# Get Celery worker concurrency
read -p "Enter Celery worker concurrency [default: 2]: " CELERY_CONCURRENCY
CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-2}

print_info "Celery worker concurrency: $CELERY_CONCURRENCY"

# Get virtual environment path
read -p "Enter virtual environment path [default: $PROJECT_DIR/venv]: " VENV_PATH
VENV_PATH=${VENV_PATH:-$PROJECT_DIR/venv}

if [ ! -d "$VENV_PATH" ]; then
    print_warn "Virtual environment not found at $VENV_PATH"
    read -p "Create virtual environment? (y/n) [default: n]: " CREATE_VENV
    if [ "${CREATE_VENV,,}" = "y" ]; then
        print_info "Creating virtual environment..."
        python3 -m venv "$VENV_PATH"
        print_info "Virtual environment created. Please install requirements manually."
    fi
fi

print_info "Virtual environment: $VENV_PATH"

# Get Python executable
PYTHON_EXEC="$VENV_PATH/bin/python"
GUNICORN_EXEC="$VENV_PATH/bin/gunicorn"
CELERY_EXEC="$VENV_PATH/bin/celery"

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    print_warn ".env file not found at $PROJECT_DIR/.env"
    print_warn "Please create .env file with required environment variables"
    print_warn "You can use .env.example as a template"
fi

# Create necessary directories
print_info "Creating necessary directories..."
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/staticfiles"
mkdir -p "$PROJECT_DIR/media"
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/staticfiles"
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/media"

# Create systemd service files directory if it doesn't exist
SYSTEMD_DIR="/etc/systemd/system"

# Function to create Django/Gunicorn service file
create_web_service() {
    print_info "Creating Django/Gunicorn systemd service file..."
    
    cat > "$SYSTEMD_DIR/ogamechanic-web.service" <<EOF
[Unit]
Description=OGameMechanic Django Web Application
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_PATH/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$GUNICORN_EXEC ogamechanic.wsgi:application \\
    --bind 0.0.0.0:8000 \\
    --workers $GUNICORN_WORKERS \\
    --worker-class sync \\
    --timeout 120 \\
    --graceful-timeout 30 \\
    --max-requests 1000 \\
    --max-requests-jitter 50 \\
    --access-logfile - \\
    --error-logfile - \\
    --log-level info
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ogamechanic-web

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR/logs $PROJECT_DIR/media $PROJECT_DIR/staticfiles

[Install]
WantedBy=multi-user.target
EOF

    print_info "Created: $SYSTEMD_DIR/ogamechanic-web.service"
}

# Function to create Celery worker service file
create_worker_service() {
    print_info "Creating Celery worker systemd service file..."
    
    cat > "$SYSTEMD_DIR/ogamechanic-worker.service" <<EOF
[Unit]
Description=OGameMechanic Celery Worker
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_PATH/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$CELERY_EXEC -A ogamechanic worker \\
    --loglevel=info \\
    --concurrency=$CELERY_CONCURRENCY \\
    --max-tasks-per-child=1000 \\
    --time-limit=3600 \\
    --soft-time-limit=3300
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ogamechanic-worker

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR/logs

[Install]
WantedBy=multi-user.target
EOF

    print_info "Created: $SYSTEMD_DIR/ogamechanic-worker.service"
}

# Function to create Celery beat service file
create_beat_service() {
    print_info "Creating Celery beat systemd service file..."
    
    cat > "$SYSTEMD_DIR/ogamechanic-beat.service" <<EOF
[Unit]
Description=OGameMechanic Celery Beat Scheduler
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_PATH/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$CELERY_EXEC -A ogamechanic beat \\
    --loglevel=info \\
    --scheduler=django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ogamechanic-beat

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR/logs

[Install]
WantedBy=multi-user.target
EOF

    print_info "Created: $SYSTEMD_DIR/ogamechanic-beat.service"
}

# Create service files
create_web_service
create_worker_service
create_beat_service

# Set proper permissions on .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    chmod 600 "$PROJECT_DIR/.env"
    chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/.env"
    print_info "Set permissions on .env file"
fi

# Reload systemd
print_info "Reloading systemd daemon..."
systemctl daemon-reload

# Summary
echo ""
print_info "====================================="
print_info "Setup completed successfully!"
print_info "====================================="
echo ""
print_info "Service files created:"
echo "  - /etc/systemd/system/ogamechanic-web.service"
echo "  - /etc/systemd/system/ogamechanic-worker.service"
echo "  - /etc/systemd/system/ogamechanic-beat.service"
echo ""
print_info "Next steps:"
echo "  1. Review and update .env file with your configuration"
echo "  2. Make sure all dependencies are installed in virtual environment"
echo "  3. Run database migrations: python manage.py migrate"
echo "  4. Collect static files: python manage.py collectstatic --noinput"
echo "  5. Enable services:"
echo "     sudo systemctl enable ogamechanic-web"
echo "     sudo systemctl enable ogamechanic-worker"
echo "     sudo systemctl enable ogamechanic-beat"
echo "  6. Start services:"
echo "     sudo systemctl start ogamechanic-web"
echo "     sudo systemctl start ogamechanic-worker"
echo "     sudo systemctl start ogamechanic-beat"
echo "  7. Check service status:"
echo "     sudo systemctl status ogamechanic-web"
echo "     sudo systemctl status ogamechanic-worker"
echo "     sudo systemctl status ogamechanic-beat"
echo ""
print_info "View logs with:"
echo "  sudo journalctl -u ogamechanic-web -f"
echo "  sudo journalctl -u ogamechanic-worker -f"
echo "  sudo journalctl -u ogamechanic-beat -f"
echo ""

