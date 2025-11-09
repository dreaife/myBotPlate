# myBotPlate 🤖

一个基于 Python 的 Telegram Bot 模板项目，集成了 OpenAI API 和多种 AI 服务插件。

## ✨ 特性

- 🧩 **插件化 AI 服务架构** - 支持 OpenAI、Gemini、Anthropic、Grok 等多种 AI 服务
- 💬 **Telegram Bot 集成** - 基于 python-telegram-bot 框架
- 🔒 **环境变量管理** - 使用 python-dotenv 安全管理敏感信息
- 🐍 **虚拟环境** - 隔离的 Python 3.14.0 环境

## 📁 项目结构

```
bot/
├── ai_plugins/          # AI 服务插件
│   ├── ai_manager.py    # AI 管理器
│   ├── base/           # 基础抽象类
│   ├── openai/         # OpenAI 服务
│   ├── gemini/         # Gemini 服务
│   ├── anthropic/      # Anthropic 服务
│   └── grok/           # Grok 服务
├── telebot/            # Telegram Bot 实现
│   └── dreaife_test_bot.py
├── .env                # 环境变量配置
├── requirements.txt    # 项目依赖
├── BotServiceConfig.md # 详细服务管理文档
└── README.MD          # 本文件
```

## � 快速开始

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
OPENAI_API_KEY="your-openai-api-key"
TELEGRAM_BOT_DREAIFE_TOKEN="your-telegram-bot-token"
```

### 3. 启动 Bot

```bash
# 前台运行（调试模式）
python telebot/dreaife_test_bot.py

# 后台运行（生产模式）
nohup python telebot/dreaife_test_bot.py > bot_output.log 2>&1 &
echo $! > bot.pid
```

## 📦 依赖项

主要依赖包：

- `openai==1.72.0` - OpenAI API 客户端
- `python-telegram-bot==22.0` - Telegram Bot SDK
- `python-dotenv==1.1.0` - 环境变量管理
- `pydantic==2.11.3` - 数据验证
- `httpx==0.28.1` - HTTP 客户端

完整依赖列表见 [`requirements.txt`](requirements.txt)

## 💡 功能说明

### Bot 命令

- `/start` - 开始与 Bot 对话
- `/help` - 显示帮助信息
- `/clear` - 清除当前用户的聊天历史

### AI 服务管理

项目使用 `AIManager` 管理多个 AI 服务提供商，可以轻松切换或扩展新的 AI 服务。

## 🔧 开发指南

### 添加新的 AI 服务

1. 在 `ai_plugins/` 下创建新的服务目录
2. 继承 `base/base_ai.py` 中的基类
3. 实现必要的接口方法
4. 在 `AIManager` 中注册新服务

## 📝 快速命令

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

## 📞 参考资料

- [Python 官方文档](https://docs.python.org/)
- [python-telegram-bot 文档](https://docs.python-telegram-bot.org/)
- [OpenAI API 文档](https://platform.openai.com/docs/)

## 📄 License

MIT

---

**Version**: 1.0.0  
**Python**: 3.14.0  
**Last Updated**: 2025年11月9日
