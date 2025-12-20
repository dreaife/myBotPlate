# 群消息备份工具使用手册

## 📖 目录
1. [详细配置](#配置详解)
2. [功能介绍](#功能介绍)
3. [常见问题](#常见问题)

## ⚙️ 配置详解

### 配置文件结构
配置文件位于 `telebot/group_backup_config.yml`。

#### 1. 基础设置
```yaml
telegram:
  api_id: 123456          # 从 my.telegram.org 获取
  api_hash: "abcdef..."   # 从 my.telegram.org 获取

settings:
  auto_delete_ignore_days: 7  # 超过7天的消息撤回时忽略，不标记
  mapping_retention_days: 30  # 保留30天的消息映射记录
  timezone: "Asia/Tokyo"      # 消息显示的时区
```

#### 2. 备份计划
```yaml
  backup_schedule:
    daily_time: "04:00"              # 每天凌晨4点本地导出
    local_export_dir: "/data/backups" # 导出路径
    weekly_day: "mon"                # 每周一
    weekly_time: "04:00"             # 凌晨4点上传到备份群
```

#### 3. 群组映射 (源 -> 目标)
支持将一个源群的消息转发到多个备份群。

**格式**:
```yaml
groups:
  SOURCE_ID:
    targets: [TARGET_ID_1, TARGET_ID_2]
    name: "源群名称" # 可选
    tag: "#标签"    # 可选
```

**示例**:
```yaml
groups:
  -100123456:
    targets: 
      - -100987654
    name: "我的群组"
```

## 🛠 功能介绍

### 1. 消息转发
- **文本**: 直接转发，包含发送者头部。
- **媒体**: 图片、视频、文件等直接发送，不带分隔线。
- **回复**: 自动追踪回复关系，在备份群中保持回复结构。

### 2. 状态追踪
- **撤回**: 当源消息被撤回，备份消息会更新 `#已撤回` 标签。如果超时无法编辑，会发送一条回复提示。
- **编辑**: 源消息编辑后，备份消息追加 `#已修改` 标签。

### 3. 排版样式
- **Header**: 包含发送者姓名、用户名、来源群名(多对一时)、时间。
- **Footer**: 连续消息在底部显示简短时间。
- **分隔线**: 文本消息之间有分隔线，媒体消息无。

### 4. 自动备份文件
- **每日备份**: 每天凌晨4点备份过去24h信息为文件 (针对备份群)
  - 命名格式： `{BackupGroupTitle}_YYYY-MM-DD_daily.bak`
- **每周备份**: 每周一凌晨4点上传到备份群
  - 命名格式： `{BackupGroupTitle}_YYYY-MM-DD_weekly.bak`

### 5. 系统日志
- **日志文件**: `/logs/bot/group_backup/backup.log`

## ❓ 常见问题

### Q: 如何获取群组 ID?
A: 可以运行项目中的 `telebot/get_chat_ids.py` 工具。

### Q: 为什么撤回没有生效?
A: Telegram 限制 Bot 只能编辑最近48小时内的消息。如果超过时间，系统会发送一条新的警告消息作为回复。

### Q: 为什么无法启动?
A: 请检查 `telebot/group_backup_config.yml` 中的 API ID 和 Hash 是否正确，以及是否有对应目录的写入权限。
