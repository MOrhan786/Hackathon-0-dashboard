#!/bin/bash
# Oracle Cloud Deployment Script for AI Employee
# Run this on your Oracle Cloud VM after cloning the repo

set -e

echo "=========================================="
echo "AI Employee - Oracle Cloud Setup"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Error: Do not run as root${NC}"
    exit 1
fi

echo ""
echo "Step 1: Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo ""
echo "Step 2: Installing Python dependencies..."
sudo apt install -y python3-pip python3-venv git curl wget

echo ""
echo "Step 3: Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

echo ""
echo "Step 4: Installing Playwright browsers..."
uv run playwright install chromium
uv run playwright install-deps chromium 2>/dev/null || true

echo ""
echo "Step 5: Setting up environment..."
if [ ! -f "config/.env" ]; then
    cp config/.env.example config/.env
    echo -e "${YELLOW}Created config/.env - Please edit with your credentials${NC}"
else
    echo -e "${GREEN}config/.env already exists${NC}"
fi

echo ""
echo "Step 6: Creating systemd service for Orchestrator..."
sudo tee /etc/systemd/system/ai-employee.service > /dev/null <<EOF
[Unit]
Description=AI Employee Orchestrator
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
Environment="PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$HOME/.local/bin/uv run python -m backend.orchestrator
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "Step 7: Creating systemd service for Dashboard..."
sudo tee /etc/systemd/system/ai-dashboard.service > /dev/null <<EOF
[Unit]
Description=AI Employee Dashboard
After=network.target ai-employee.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
Environment="PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$HOME/.local/bin/uv run python -m backend.dashboard_server --host 0.0.0.0 --port 8765
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "Step 8: Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable ai-employee
sudo systemctl enable ai-dashboard

echo ""
echo "Step 9: Opening firewall ports..."
sudo ufw allow 22/tcp comment "SSH"
sudo ufw allow 8765/tcp comment "Dashboard"
sudo ufw allow 8069/tcp comment "Odoo (optional)" 2>/dev/null || true

echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Edit config/.env with your credentials"
echo "2. Setup session files (WhatsApp, LinkedIn, etc.)"
echo "3. Start services:"
echo "   sudo systemctl start ai-employee"
echo "   sudo systemctl start ai-dashboard"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status ai-employee"
echo "   sudo systemctl status ai-dashboard"
echo ""
echo "5. Access Dashboard:"
echo "   http://$(curl -s ifconfig.me):8765"
echo ""
echo "=========================================="
