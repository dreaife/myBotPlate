import logging
import pytz
import asyncio
from datetime import datetime
from telethon.tl.types import MessageService, MessageMediaWebPage, Message

class MessageHandler:
    """处理消息逻辑"""
    
    def __init__(self, client, config, mapper, chat_states):
        self.client = client
        self.config = config
        self.mapper = mapper
        self.chat_states = chat_states
        self.logger = logging.getLogger(__name__)
        self._queues = {}
        self._workers = {}

    async def _get_queue(self, target_id):
        if target_id not in self._queues:
            self._queues[target_id] = asyncio.Queue()
            self._workers[target_id] = asyncio.create_task(self._worker_loop(target_id))
        return self._queues[target_id]

    async def _worker_loop(self, target_id):
        queue = await self._get_queue(target_id)
        while True:
            try:
                task_type, args = await queue.get()
                try:
                    if task_type == 'new':
                        await self._process_single_target(*args)
                    elif task_type == 'edit':
                        await self._process_edit_target(*args)
                    elif task_type == 'delete':
                        await self._process_delete_target(*args)
                except Exception as e:
                    self.logger.error(f"Worker {target_id} error processing {task_type}: {e}", exc_info=True)
                finally:
                    queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Worker {target_id} critical error: {e}", exc_info=True)
                await asyncio.sleep(1)

    def _get_topic_id(self, message):
        """Get the topic ID of the message if applicable"""
        if not hasattr(message, 'reply_to') or not message.reply_to:
            return None
        
        # In Telethon, reply_to attribute can check for forum topic
        # reply_to_top_id is usually the topic ID for forum messages
        # reply_to_msg_id might be topic ID if it is a direct reply to the topic creation message
        if getattr(message.reply_to, 'forum_topic', False):
             return message.reply_to.reply_to_top_id or message.reply_to.reply_to_msg_id
        return None

    async def handle_new_message(self, event, target_info_list):
        """处理新消息分发"""
        try:
            message = event.message
            if isinstance(message, MessageService):
                return
            
            chat_id = message.chat_id
            # sender fetching moved to worker to speed up dispatch
            
            # Get message topic ID (if any)
            msg_topic_id = self._get_topic_id(message)
            
            # 对每个目标群组进行转发
            for target_info in target_info_list:
                # Source Topic Filtering
                source_topic_id = target_info.get('source_topic_id')
                if source_topic_id is not None:
                    if msg_topic_id != source_topic_id:
                        continue
                        
                target_id = target_info['target_id']
                target_topic_id = target_info.get('target_topic_id')
                queue_key = (target_id, target_topic_id)
                self.logger.info(f"Queuing msg {message.id} from {chat_id} to {queue_key}")
                queue = await self._get_queue(queue_key)
                await queue.put(('new', (message, target_id, target_info)))
                
        except Exception as e:
            self.logger.error(f"处理新消息失败: {e}", exc_info=True)

    async def _process_single_target(self, message, target_id, target_info):
        """处理单个目标的转发逻辑"""
        try:
            sender = await message.get_sender()
        except Exception as e:
            self.logger.warning(f"Failed to get sender for {message.id}: {e}")
            sender = None
            
        sender_id = sender.id if sender else 0

        sender_name = getattr(sender, 'first_name', 'Unknown')
        if hasattr(sender, 'last_name') and sender.last_name:
            sender_name += f" {sender.last_name}"
            
        # 检查是否需要发送头部
        target_topic_id = target_info.get('target_topic_id')
        state_key = (target_id, target_topic_id) if target_topic_id else target_id

        # 检查是否需要发送头部
        state = self.chat_states.get(state_key, {'last_sender_id': 0})
        should_send_header = state['last_sender_id'] != sender_id
        
        # 更新状态
        self.chat_states[state_key] = {'last_sender_id': sender_id}
        
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
            avatar_icon = self._build_avatar_icon(sender_name)
            header = f"{avatar_icon} {sender_name} {sender_username}"
            
            if target_info.get('name'):
                header += f"\n📢 {target_info['name']}"
            if target_info.get('tag'):
                header += f" {target_info['tag']}"
            
            header += f"\n🕐 {time_str_full} ({timezone_str})\n"
            
            if message.edit_date:
                header += "✏️ (已编辑)\n"
            
            header += separator
        elif not is_rich_media:
             # 非第一条且非媒体 -> 不加分隔线
             header = ""

        # 构建内容 (Header + Text + Footer)
        msg_content = header
        if message.text:
            msg_content += message.text

        # Footer (时间戳) - 仅当不是Header模式显示时间时
        if not should_send_header and not is_rich_media:
             msg_content += f"\n\n`{time_str_full}`"

        # 查找回复
        reply_to = self._find_reply_to(message.chat_id, message.reply_to_msg_id, target_id)
        
        # 如果未找到回复对象，且指定了目标 Topic，则回复到 Topic ID
        target_topic_id = target_info.get('target_topic_id')
        if not reply_to and target_topic_id:
            reply_to = target_topic_id

        # 发送
        backup_msg = None
        if message.media:
            backup_msg = await self._send_media(target_id, message, msg_content, should_send_header, time_str_full, reply_to)
        else:
            backup_msg = await self._send_text(target_id, msg_content, reply_to)
            
        # 记录映射
        if backup_msg:
             target_topic_id = target_info.get('target_topic_id')
             self.mapper.add_mapping(
                message.chat_id, 
                message.id,
                target_id, 
                backup_msg.id,
                target_topic_id
            )

    async def _send_media(self, target_id, message, msg_content, should_send_header, time_str, reply_to):
        """发送媒体消息"""
        if isinstance(message.media, MessageMediaWebPage):
            return await self.client.send_message(
                target_id,
                msg_content or "",
                link_preview=True,
                reply_to=reply_to
            )
        is_media_only = bool(message.media and not message.text)
        # 对于媒体消息，如果没有文本，header作为caption
        # 如果有文本，header拼接到文本前
        caption = msg_content if message.text else (msg_content if should_send_header else "")
        # 媒体消息如果不带header且无文本，加时间戳caption
        if not caption and not should_send_header: 
                caption = f"`{time_str}`"
        if is_media_only and should_send_header:
            backup_msg = await self.client.send_file(
                target_id,
                message.media,
                reply_to=reply_to
            )
            if msg_content:
                await self.client.send_message(
                    target_id,
                    msg_content,
                    link_preview=False,
                    reply_to=backup_msg.id
                )
            return backup_msg

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

    def _build_avatar_icon(self, sender_name):
        """使用文本图标模拟头像显示。"""
        if sender_name:
            return f"🧑[{sender_name[0]}]"
        return "🧑"

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

    async def handle_edit_message(self, event, target_info_list):
        """处理消息编辑"""
        try:
            msg = event.message
            chat_id = msg.chat_id
            msg_id = msg.id
            
            # Use Mapping to determine where to send edits
            backups = self.mapper.get_backup_msgs(chat_id, msg_id)
            if not backups:
                return

            # Deduplicate by queue to avoid sending same edit multiple times to same queue?
            # Actually each backup entry corresponds to a specific message on a specific target.
            # We should dispatch individual tasks for each backup entry.
            
            for backup in backups:
                target_id = backup['backup_chat_id']
                topic_id = backup.get('target_topic_id')
                queue_key = (target_id, topic_id)
                
                queue = await self._get_queue(queue_key)
                await queue.put(('edit', (msg, target_id, backup))) # Pass backup entry instead of target_info

        except Exception as e:
            self.logger.error(f"Error dispatching edit: {e}", exc_info=True)

    async def _process_edit_target(self, msg, target_id, backup_entry):
            # Worker now receives specific backup entry
            # No need to iterate all backups again or check IDs
            
            # Verify target_id matches (should match as dispatched by key)
            if str(backup_entry['backup_chat_id']) != str(target_id):
                return

            backup_msg_id = backup_entry['backup_msg_id']
            # ... process edit ...
            try:
                    # 在原消息后追加编辑记录
                    current_backup = await self.client.get_messages(target_id, ids=backup_msg_id)
                    if current_backup:
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
                            f"🕐 修改时间: {edit_time_str} ({timezone_str})\n"
                            f"{edited_text}"
                        )
                        current_text = current_backup.text or ""
                        
                        # Avoid duplicate edits check
                        if edit_entry in current_text:
                            return 

                        new_text = f"{current_text}\n\n{edit_entry}" if current_text else edit_entry
                        await self.client.edit_message(target_id, backup_msg_id, new_text)
                            
            except Exception as e:
                    self.logger.error(f"编辑消息失败 {backup_entry}: {e}")

    async def handle_deleted_message(self, event, target_info_list):
        """处理消息撤回"""
        try:
            msg_ids = event.deleted_ids
            chat_id = event.chat_id
            
            if not msg_ids or not chat_id:
                return
                
            for msg_id in msg_ids:
                backups = self.mapper.get_backup_msgs(chat_id, msg_id)
                for backup in backups:
                    target_id = backup['backup_chat_id']
                    topic_id = backup.get('target_topic_id')
                    queue_key = (target_id, topic_id)
                    
                    queue = await self._get_queue(queue_key)
                    # Pass list of ONE backup entry to keep processing logic simple or adapt?
                    # Original logic processed list of msg_ids.
                    # Adapting to process single backup entry is cleaner.
                    await queue.put(('delete', ([msg_id], chat_id, target_id, backup))) 

        except Exception as e:
            self.logger.error(f"Error dispatching delete: {e}", exc_info=True)

    async def _process_delete_target(self, msg_ids, chat_id, target_id, backup_entry=None):
            recall_time = datetime.now().strftime('%H:%M:%S')
            
            # If backup_entry provided, use it directly (optimized path)
            if backup_entry:
                try:
                    target_id = backup_entry['backup_chat_id']
                    backup_msg_id = backup_entry['backup_msg_id']
                    
                    if self._is_auto_delete_ignored(backup_entry.get('timestamp')):
                            return

                    # 尝试编辑
                    try:
                        old_msg = await self.client.get_messages(target_id, ids=backup_msg_id)
                        if old_msg:
                            text = old_msg.text or ""
                            # Check if already recalled
                            if "#已撤回" in text:
                                return
                            await self.client.edit_message(target_id, backup_msg_id, text + f"\n\n#已撤回 `{recall_time}`")
                            
                        # 发送警告
                        await self.client.send_message(
                            target_id, 
                            f"⚠️ 消息已被撤回 ⚠️\n🕐 撤回时间: {recall_time}",
                            reply_to=backup_msg_id
                        )
                    except Exception as e:
                         # 失败告警
                         await self.client.send_message(
                            target_id, 
                            f"⚠️ 消息已被撤回 ⚠️\n🕐 撤回时间: {recall_time}\n#已撤回",
                            reply_to=backup_msg_id
                        )
                except Exception as e:
                     self.logger.error(f"Delete processing failed: {e}")
                return

            # Legacy / Fallback path (should not be hit with new dispatcher)
            pass

    def _is_auto_delete_ignored(self, timestamp_str):
        if not timestamp_str: return False
        try:
             settings = self.config.get('settings', {})
             ignore_days = settings.get('auto_delete_ignore_days', 30)
             msg_time = datetime.fromisoformat(timestamp_str)
             return (datetime.now() - msg_time).days >= ignore_days
        except:
             return False
