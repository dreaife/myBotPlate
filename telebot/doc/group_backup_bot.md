# 群消息备份程序 - 使用用户账号

## 🎯 功能特点

使用**你自己的 Telegram 账号**进行消息备份,而不是 Bot:

- ✅ **完整的撤回消息检测** - 可以精准检测到任何消息的撤回
- ✅ **支持所有消息类型** - 文本、图片、视频、文件、语音等
- ✅ **保留原始格式** - 媒体文件完整转发
- ✅ **发送者信息标注** - 显示发送者姓名、用户名和时间
- ✅ **消息编辑追踪** - 记录消息的编辑
- ✅ **无需管理员权限** - 只要你的账号在群里即可

## 📋 前置要求

### 1. 获取 Telegram API 凭证

1. 访问 https://my.telegram.org
2. 使用你的手机号登录
3. 点击 "API development tools"
4. 创建一个新应用(随便填写应用名称和描述)
5. 获取 **API ID** 和 **API Hash**

### 2. 准备环境

```bash
# 安装依赖
pip install -r requirements.txt

# 如果只需要安装 Telethon
pip install Telethon
```

## 🚀 快速开始

### 1️⃣ 配置环境变量

```bash
# 复制配置文件
cp .env.example .env

# 编辑配置
nano .env
```

在 `.env` 中填入:

```env
# 从 https://my.telegram.org 获取
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef

# 源群组ID (要备份的群)
SOURCE_CHAT_ID=-1001234567890

# 备份群组ID (保存消息的群)  
BACKUP_CHAT_ID=-1009876543210
```

### 2️⃣ 获取群组ID

**方法1: 使用 @userinfobot**
- 将机器人添加到群组
- 它会显示群组ID

**方法2: 使用代码获取**

创建临时脚本 `get_chats.py`:

```python
from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv('TELEGRAM_API_ID'))
api_hash = os.getenv('TELEGRAM_API_HASH')

async def main():
    client = TelegramClient('temp_session', api_id, api_hash)
    await client.start()
    
    print("\n你的对话列表:")
    async for dialog in client.iter_dialogs():
        print(f"{dialog.name}: {dialog.id}")
    
    await client.disconnect()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```

运行:
```bash
python get_chats.py
```

### 3️⃣ 运行程序

**首次运行会要求登录:**

```bash
cd /home/dreaife/bot
python3 telebot/group_backup_bot.py
```

**首次登录流程:**
1. 输入你的手机号(国际格式,如: +86123456789)
2. 输入 Telegram 发送给你的验证码
3. 如果启用了两步验证,输入密码

**登录后会生成 session 文件,下次运行无需再次登录**

### 4️⃣ 后台运行(推荐)

**使用 systemd 服务:**

1. 编辑服务文件:
```bash
nano deploy/group_backup_bot.service
```

修改用户名:
```ini
User=your_username
```

2. 安装并启动服务:
```bash
sudo cp deploy/group_backup_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable group_backup_bot
sudo systemctl start group_backup_bot
```

3. 查看状态:
```bash
sudo systemctl status group_backup_bot
sudo journalctl -u group_backup_bot -f
```

**使用 screen 或 tmux:**

```bash
# 使用 screen
screen -S backup
python3 telebot/group_backup_bot.py
# 按 Ctrl+A, 然后按 D 退出

# 重新连接
screen -r backup

# 或使用 tmux
tmux new -s backup
python3 telebot/group_backup_bot.py
# 按 Ctrl+B, 然后按 D 退出

# 重新连接
tmux attach -t backup
```

## 📊 消息格式

### 普通消息
```
👤 张三 @zhangsan
🕐 2025-12-09 10:30:00
──────────────────────────────
这是消息内容
```

### 编辑过的消息
```
👤 张三 @zhangsan
🕐 2025-12-09 10:30:00
✏️ (已编辑)
──────────────────────────────
这是编辑后的内容
```

### 撤回消息提示
```
⚠️ 消息已被撤回 ⚠️
🕐 撤回时间: 2025-12-09 10:35:00
📝 原消息ID: 12345
```

## 📁 数据存储

### Session 文件
- 位置: `/data/bot/group_backup/group_backup.session`
- 包含登录信息,**请妥善保管,不要泄露**

### 消息映射
- 位置: `/data/bot/group_backup/message_mapping.json`
- 记录原消息和备份消息的对应关系

### 日志文件
- 位置: `/logs/bot/group_backup/backup.log`
- 自动按天滚动,保留30天

## 🔧 常见问题

### Q: 首次运行时如何登录?
A: 程序会交互式地要求你输入:
1. 手机号(国际格式: +8613800138000)
2. 验证码(Telegram 会发送给你)
3. 两步验证密码(如果启用)

### Q: 多次运行需要重复登录吗?
A: 不需要。首次登录后会生成 session 文件,以后自动登录。

### Q: 可以同时运行多个备份任务吗?
A: 可以,使用不同的 `--session-name` 参数:

```bash
python3 telebot/group_backup_bot.py --session-name backup1
python3 telebot/group_backup_bot.py --session-name backup2
```

每个会话需要配置不同的环境变量或使用不同的 `.env` 文件。

### Q: Session 文件丢失怎么办?
A: 重新运行程序,会再次要求登录。

### Q: 如何停止程序?
```bash
# 如果是直接运行,按 Ctrl+C

# 如果是 systemd 服务
sudo systemctl stop group_backup_bot

# 如果是 screen
screen -r backup
# 然后按 Ctrl+C

# 如果是 tmux  
tmux attach -t backup
# 然后按 Ctrl+C
```

### Q: 能检测到所有撤回消息吗?
A: **是的!** 使用 Telethon 可以完整检测所有撤回消息,这是使用用户账号相比 Bot 的最大优势。

### Q: 会被封号吗?
A: 正常使用不会。但建议:
- 不要频繁大量发送消息
- 遵守 Telegram 使用条款
- 不要用于垃圾信息或骚扰

### Q: 可以备份私聊消息吗?
A: 可以,只需将 `SOURCE_CHAT_ID` 设置为对方的用户ID即可。

## 🔒 安全注意事项

1. **保护 Session 文件**
   - Session 文件相当于你的登录凭证
   - 不要分享给他人
   - 建议设置文件权限: `chmod 600 /data/bot/group_backup/*.session`

2. **保护 .env 文件**
   - 包含 API 凭证
   - 不要提交到 git 仓库
   - 已在 `.gitignore` 中排除

3. **隐私考虑**
   - 确保备份群的成员知晓并同意
   - 妥善管理备份群的访问权限

## 🆚 对比 Bot 方式

| 特性 | 用户账号 (Telethon) | Bot API |
|------|-------------------|---------|
| 撤回消息检测 | ✅ 完整支持 | ❌ 不支持 |
| 需要管理员权限 | ❌ 不需要 | ✅ 需要 |
| 消息历史 | ✅ 可获取 | ❌ 仅新消息 |
| 使用限制 | 稍严格 | 宽松 |
| 设置复杂度 | 需要 API 凭证 | 只需 Token |

## 📚 进阶使用

### 自定义目录
```bash
python3 telebot/group_backup_bot.py \
    --session-name my_backup \
    --log-dir /path/to/logs \
    --data-dir /path/to/data
```

### 备份多个群组
创建多个配置文件和服务:

```bash
# 配置1: .env.group1
TELEGRAM_API_ID=xxx
TELEGRAM_API_HASH=xxx
SOURCE_CHAT_ID=-1001111111111
BACKUP_CHAT_ID=-1002222222222

# 配置2: .env.group2  
TELEGRAM_API_ID=xxx
TELEGRAM_API_HASH=xxx
SOURCE_CHAT_ID=-1003333333333
BACKUP_CHAT_ID=-1004444444444
```

运行:
```bash
# 使用不同配置
env $(cat .env.group1 | xargs) python3 telebot/group_backup_bot.py --session-name group1
env $(cat .env.group2 | xargs) python3 telebot/group_backup_bot.py --session-name group2
```

## 🛠️ 故障排除

### 问题1: 无法登录

**错误信息**: `[400] PHONE_NUMBER_INVALID`

**解决方案**:
- 确保手机号格式正确: `+86130000000`
- 使用注册 Telegram 的手机号

### 问题2: Session 过期

**错误信息**: `Unauthorized`

**解决方案**:
```bash
# 删除旧的 session 文件
rm /data/bot/group_backup/*.session
# 重新运行程序登录
```

### 问题3: 无法获取消息

**可能原因**:
- 群组ID错误
- 你的账号不在源群中

**检查方法**:
```bash
# 查看日志
tail -f /logs/bot/group_backup/backup.log
```

## 📞 支持

如有问题,请:
1. 查看日志文件
2. 检查环境变量配置
3. 确认 API 凭证正确
4. 提交 Issue 或 Pull Request

---

**提示**: 首次使用建议在测试群组中试运行,确保一切正常后再用于正式群组。
