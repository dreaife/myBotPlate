import logging
import pytz
from datetime import datetime
from telethon.tl.types import MessageService, MessageMediaWebPage

class MessageHandler:
    """处理消息逻辑"""
    
    def __init__(self, client, config, mapper, chat_states):
        self.client = client
        self.config = config
        self.mapper = mapper
        self.chat_states = chat_states
        self.logger = logging.getLogger(__name__)

    async def handle_new_message(self, event, target_info_list):
        """处理新消息分发"""
        try:
            message = event.message
            if isinstance(message, MessageService):
                return
            
            chat_id = message.chat_id
            sender = await message.get_sender()
            sender_id = sender.id if sender else 0
            
            # 对每个目标群组进行转发
            for target_info in target_info_list:
                target_id = target_info['target_id']
                await self._process_single_target(message, sender, target_id, target_info)
                
        except Exception as e:
            self.logger.error(f"处理新消息失败: {e}", exc_info=True)

    async def _process_single_target(self, message, sender, target_id, target_info):
        """处理单个目标的转发逻辑"""
        sender_id = sender.id if sender else 0
        sender_name = getattr(sender, 'first_name', 'Unknown')
        if hasattr(sender, 'last_name') and sender.last_name:
            sender_name += f" {sender.last_name}"
            
        # 检查是否需要发送头部
        state = self.chat_states.get(target_id, {'last_sender_id': 0})
        should_send_header = state['last_sender_id'] != sender_id
        
        # 更新状态
        self.chat_states[target_id] = {'last_sender_id': sender_id}
        
        # 获取配置时区
        timezone_str = self.config.get('settings', {}).get('timezone', 'Asia/Tokyo')
        try:
            tz = pytz.timezone(timezone_str)
        except Exception:
            tz = pytz.utc
        
        # 转换时间
        msg_date = message.date.astimezone(tz)
        time_str_full = msg_date.strftime('%Y-%m-%d %H:%M:%S') # HEADER / FOOTER
        
        # 判断是否为富媒体消息
        is_rich_media = bool(message.media and not isinstance(message.media, MessageMediaWebPage))

        # 定义分隔线
        separator = "" if is_rich_media else ("─" * 30 + "\n")

        # 构建 Header
        header = ""
        if should_send_header:
            sender_username = f"@{sender.username}" if hasattr(sender, 'username') and sender.username else ""
            header = f"👤 {sender_name} {sender_username}"
            
            if target_info.get('name'):
                header += f"\n📢 {target_info['name']}"
            if target_info.get('tag'):
                header += f" {target_info['tag']}"
            
            header += f"\n🕐 {time_str_full} ({timezone_str})\n"
            
            if message.edit_date:
                header += "✏️ (已编辑)\n"
            
            header += separator
        elif not is_rich_media:
             # 非第一条且非媒体 -> 加分隔线
             header = separator

        # 构建内容 (Header + Text + Footer)
        msg_content = header
        if message.text:
            msg_content += message.text
        
        # Footer (时间戳) - 仅当不是Header模式显示时间时
        if not should_send_header and not is_rich_media:
             msg_content += f"\n\n`{time_str_full}`"

        # 查找回复
        reply_to = self._find_reply_to(message.chat_id, message.reply_to_msg_id, target_id)

        # 发送
        backup_msg = None
        if message.media:
            backup_msg = await self._send_media(target_id, message, msg_content, should_send_header, time_str_full, reply_to)
        else:
            backup_msg = await self._send_text(target_id, msg_content, reply_to)
            
        # 记录映射
        if backup_msg:
             self.mapper.add_mapping(
                message.chat_id, 
                message.id,
                target_id, 
                backup_msg.id
            )

    async def _send_media(self, target_id, message, msg_content, should_send_header, time_str, reply_to):
        """发送媒体消息"""
        # 对于媒体消息，如果没有文本，header作为caption
        # 如果有文本，header拼接到文本前
        caption = msg_content if message.text else (msg_content if should_send_header else "")
        # 媒体消息如果不带header且无文本，加时间戳caption
        if not caption and not should_send_header: 
                caption = f"`{time_str}`"

        return await self.client.send_file(
            target_id,
            message.media,
            caption=caption,
            reply_to=reply_to
        )

    async def _send_text(self, target_id, content, reply_to):
        """发送文本消息"""
        return await self.client.send_message(
            target_id,
            content,
            link_preview=False,
            reply_to=reply_to
        )

    def _find_reply_to(self, chat_id, reply_to_msg_id, target_id):
        """查找回复目标ID"""
        if not reply_to_msg_id:
            return None
            
        backup_msgs = self.mapper.get_backup_msgs(chat_id, reply_to_msg_id)
        for bm in backup_msgs:
            # Coerce to string for safe comparison (JSON ids might be loaded as int or str)
            # target_id is usually int from core.py
            bm_target_id = bm.get('backup_chat_id')
            if str(bm_target_id) == str(target_id):
                return bm.get('backup_msg_id')
        return None

    async def handle_edit_message(self, event):
        """处理消息编辑"""
        try:
            msg = event.message
            chat_id = msg.chat_id
            msg_id = msg.id
            
            backups = self.mapper.get_backup_msgs(chat_id, msg_id)
            if not backups:
                return
                
            for backup in backups:
                try:
                    target_id = backup['backup_chat_id']
                    backup_msg_id = backup['backup_msg_id']
                    
                    # 简单处理: 在原消息后追加 (已修改) 
                    # 复杂处理需要重建text，但这很难因为不知道原始Header格式
                    # 这里保持原有逻辑: 追加TAG
                    # Get current message logic is complex. 
                    # Simply appending tag is safer.
                    
                    # NOTE: current logic in bot was complex edit. 
                    # Let's try to append tag if not present.
                    current_backup = await self.client.get_messages(target_id, ids=backup_msg_id)
                    if current_backup and current_backup.text:
                        timezone_str = self.config.get('settings', {}).get('timezone', 'Asia/Tokyo')
                        try:
                            tz = pytz.timezone(timezone_str)
                        except Exception:
                            tz = pytz.utc

                        edit_time = msg.edit_date.astimezone(tz) if msg.edit_date else datetime.now(tz)
                        edit_time_str = edit_time.strftime('%Y-%m-%d %H:%M:%S')
                        edited_text = msg.text or ""
                        edit_entry = (
                            "----\n"
                            f"{edit_time_str} ({timezone_str})\n"
                            f"{edited_text}"
                        )
                        if edit_entry in current_backup.text:
                            continue
                        new_text = f"{current_backup.text}\n{edit_entry}"
                        await self.client.edit_message(target_id, backup_msg_id, new_text)
                            
                except Exception as e:
                    self.logger.error(f"编辑消息失败 {backup}: {e}")
                    
        except Exception as e:
            self.logger.error(f"处理编辑消息失败: {e}")

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
                    if self._is_auto_delete_ignored(backup.get('timestamp')):
                         continue

                    target_id = backup['backup_chat_id']
                    backup_msg_id = backup['backup_msg_id']
                    
                    try:
                        # 尝试编辑
                        # NOTE: Simplified logic for brevity in refactor
                        old_msg = await self.client.get_messages(target_id, ids=backup_msg_id)
                        if old_msg:
                            text = old_msg.text or ""
                            await self.client.edit_message(target_id, backup_msg_id, text + f"\n\n#已撤回 `{recall_time}`")
                            
                        # 发送警告 (保持原有逻辑)
                        await self.client.send_message(
                            target_id, 
                            f"⚠️ 消息已被撤回 ⚠️\n🕐 撤回时间: {recall_time}",
                            reply_to=backup_msg_id
                        )
                    except Exception as e:
                        # 如编辑失败(超时)，发送带tag的警告
                         await self.client.send_message(
                            target_id, 
                            f"⚠️ 消息已被撤回 ⚠️\n🕐 撤回时间: {recall_time}\n#已撤回",
                            reply_to=backup_msg_id
                        )
                        
        except Exception as e:
            self.logger.error(f"处理撤回消息失败: {e}")

    def _is_auto_delete_ignored(self, timestamp_str):
        if not timestamp_str: return False
        try:
             settings = self.config.get('settings', {})
             ignore_days = settings.get('auto_delete_ignore_days', 30)
             msg_time = datetime.fromisoformat(timestamp_str)
             return (datetime.now() - msg_time).days >= ignore_days
        except:
             return False
