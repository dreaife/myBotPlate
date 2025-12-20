#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
群消息备份程序 (使用用户账号)
功能:
1. 将源群的所有消息转发到备份群
2. 检测并标注撤回的消息
3. 保存消息映射关系
"""

from telethon import TelegramClient, events
from telethon.tl.types import MessageService
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
import os
import sys
import json
import yaml  # Added yaml
from pathlib import Path
from datetime import datetime
import argparse
import asyncio

# 加载环境变量
load_dotenv()


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Telegram 群消息备份程序 (用户账号)')
    parser.add_argument('--session-name', type=str, default='group_backup',
                        help='会话名称，用于日志和数据目录 (默认: group_backup)')
    parser.add_argument('--config', type=str, default='telebot/group_backup_config.yml',
                        help='配置文件路径 (默认: telebot/group_backup_config.yml)')
    parser.add_argument('--log-dir', type=str, default=None,
                        help='日志目录路径 (默认: /logs/bot/<session-name>/)')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='数据目录路径 (默认: /data/bot/<session-name>/)')
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config file {config_path}: {e}")
        return {}


def setup_logging(session_name, log_dir=None):
    """设置日志配置"""
    if log_dir is None:
        log_dir = Path("/logs") / "bot" / session_name
    else:
        log_dir = Path(log_dir)
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "backup.log"

    handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler, logging.StreamHandler()]
    )
    
    return logging.getLogger(__name__)


class MessageMapper:
    """消息映射管理器 - 用于记录原消息和转发消息的对应关系"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mapping_file = self.data_dir / "message_mapping.json"
        self.mapping = self._load_mapping()
    
    def _load_mapping(self) -> dict:
        """加载消息映射"""
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"加载消息映射失败: {e}")
                return {}
        return {}
    
    def _save_mapping(self):
        """保存消息映射"""
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存消息映射失败: {e}")
    
    def add_mapping(self, source_chat_id: int, source_msg_id: int, 
                    backup_chat_id: int, backup_msg_id: int):
        """添加消息映射 (支持一对多)"""
        key = f"{source_chat_id}_{source_msg_id}"
        if key not in self.mapping:
            self.mapping[key] = []
        
        # Check uniqueness to avoid duplicates if re-run
        entry = {
            "source_chat_id": source_chat_id,
            "source_msg_id": source_msg_id,
            "backup_chat_id": backup_chat_id,
            "backup_msg_id": backup_msg_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # If mapping was old format (dict), convert to list
        if isinstance(self.mapping[key], dict):
            self.mapping[key] = [self.mapping[key]]
            
        self.mapping[key].append(entry)
        self._save_mapping()
    
    def get_backup_msgs(self, source_chat_id: int, source_msg_id: int) -> list:
        """获取对应的备份消息信息列表"""
        key = f"{source_chat_id}_{source_msg_id}"
        data = self.mapping.get(key)
        
        if not data:
            return []
            
        if isinstance(data, dict):
            return [data]
            
        return data


class GroupBackupClient:
    """群消息备份客户端"""
    
    def __init__(self, api_id: int, api_hash: str, config: dict, data_dir: Path, logger: logging.Logger,
                 session_name: str = 'group_backup'):
        self.api_id = api_id
        self.api_hash = api_hash
        self.config = config
        self.logger = logger
        self.mapper = MessageMapper(data_dir)
        self.session_file = data_dir / f"{session_name}.session"
        self.client = None
        
        # 解析配置，构建映射关系
        # source_id -> [ {target_id, name, tag} ]
        self.source_map = {}
        # 记录每个目标群组的最后发送者，用于合并消息头
        # target_id -> {last_sender_id, last_time}
        self.chat_states = {}
        
        self._parse_config()
        
    def _parse_config(self):
        """解析配置构建快速查找表"""
        groups = self.config.get('groups', {})
        for target_id, sources in groups.items():
            try:
                target_id = int(target_id)
            except ValueError:
                self.logger.error(f"Invalid target ID: {target_id}")
                continue
                
            for source_id, source_info in sources.items():
                try:
                    source_id = int(source_id)
                except ValueError:
                    self.logger.error(f"Invalid source ID: {source_id}")
                    continue
                    
                if source_id not in self.source_map:
                    self.source_map[source_id] = []
                
                info = source_info or {}
                self.source_map[source_id].append({
                    'target_id': target_id,
                    'name': info.get('name'),
                    'tag': info.get('tag')
                })
                
    def _is_auto_delete_ignored(self, timestamp_str: str) -> bool:
        """检查是否应该忽略自动删除 (基于时间)"""
        if not timestamp_str:
            return False
            
        settings = self.config.get('settings', {})
        ignore_days = settings.get('auto_delete_ignore_days', 30)
        
        try:
            msg_time = datetime.fromisoformat(timestamp_str)
            delta = datetime.now() - msg_time
            return delta.days > ignore_days
        except Exception:
            return False

    async def handle_new_message(self, event):
        """处理新消息"""
        try:
            message = event.message
            if isinstance(message, MessageService):
                return
            
            chat_id = message.chat_id
            if chat_id not in self.source_map:
                return
            
            sender = await message.get_sender()
            sender_id = sender.id if sender else 0
            sender_name = getattr(sender, 'first_name', 'Unknown')
            if hasattr(sender, 'last_name') and sender.last_name:
                sender_name += f" {sender.last_name}"
            
            # 对每个目标群组进行转发
            for target_info in self.source_map[chat_id]:
                target_id = target_info['target_id']
                
                # 检查是否需要发送头部
                state = self.chat_states.get(target_id, {'last_sender_id': 0})
                should_send_header = state['last_sender_id'] != sender_id
                
                # 更新状态
                self.chat_states[target_id] = {'last_sender_id': sender_id}
                
                # 构建消息内容
                msg_content = ""
                
                # 头部 (如果是新发送者)
                if should_send_header:
                    sender_username = f"@{sender.username}" if hasattr(sender, 'username') and sender.username else ""
                    header = f"👤 {sender_name} {sender_username}"
                    
                    # 添加来源群组信息 (如果是多对一/配置了名称)
                    if target_info.get('name'):
                        header += f"\n📢 {target_info['name']}"
                    if target_info.get('tag'):
                        header += f" {target_info['tag']}"
                    
                    msg_content += f"{header}\n"
                
                # 消息主体 (如果有文本)
                if message.text:
                    msg_content += message.text
                
                # 底部时间戳 (右下角风格，这里用简单的换行实现)
                time_str = message.date.strftime('%H:%M')
                msg_content += f"\n\n`{time_str}`"
                
                # 发送/转发
                try:
                    if message.media:
                        # 对于媒体消息，如果没有文本，header作为caption
                        # 如果有文本，header拼接到文本前
                        caption = msg_content if message.text else (msg_content if should_send_header else "")
                        # 媒体消息如果不带header且无文本，也最好加个时间戳caption
                        if not caption:
                             caption = f"`{time_str}`"

                        backup_msg = await self.client.send_file(
                            target_id,
                            message.media,
                            caption=caption
                        )
                    else:
                        backup_msg = await self.client.send_message(
                            target_id,
                            msg_content,
                            link_preview=False
                        )
                    
                    # 记录映射
                    self.mapper.add_mapping(chat_id, message.id, target_id, backup_msg.id)
                    
                except Exception as e:
                    self.logger.error(f"Failed to forward to {target_id}: {e}")

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    async def handle_edited_message(self, event):
        """处理消息编辑"""
        try:
            message = event.message
            chat_id = message.chat_id
            msg_id = message.id
            
            # 获取所有相关备份
            backups = self.mapper.get_backup_msgs(chat_id, msg_id)
            if not backups:
                return
                
            edit_time = datetime.now().strftime('%H:%M')
            
            for backup in backups:
                try:
                    target_id = backup['backup_chat_id']
                    backup_msg_id = backup['backup_msg_id']
                    
                    # 获取原备份消息内容
                    # Telethon的edit_message也可以直接传新内容覆盖
                    # 我们需要重构内容: 保持Header(如果有) + 新内容 + #已修改
                    
                    # 简单起见，我们直接获取当前备份消息(如果在内存中不好拿到，就重新构建)
                    # 重新构建内容稍微麻烦的是Header信息。
                    # 理想情况下，我们应该只修改Text部分。
                    # 但是Telegram Edit API替换整个Text。
                    # 我们可以尝试 fetch 那个备份消息拿到 current text，然后替换 body?
                    # 或者我们可以盲操作：
                    # 如果我们能知道那个备份消息是否有header...
                    # 之前的 `add_mapping` 没有存是否有 header。
                    
                    # 策略: 读取备份消息 ->保留Header -> 替换Body -> 追加Tag
                    
                    params = {}
                    old_backup_msg = await self.client.get_messages(target_id, ids=backup_msg_id)
                    if not old_backup_msg:
                        continue
                        
                    current_text = old_backup_msg.text or ""
                    
                    # 尝试分离 Header
                    # Header 特征: 第一行是 👤 ... 
                    # 分割线是 ─" * 30
                    separator = "─" * 30
                    
                    new_text_body = message.text or ""
                    
                    if separator in current_text:
                        # 有 Header
                        parts = current_text.split(separator, 1)
                        header_part = parts[0] + separator + "\n"
                    else:
                        # 无 Header (或者格式乱了)
                        header_part = ""
                        # 如果没有Header，那原来可能就是纯文本或者接着上一条
                        # 我们尽量保持原样
                    
                    # 拼接新文本
                    # 注意：如果原来有 #已修改 标签，我们要小心不要重复堆叠?
                    # 只要我们是用新的 message.text 重新拼接，就不会堆叠旧的 tag (除了 message.text 本身带的)
                    
                    full_new_text = header_part + new_text_body
                    
                    # 添加 #已修改 tag
                    full_new_text += f"\n\n#已修改 `{edit_time}`"
                    
                    await self.client.edit_message(
                        target_id,
                        backup_msg_id,
                        full_new_text
                    )
                    
                except Exception as e:
                    self.logger.error(f"Failed to edit backup message {backup}: {e}")
                    
        except Exception as e:
            self.logger.error(f"处理编辑消息时出错: {e}", exc_info=True)

    async def handle_deleted_message(self, event):
        """处理消息撤回"""
        try:
            msg_ids = event.deleted_ids
            chat_id = event.chat_id
            
            if not msg_ids or not chat_id:
                return
                
            recall_time = datetime.now().strftime('%H:%M:%S')
            
            for msg_id in msg_ids:
                backups = self.mapper.get_backup_msgs(chat_id, msg_id)
                for backup in backups:
                    # 检查是否忽略自动删除
                    if self._is_auto_delete_ignored(backup.get('timestamp')):
                        self.logger.info(f"忽略自动删除: {msg_id} (时间: {backup.get('timestamp')})")
                        continue
                    
                    target_id = backup['backup_chat_id']
                    backup_msg_id = backup['backup_msg_id']
                    
                    try:
                        # 1. 修改原消息，打上 #已撤回 标签
                        # 获取原消息以保持Header
                        old_backup_msg = await self.client.get_messages(target_id, ids=backup_msg_id)
                        if old_backup_msg:
                            current_text = old_backup_msg.text or ""
                            # 追加标签 (简单追加即可，不去重，表示多次撤回?)
                            # 或者是替换？
                            # 既然已经撤回，意味着原内容没了。但在备份里我们希望保留原内容！
                            # 所以只是 Append Tag。
                            
                            new_text = current_text + f"\n\n#已撤回 `{recall_time}`"
                            await self.client.edit_message(target_id, backup_msg_id, new_text)
                        
                        # 2. 发送警告回复 (保持原有逻辑)
                        warning_text = (
                            f"⚠️ 消息已被撤回 ⚠️\n"
                            f"🕐 撤回时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            # f"📝 原消息ID: {msg_id}" # 用户说"信息id就没必要显示了"
                        )
                        
                        await self.client.send_message(
                            target_id,
                            warning_text,
                            reply_to=backup_msg_id
                        )
                        
                    except Exception as e:
                        self.logger.error(f"处理撤回消息失败 {backup}: {e}")
                        
        except Exception as e:
            self.logger.error(f"处理撤回事件时出错: {e}", exc_info=True)

    async def start(self):
        """启动客户端"""
        self.logger.info("Starting backup bot...")
        
        self.client = TelegramClient(
            str(self.session_file),
            self.api_id,
            self.api_hash
        )
        
        await self.client.start()
        
        # Collect source chats
        source_chats = list(self.source_map.keys())
        self.logger.info(f"Monitoring {len(source_chats)} source groups: {source_chats}")
        
        @self.client.on(events.NewMessage(chats=source_chats))
        async def handler_new(event):
            await self.handle_new_message(event)
            
        @self.client.on(events.MessageEdited(chats=source_chats))
        async def handler_edit(event):
            await self.handle_edit_message(event) # Configure this
            
        @self.client.on(events.MessageDeleted(chats=source_chats))
        async def handler_delete(event):
            await self.handle_deleted_message(event)

        self.logger.info("Client started.")
        await self.client.run_until_disconnected()

    def run(self):
        asyncio.run(self.start())



def main():
    """主函数"""
    # 解析参数
    args = parse_args()
    
    # 设置日志
    logger = setup_logging(args.session_name, args.log_dir)
    
    # 设置数据目录
    if args.data_dir is None:
        data_dir = Path("/data") / "bot" / args.session_name
    else:
        data_dir = Path(args.data_dir)
    
    # 从环境变量获取配置
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    source_chat_id = os.getenv("SOURCE_CHAT_ID")
    backup_chat_id = os.getenv("BACKUP_CHAT_ID")
    
    # 验证配置
    if not api_id:
        logger.error("未设置 TELEGRAM_API_ID 环境变量")
        logger.error("请访问 https://my.telegram.org 获取 API ID 和 API Hash")
        sys.exit(1)
    
    if not api_hash:
        logger.error("未设置 TELEGRAM_API_HASH 环境变量")
        logger.error("请访问 https://my.telegram.org 获取 API ID 和 API Hash")
        sys.exit(1)
    
    if not source_chat_id:
        logger.error("未设置 SOURCE_CHAT_ID 环境变量")
        sys.exit(1)
    
    if not backup_chat_id:
        logger.error("未设置 BACKUP_CHAT_ID 环境变量")
        sys.exit(1)
    
    try:
        api_id = int(api_id)
        source_chat_id = int(source_chat_id)
        backup_chat_id = int(backup_chat_id)
    except ValueError:
        logger.error("API_ID, SOURCE_CHAT_ID 和 BACKUP_CHAT_ID 必须是整数")
        sys.exit(1)
    
    # 创建并运行客户端
    client = GroupBackupClient(
        api_id=api_id,
        api_hash=api_hash,
        source_chat_id=source_chat_id,
        backup_chat_id=backup_chat_id,
        data_dir=data_dir,
        logger=logger,
        session_name=args.session_name
    )
    
    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("程序已停止")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
