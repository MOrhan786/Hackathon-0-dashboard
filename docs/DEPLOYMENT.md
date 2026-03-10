# AI Employee - Deployment Guide

Complete guide for deploying your Personal AI Employee to Oracle Cloud (Free Tier).

---

## 📋 Prerequisites

- Oracle Cloud account (Free Tier)
- GitHub account
- Your AI Employee credentials (Gmail, WhatsApp, LinkedIn, etc.)

---

## 🚀 Quick Deploy (5 Minutes)

### Step 1: Create Oracle Cloud VM

1. Login to [Oracle Cloud Console](https://cloud.oracle.com)
2. Go to **Compute → Instances**
3. Click **Create Instance**
4. Configure:
   - **Name:** `ai-employee`
   - **Image:** Ubuntu 22.04 or 24.04
   - **Shape:** VM.Standard.A1.Flex (4 OCPU, 24GB RAM) - **FREE!**
   - **Storage:** 200GB
   - **SSH Keys:** Download and save securely
5. Click **Create**

### Step 2: Configure Security Rules

1. Go to **Virtual Cloud Networks → Your VCN → Security Lists**
2. Add **Ingress Rules**:
   ```
   Port 22   - SSH (required)
   Port 8765 - Dashboard (required)
   Port 8069 - Odoo (optional, if running Odoo locally)
   ```

### Step 3: Connect via SSH

```bash
ssh -i /path/to/your/key ubuntu@YOUR_ORACLE_PUBLIC_IP
```

### Step 4: Clone & Deploy

```bash
# Clone your repository
git clone https://github.com/MOrhan786/Hackathon-0-dashboard.git
cd Hackathon-0-dashboard

# Run the deployment script
bash deploy-oracle-cloud.sh
```

### Step 5: Configure Credentials

```bash
nano config/.env
```

**Edit these values:**
```env
# Safety (set false for production)
DEV_MODE=false
DRY_RUN=false

# Gmail (required for email monitoring)
GMAIL_CLIENT_ID=your_client_id
GMAIL_CLIENT_SECRET=your_secret
GMAIL_REFRESH_TOKEN=your_refresh_token
GMAIL_USER_EMAIL=your.email@gmail.com

# Odoo (optional - if using Odoo integration)
ODOO_URL=http://localhost:8069
ODOO_DATABASE=ai_employee
ODOO_USERNAME=your_email
ODOO_API_KEY=your_api_key

# WhatsApp (optional)
WHATSAPP_KEYWORDS=urgent,invoice,payment,asap,help

# LinkedIn (optional)
LINKEDIN_KEYWORDS=opportunity,invoice,project,meeting
```

### Step 6: Setup Browser Sessions (First Time Only)

```bash
# WhatsApp - Scan QR code
uv run python -m backend.watchers.whatsapp_watcher --setup

# LinkedIn - Manual login
uv run python -m backend.watchers.linkedin_watcher --setup

# Facebook/Instagram - Manual login
uv run python -m backend.watchers.facebook_watcher --setup
```

### Step 7: Start Services

```bash
# Start Orchestrator (watches + action executor)
sudo systemctl start ai-employee

# Start Dashboard
sudo systemctl start ai-dashboard

# Check status
sudo systemctl status ai-employee
sudo systemctl status ai-dashboard
```

### Step 8: Access Dashboard

Open in browser:
```
http://YOUR_ORACLE_PUBLIC_IP:8765
```

---

## 🔧 Manual Deployment (Step-by-Step)

If you prefer manual setup:

### 1. Install Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Install Playwright
uv run playwright install chromium
```

### 2. Setup Environment

```bash
cp config/.env.example config/.env
nano config/.env  # Edit with your credentials
```

### 3. Create Systemd Services

**Orchestrator Service:**
```bash
sudo nano /etc/systemd/system/ai-employee.service
```

```ini
[Unit]
Description=AI Employee Orchestrator
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Hackathon-0-dashboard
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/.local/bin/uv run python -m backend.orchestrator
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Dashboard Service:**
```bash
sudo nano /etc/systemd/system/ai-dashboard.service
```

```ini
[Unit]
Description=AI Employee Dashboard
After=network.target ai-employee.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Hackathon-0-dashboard
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/.local/bin/uv run python -m backend.dashboard_server --host 0.0.0.0 --port 8765
Restart=always

[Install]
WantedBy=multi-user.target
```

### 4. Enable & Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-employee ai-dashboard
sudo systemctl start ai-employee ai-dashboard
```

---

## 📊 Monitoring & Maintenance

### Check Status

```bash
# Service status
sudo systemctl status ai-employee
sudo systemctl status ai-dashboard

# View logs
sudo journalctl -u ai-employee -f
sudo journalctl -u ai-dashboard -f

# Check processes
ps aux | grep orchestrator
ps aux | grep dashboard
```

### Restart Services

```bash
sudo systemctl restart ai-employee
sudo systemctl restart ai-dashboard
```

### Stop Services

```bash
sudo systemctl stop ai-employee
sudo systemctl stop ai-dashboard
```

### Update Deployment

```bash
cd ~/Hackathon-0-dashboard
git pull
sudo systemctl restart ai-employee ai-dashboard
```

---

## 🔐 Security Best Practices

1. **Never commit `.env` file** - Already in `.gitignore`
2. **Use strong API keys** - Generate from respective platforms
3. **Enable firewall** - Only required ports open
4. **Regular updates** - `sudo apt update && sudo apt upgrade`
5. **Backup vault data** - Regular backups of `vault/` folder
6. **Monitor logs** - Check `/var/log/syslog` for issues

---

## ❄️ Troubleshooting

### Dashboard Not Accessible

```bash
# Check if service is running
sudo systemctl status ai-dashboard

# Check firewall
sudo ufw status

# Check port is listening
sudo netstat -tlnp | grep 8765
```

### Orchestrator Not Running

```bash
# Check logs
sudo journalctl -u ai-employee -f

# Check .env configuration
cat config/.env | grep -E "DEV_MODE|DRY_RUN"

# Restart service
sudo systemctl restart ai-employee
```

### Browser Session Issues

```bash
# Remove session data and re-setup
rm -rf config/linkedin_session/
uv run python -m backend.watchers.linkedin_watcher --setup
```

### Odoo Connection Failed

```bash
# Check if Odoo is accessible
curl http://localhost:8069

# If Odoo is on different machine, use ngrok
ngrok http 8069
# Update ODOO_URL in .env with ngrok URL
```

---

## 📈 Cost Estimate

| Resource | Oracle Cloud Free Tier | Your Cost |
|----------|----------------------|-----------|
| Compute (4 OCPU, 24GB RAM) | ✅ Included | $0/month |
| Storage (200GB) | ✅ Included | $0/month |
| Network (10TB outbound) | ✅ Included | $0/month |
| **Total** | | **$0/month** |

---

## 🎯 Post-Deployment Checklist

- [ ] Dashboard accessible at `http://YOUR_IP:8765`
- [ ] Gmail watcher receiving emails
- [ ] WhatsApp session active
- [ ] LinkedIn session active
- [ ] Test email received and processed
- [ ] Test post published successfully
- [ ] Odoo connection working (if configured)
- [ ] Logs showing no errors
- [ ] Services auto-restart on reboot

---

## 📞 Support

For issues or questions:
- Check logs: `sudo journalctl -u ai-employee -f`
- Review documentation: `docs/ARCHITECTURE.md`
- GitHub Issues: https://github.com/MOrhan786/Hackathon-0-dashboard/issues

---

**Deployed successfully? Share your experience!** 🚀
