# myBotPlate 🤖

一个基于 Python 的 Telegram 项目，包含 AI Bot 和群消息备份工具。

## ✨ 特性

### AI Bot
- 🧩 **插件化 AI 服务架构** - 支持 OpenAI、Gemini、Anthropic、Grok 等多种 AI 服务
- 💬 **Telegram Bot 集成** - 基于 python-telegram-bot 框架
- 🔒 **环境变量管理** - 使用 python-dotenv 安全管理敏感信息

### 群消息备份工具 ⭐ NEW
- 📝 **完整消息备份** - 使用你的账号实时转发群消息到备份群
- ⚠️ **撤回消息检测** - 精准捕获并标注被撤回的消息
- 🎯 **全类型支持** - 文本、图片、视频、文件、语音等所有消息类型
- 👤 **发送者追踪** - 保留原发送者姓名、用户名和时间信息
- 🔄 **自动映射** - 记录原消息和备份消息的对应关系

## 📁 项目结构

```
bot/
├── ai_plugins/                      # AI 服务插件
│   ├── ai_manager.py                # AI 管理器
│   ├── base/                       # 基础抽象类
│   ├── openai/                     # OpenAI 服务
│   ├── gemini/                     # Gemini 服务
│   ├── anthropic/                  # Anthropic 服务
│   └── grok/                       # Grok 服务
├── telebot/                         # Telegram 程序
│   ├── dreaife_test_bot.py         # AI Bot
│   ├── group_backup_bot.py         # 群消息备份工具 ⭐
│   ├── get_chat_ids.py             # 群组ID获取工具
│   └── doc/                        # 文档
├── deploy/                          # 部署配置
│   └── group_backup_bot.service    # Systemd 服务
├── .env                            # 环境变量配置
├── requirements.txt                # 项目依赖
├── QUICKSTART.md                   # 快速开始 ⭐
├── USER_ACCOUNT_BACKUP_README.md   # 完整使用文档
├── FILES_GUIDE.md                  # 文件说明
├── BotServiceConfig.md             # 服务管理文档
└── README.MD                       # 本文件
```

## 🚀 快速开始

### 选择你需要的功能

#### 🎯 群消息备份工具 (推荐新手)

**5分钟快速上手** - [查看快速指南](QUICKSTART.md)

```bash
# 1. 安装依赖
pip install Telethon python-dotenv

# 2. 配置 (从 https://my.telegram.org 获取凭证)
cp .env.example .env
nano .env  # 填入 API_ID, API_HASH, 群组ID

# 3. 运行
./start_backup.sh
# 或
python3 telebot/group_backup_bot.py
```

**功能**: 自动转发群消息到备份群，检测撤回消息

**详细文档**: [USER_ACCOUNT_BACKUP_README.md](USER_ACCOUNT_BACKUP_README.md)

---

#### 🤖 AI Bot

### 1. 环境准备

```bash
# 克隆项目
git clone git@github.com:dreaife/myBotPlate.git
cd myBotPlate

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件并添加必要的 API 密钥：

```bash
# AI Bot 配置
OPENAI_API_KEY="your-openai-api-key"
TELEGRAM_BOT_DREAIFE_TOKEN="your-telegram-bot-token"

# 群消息备份配置 (可选)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef
SOURCE_CHAT_ID=-1001234567890
BACKUP_CHAT_ID=-1009876543210
```

### 3. 启动程序

**AI Bot**:
```bash
# 前台运行（调试模式）
python telebot/dreaife_test_bot.py

# 后台运行（生产模式）
nohup python telebot/dreaife_test_bot.py > bot_output.log 2>&1 &
echo $! > bot.pid
```

**群消息备份**:
```bash
# 使用快速启动脚本
./start_backup.sh

# 或直接运行
python3 telebot/group_backup_bot.py

# 后台运行
screen -S backup
python3 telebot/group_backup_bot.py
# Ctrl+A, D 退出
```

## 📦 依赖项

主要依赖包：

**AI Bot**:
- `openai==1.72.0` - OpenAI API 客户端
- `python-telegram-bot==22.0` - Telegram Bot SDK
- `pydantic==2.11.3` - 数据验证
- `httpx==0.28.1` - HTTP 客户端

**群消息备份**:
- `Telethon==1.38.1` - Telegram 用户客户端
- `python-dotenv==1.1.0` - 环境变量管理

完整依赖列表见 [`requirements.txt`](requirements.txt)

## 💡 功能说明

### 群消息备份工具

**核心功能**:
- ✅ 实时转发源群消息到备份群
- ✅ 完整的撤回消息检测和标注
- ✅ 支持所有消息类型(文本、图片、视频、文件、语音等)
- ✅ 显示发送者信息和时间戳
- ✅ 自动保存消息映射关系

**使用场景**:
- 重要群组的消息备份
- 监控和记录群组动态
- 撤回消息的追溯

**文档**:
- 快速开始: [QUICKSTART.md](QUICKSTART.md)
- 完整文档: [USER_ACCOUNT_BACKUP_README.md](USER_ACCOUNT_BACKUP_README.md)
- 文件说明: [FILES_GUIDE.md](FILES_GUIDE.md)

### AI Bot

**Bot 命令**:
- `/start` - 开始与 Bot 对话
- `/help` - 显示帮助信息
- `/clear` - 清除当前用户的聊天历史

**AI 服务管理**:
项目使用 `AIManager` 管理多个 AI 服务提供商，可以轻松切换或扩展新的 AI 服务。

## 🔧 开发指南

### 添加新的 AI 服务

1. 在 `ai_plugins/` 下创建新的服务目录
2. 继承 `base/base_ai.py` 中的基类
3. 实现必要的接口方法
4. 在 `AIManager` 中注册新服务

## 📝 快速命令

### 群消息备份

```bash
# 获取群组ID
python3 telebot/get_chat_ids.py

# 后台运行
screen -S backup
python3 telebot/group_backup_bot.py

# 查看日志
tail -f /logs/bot/group_backup/backup.log

# 使用 systemd 服务(需先python运行一遍程序完成登录获取到session文件)
sudo cp deploy/group_backup_bot.service /etc/systemd/system/
sudo systemctl start group_backup_bot
sudo systemctl status group_backup_bot
```

### AI Bot

```bash
# 启动服务
cd /home/dreaife/bot && source venv/bin/activate && python telebot/dreaife_test_bot.py

# 停止服务
cat bot.pid | xargs kill

# 查看日志
tail -f bot_output.log

# 更新依赖
source venv/bin/activate && pip install -r requirements.txt
```

## 📚 文档索引

- 📖 **主文档**: [README.MD](README.MD) (当前文件)
- ⚡ **快速开始**: [QUICKSTART.md](QUICKSTART.md) - 5分钟上手群消息备份
- 📚 **完整指南**: [USER_ACCOUNT_BACKUP_README.md](USER_ACCOUNT_BACKUP_README.md)
- 📁 **文件说明**: [FILES_GUIDE.md](FILES_GUIDE.md) - 了解各文件作用
- 🔧 **服务管理**: [BotServiceConfig.md](BotServiceConfig.md) - AI Bot 服务配置

## 📞 参考资料

- [Python 官方文档](https://docs.python.org/)
- [python-telegram-bot 文档](https://docs.python-telegram-bot.org/)
- [Telethon 文档](https://docs.telethon.dev/)
- [OpenAI API 文档](https://platform.openai.com/docs/)
- [Telegram API 文档](https://core.telegram.org/api)

## ⚠️ 注意事项

### 群消息备份

1. **隐私保护**: 确保备份群成员知晓并同意消息被备份
2. **Session 安全**: `/data/bot/group_backup/*.session` 是登录凭证,请勿泄露
3. **API 凭证**: 妥善保管从 https://my.telegram.org 获取的 API ID 和 Hash
4. **使用规范**: 遵守 Telegram 使用条款,不要用于垃圾信息或骚扰

### AI Bot

1. **API 密钥**: 保护好你的 OpenAI API Key
2. **费用控制**: 注意 API 调用次数和费用
3. **环境变量**: 不要将 `.env` 文件提交到版本控制

## 🐛 故障排除

### 群消息备份

**无法登录**:
```bash
# 删除旧的 session 文件
rm /data/bot/group_backup/*.session
# 重新运行程序
python3 telebot/group_backup_bot.py
```

**收不到消息**:
- 检查群组ID是否正确
- 确认你的账号在源群中

**查看详细日志**:
```bash
tail -f /logs/bot/group_backup/backup.log
```

更多问题请查看: [USER_ACCOUNT_BACKUP_README.md](USER_ACCOUNT_BACKUP_README.md)

## 📄 License

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

## 📮 联系方式

- GitHub: [@dreaife](https://github.com/dreaife)
- 项目地址: [myBotPlate](https://github.com/dreaife/myBotPlate)

---

**Version**: 2.0.0  
**Python**: 3.8+  
**Last Updated**: 2025年12月9日

### 更新日志

**v2.0.0** (2025-12-09)
- ➕ 新增群消息备份工具(使用 Telethon)
- ✅ 支持完整的撤回消息检测
- ✅ 支持所有消息类型转发
- 📚 新增完整文档和快速开始指南

**v1.0.0** (2025-11-09)
- 🎉 初始版本
- ✅ AI Bot 基础功能
- ✅ 多 AI 服务插件支持
