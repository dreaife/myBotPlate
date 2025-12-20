# Group Backup Tool User Manual

## 📖 Contents
1. [Configuration](#configuration)
2. [Features](#features)
3. [FAQ](#faq)

## ⚙️ Configuration

### Config File
Located at `telebot/group_backup_config.yml`.

#### 1. Basic Settings
```yaml
telegram:
  api_id: 123456          # From my.telegram.org
  api_hash: "abcdef..."   # From my.telegram.org

settings:
  auto_delete_ignore_days: 7  # Ignore recalls for messages older than 7 days
  mapping_retention_days: 30  # Keep mapping records for 30 days
  timezone: "Asia/Tokyo"      # Display timezone
```

#### 2. Backup Schedule
```yaml
  backup_schedule:
    daily_time: "04:00"              # Daily local export at 4 AM
    local_export_dir: "/data/backups" # Export path
    weekly_day: "mon"                # Weekly upload on Monday
    weekly_time: "04:00"             # At 4 AM
```

#### 3. Group Mapping (Source-to-Targets)
Support forwarding one source group to multiple backup groups.

**Format**:
```yaml
groups:
  SOURCE_ID:
    targets: [TARGET_ID_1, TARGET_ID_2]
    name: "Source Name" # Optional
    tag: "#Tag"         # Optional
```

**Example**:
```yaml
groups:
  -100123456:
    targets: 
      - -100987654
    name: "My Group"
```

## 🛠 Features

### 1. Message Forwarding
- **Text**: Direct forwarding with sender header.
- **Media**: Photos, videos, files sent directly without separator lines.
- **Replies**: Automatically traces reply relationships.

### 2. State Tracking
- **Recall**: When source message is recalled, backup is tagged `#Recalled` (or `#已撤回` in CN).
- **Edit**: When source is edited, backup is tagged `#Edited` (or `#已修改`).

### 3. Styling
- **Header**: Includes Sender Name, Username, Source Group Name, Time.
- **Footer**: Short timestamp for consecutive messages.

### 4. Automatic Backup Files
- **Daily Backup**: Backs up messages from the last 24 hours at 4 AM every day.
  - Naming Format: {group name/group_id}_YYYY-MM-DD.bak
- **Weekly Backup**: Uploads to the backup group at 4 AM every Monday.

### 5. System Log
- **Log File**: `/logs/bot/group_backup/backup.log`

## ❓ FAQ

### Q: How to get Chat IDs?
A: Run `telebot/get_chat_ids.py` or forward a message to @userinfobot.

### Q: Why isn't recall working?
A: Telegram limits editing to messages sent within the last 48 hours. Older messages will trigger a reply warning instead.
