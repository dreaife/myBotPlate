# Telegram Group Backup 🤖
(原 myBotPlate)

一个强大的 Telegram 群组消息备份工具，基于 Python 和 Telethon 开发。

[🇺🇸 English](README.md) | [🇨🇳 中文](README_CN.md)

## ✨ 特性

### 群消息备份工具
- 📝 **完整消息备份** - 实时转发源群消息到备份群，支持 N 对 N 映射
- ⚠️ **撤回/编辑追踪** - 自动检测并标注被撤回或编辑的消息
- ⏰ **定时备份** - 支持每日本地导出和每周远程上传备份
- 🌏 **时区支持** - 自定义时区显示 (如 Asia/Tokyo)
- 💅 **精美排版** - 优化的消息展示样式，支持富媒体无缝显示

### AI Bot (可选功能)
- 🧩 **插件化架构** - 支持 OpenAI、Grok 等多种 AI 服务

## 📁 项目结构

```
bot/
├── telebot/                         # 核心代码
│   ├── group_backup/               # 备份模块 ⭐
│   │   ├── core.py                 # 核心逻辑
│   │   ├── handlers.py             # 消息处理
│   │   └── mapper.py               # 映射管理
│   ├── doc/                        # 文档目录 📖
│   └── group_backup_bot.py         # 启动入口
├── deploy/                          # 部署文件
└── requirements.txt                # 项目依赖
```

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置
```bash
cp telebot/group_backup_config.example.yml telebot/group_backup_config.yml
nano telebot/group_backup_config.yml # check config

# systemd
sudo cp deploy/group_backup_bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/group_backup_bot.service # check main process path
sudo systemctl daemon-reload
sudo systemctl enable group_backup_bot # enable auto-start
```

### 3. 运行
```bash
# run directly
python3 telebot/group_backup_bot.py

# systemd
sudo systemctl start group_backup_bot # start service
sudo systemctl status group_backup_bot # check status
```

## 📦主要依赖
- `Telethon` - Telegram 客户端
- `APScheduler` - 定时任务
- `pytz` - 时区处理
- `PyYAML` - 配置解析

## 📚 文档索引

- 📖 [群消息备份使用手册](telebot/doc/group_backup_manual_cn.md) - **详细配置与使用说明请点此**
- 🔧 [Systemd 部署指南](deploy/group_backup_bot.service)

## 🐛 故障排除

- **无法登录**: 删除 `/data/bot/group_backup/*.session` 后重试。
- **收不到消息**: 检查 API ID/Hash 及群组 ID 配置。
- **查看日志**: `tail -f /logs/bot/group_backup/backup.log`

---
**GitHub**: [@dreaife](https://github.com/dreaife) | **License**: MIT

