# Telegram Group Backup 🤖
(Previously myBotPlate)

A powerful Telegram group message backup tool developed with Python and Telethon.

[🇺🇸 English](README.md) | [🇨🇳 中文](README_CN.md)

## ✨ Features

### Group Message Backup Tool
- 📝 **Full Message Backup** - Real-time forwarding (N to N support).
- ⚠️ **Recall/Edit Tracking** - Auto-tag recalled or edited messages.
- ⏰ **Scheduled Backup** - Daily local export & Weekly remote upload.
- 🌏 **Timezone Support** - Custom timezone display.
- 💅 **Rich Styling** - Optimized layout for text and media.

### AI Bot (Optional)
- 🧩 **Plugin Architecture** - Supports OpenAI, Grok, etc.

## 📁 Project Structure

```
bot/
├── telebot/                         # Core Code
│   ├── group_backup/               # Backup Module ⭐
│   │   ├── core.py
│   │   ├── handlers.py
│   │   └── mapper.py
│   ├── doc/                        # Documentation 📖
│   └── group_backup_bot.py         # Entry Point
├── deploy/                          # Deployment
└── requirements.txt                # Dependencies
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configuration
```bash
cp telebot/group_backup_config.example.yml telebot/group_backup_config.yml
nano telebot/group_backup_config.yml # check config

# systemd
sudo cp deploy/group_backup_bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/group_backup_bot.service # check main process path
sudo systemctl daemon-reload
sudo systemctl enable group_backup_bot # enable auto-start
```

### 3. Run
```bash
# run directly
python3 telebot/group_backup_bot.py

# systemd
sudo systemctl start group_backup_bot # start service
sudo systemctl status group_backup_bot # check status
```

## 📦 Dependencies
- `Telethon` - Telegram Client
- `APScheduler` - Scheduling
- `pytz` - Timezone
- `PyYAML` - Config Parsing

## 📚 Documentation

- 📖 [User Manual (Config & Usage)](telebot/doc/group_backup_manual_en.md) - **Click here for Details**
- 🔧 [Systemd Deployment](deploy/group_backup_bot.service)

## 🐛 Troubleshooting

- **Login Failed**: Delete `/data/bot/group_backup/*.session` and retry.
- **No Messages**: Check API ID/Hash and Chat IDs.
- **Logs**: `tail -f /logs/bot/group_backup/backup.log`

---
**GitHub**: [@dreaife](https://github.com/dreaife) | **License**: MIT

