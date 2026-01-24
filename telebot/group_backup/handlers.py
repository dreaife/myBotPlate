import logging
import pytz
import asyncio
from datetime import datetime
from telethon.tl.types import MessageService, MessageMediaWebPage, Message, UpdateMessageReactions
from telethon.tl.functions.messages import SendReactionRequest

class MessageHandler:
    """处理消息逻辑"""
    
    def __init__(self, client, config, mapper, chat_states):
        self.client = client
        self.config = config
        self.mapper = mapper
        self.chat_states = chat_states
        self.logger = logging.getLogger(__name__)
        self.logger = logging.getLogger(__name__)
        self._queues = {}
        self._workers = {}
        self._album_buffers = {} # Key: (queue_key, grouped_id) -> [messages]
        self.focus_users = self._parse_focus_users()

    def _parse_focus_users(self):
        raw = self.config.get('settings', {}).get('focus_users', [])
        focused = set()
        for u in raw:
            if isinstance(u, int):
                focused.add(u)
            elif isinstance(u, str):
                focused.add(u.lstrip('@').lower())
        return focused

    def _get_queue_key(self, target_info):
        target_id = target_info['target_id']
        target_topic_id = target_info.get('target_topic_id')
        return (target_id, target_topic_id)

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
                    elif task_type == 'album':
                        await self._process_album_target(*args)
                    elif task_type == 'album':
                        await self._process_album_target(*args)
                    elif task_type == 'edit':
                        await self._process_edit_target(*args)
                    elif task_type == 'delete':
                        await self._process_delete_target(*args)
                    elif task_type == 'reaction':
                        await self._process_reaction_target(*args)
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
                queue_key = self._get_queue_key(target_info)
                
                if message.grouped_id:
                    # Handle Album
                    await self._handle_grouped_message(message, target_info, queue_key)
                else:
                    self.logger.info(f"Queuing msg {message.id} from {chat_id} to {queue_key}")
                    queue = await self._get_queue(queue_key)
                    await queue.put(('new', (message, target_id, target_info)))
        except Exception as e:
            self.logger.error(f"处理新消息失败: {e}", exc_info=True)

    async def _handle_grouped_message(self, message, target_info, queue_key):
        """Buffer grouped messages and schedule flush"""
        grouped_id = message.grouped_id
        buffer_key = (queue_key, grouped_id)
        
        if buffer_key not in self._album_buffers:
            self._album_buffers[buffer_key] = []
            # Schedule flush
            asyncio.create_task(self._flush_album(buffer_key, target_info, queue_key))
            
        self._album_buffers[buffer_key].append(message)

    async def _flush_album(self, buffer_key, target_info, queue_key):
        """Wait for album to complete then collect and queue"""
        # Wait for other parts to arrive
        await asyncio.sleep(2.0)
        
        messages = self._album_buffers.pop(buffer_key, [])
        if not messages:
            return
            
        # Sort by message ID to ensure order
        messages.sort(key=lambda m: m.id)
        
        target_id = target_info['target_id']
        self.logger.info(f"Queuing album {buffer_key[1]} ({len(messages)} msgs) to {queue_key}")
        
        queue = await self._get_queue(queue_key)
        await queue.put(('album', (messages, target_id, target_info)))

    def _get_fwd_sig(self, message):
        """Get unique signature for forward source to detect context changes"""
        if not message.fwd_from:
            return None
        # Telethon Peer objects str() are unique enough (e.g. PeerUser(id=123))
        if message.fwd_from.from_id:
            return str(message.fwd_from.from_id)
        if message.fwd_from.from_name:
            return message.fwd_from.from_name
        return "unknown_forward"

    async def _process_single_target(self, message, target_id, target_info):
        """处理单个目标的转发逻辑"""
        try:
            sender = await message.get_sender()
            try:
                chat = await message.get_chat()
            except Exception:
                chat = None
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

        # Get fwd signature
        fwd_sig = self._get_fwd_sig(message)

        # 检查是否需要发送头部
        state = self.chat_states.get(state_key, {'last_sender_id': 0, 'last_fwd_sig': None})
        
        last_sender = state.get('last_sender_id')
        last_fwd = state.get('last_fwd_sig')
        
        should_send_header = (last_sender != sender_id) or (last_fwd != fwd_sig)
        
        # 更新状态
        self.chat_states[state_key] = {'last_sender_id': sender_id, 'last_fwd_sig': fwd_sig}
        
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

        header = ""
        if should_send_header:
            header = self._build_message_header(sender, target_info, msg_date, timezone_str, chat, message.id, bool(message.edit_date), message.fwd_from)
            # Remove separator if rich media?
            # Original logic: separator = "" if is_rich_media else ...
            if is_rich_media:
                 header = header.replace("─" * 30 + "\n", "")

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

    async def _process_album_target(self, messages, target_id, target_info):
        """处理相册转发"""
        if not messages: return
        
        # Use first message for header/metadata info
        first_msg = messages[0]
        
        # Fetch sender (try first msg)
        try:
            sender = await first_msg.get_sender()
            try:
                chat = await first_msg.get_chat()
            except Exception:
                chat = None
        except:
            sender = None
        sender_id = sender.id if sender else 0
        sender_name = getattr(sender, 'first_name', 'Unknown')
        if hasattr(sender, 'last_name') and sender.last_name:
            sender_name += f" {sender.last_name}"

        # Setup State & Header
        queue_key = self._get_queue_key(target_info)
        
        # Get fwd signature
        fwd_sig = self._get_fwd_sig(first_msg)

        state = self.chat_states.get(queue_key, {'last_sender_id': 0, 'last_fwd_sig': None})
        last_sender = state.get('last_sender_id')
        last_fwd = state.get('last_fwd_sig')
        
        should_send_header = (last_sender != sender_id) or (last_fwd != fwd_sig)
        
        self.chat_states[queue_key] = {'last_sender_id': sender_id, 'last_fwd_sig': fwd_sig}

        # Time Info
        timezone_str = self.config.get('settings', {}).get('timezone', 'Asia/Tokyo')
        try:
            tz = pytz.timezone(timezone_str)
        except:
            tz = pytz.utc
        msg_date = first_msg.date.astimezone(tz)
        time_str_full = msg_date.strftime('%Y-%m-%d %H:%M:%S')

        # Build Header
        header = ""
        if should_send_header:
            header = self._build_message_header(
                sender, target_info, msg_date, timezone_str, 
                chat, first_msg.id, bool(first_msg.edit_date), first_msg.fwd_from
            )
            # Albums are always rich media, so strip separator
            header = header.replace("─" * 30 + "\n", "")
            # Add extra newline for visual separation in caption
            header += "\n"

        # Combine Text/Captions
        # Logic: Concatenate all unique texts? Or just put header on first?
        # Telegram albums share one caption usually, or separate?
        # Actually client.send_file with list accepts 'caption' as str (for first) or list.
        # We will put Header + Msg1 Text on first image.
        # Subsequent images: their own text if any.
        
        # NOTE: Telegram API allows caption per media.
        # We will attempt to preserve captions.
        captions = []
        for i, m in enumerate(messages):
            cap = m.text or ""
            if i == 0:
                # Add Header to first message
                cap = header + cap
                # Add footer if needed? (Usually albums don't have footer seps)
                if not should_send_header:
                     # If continuation, maybe add small time tag?
                     # cap += f"\n`{time_str_full}`"
                     pass
            captions.append(cap)
            
        # Reply Target
        reply_to = self._find_reply_to(first_msg.chat_id, first_msg.reply_to_msg_id, target_id)
        if not reply_to and target_info.get('target_topic_id'):
            reply_to = target_info.get('target_topic_id')
            
        # Extract media
        media_list = [m.media for m in messages]
        
        try:
            sent_messages = await self.client.send_file(
                target_id,
                media_list,
                caption=captions,
                reply_to=reply_to
            )
            
            # If single file sent (not list), wrap it
            if not isinstance(sent_messages, list):
                sent_messages = [sent_messages]
                
            # Map messages
            # Assuming 1-to-1 mapping order is preserved by Telegram
            if len(sent_messages) == len(messages):
                for i, sent_m in enumerate(sent_messages):
                    orig_m = messages[i]
                    self.mapper.add_mapping(
                        orig_m.chat_id,
                        orig_m.id,
                        target_id,
                        sent_m.id,
                        target_info.get('target_topic_id')
                    )
            else:
                self.logger.warning(f"Album count mismatch: sent {len(sent_messages)}, orig {len(messages)}")
                
        except Exception as e:
            self.logger.error(f"Failed to send album to {target_id}: {e}", exc_info=True)


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

    def _build_message_header(self, sender, target_info, msg_date, timezone_str, chat, message_id, is_edit=False, fwd_from=None):
        sender_name = getattr(sender, 'first_name', 'Unknown')
        if hasattr(sender, 'last_name') and sender.last_name:
            sender_name += f" {sender.last_name}"
        
        is_focused = False
        if sender:
            # Combine all focus users
            current_focus_set = self.focus_users.copy() # Global
            
            # Source Level
            source_focus = target_info.get('source_focus_users', [])
            current_focus_set.update(self._parse_raw_users(source_focus))
            
            # Target Level
            target_focus = target_info.get('target_focus_users', [])
            current_focus_set.update(self._parse_raw_users(target_focus))
            
            if sender.id in current_focus_set:
                is_focused = True
            elif hasattr(sender, 'username') and sender.username and sender.username.lower() in current_focus_set:
                is_focused = True
                
        if is_focused:
            sender_name = f"**{sender_name}**"
        
        sender_username = f"@{sender.username}" if hasattr(sender, 'username') and sender.username else ""
        avatar_icon = self._build_avatar_icon(sender_name)
        header = f"{avatar_icon} {sender_name} {sender_username}"
        
        if target_info.get('name'):
            header += f"\n📢 {target_info['name']}"
        if target_info.get('tag'):
            header += f" {target_info['tag']}"
        
        time_str_full = msg_date.strftime('%Y-%m-%d %H:%M:%S')
        header += f"\n🕐 {time_str_full} ({timezone_str})\n"
        
        if chat:
            link = ""
            if getattr(chat, "username", None):
                link = f"https://t.me/{chat.username}/{message_id}"
            else:
                cid = str(chat.id)
                if cid.startswith("-100"):
                    cid = cid[4:]
                elif cid.startswith("-"):
                    cid = cid[1:]
                if cid:
                     link = f"https://t.me/c/{cid}/{message_id}"
            
            if link:
                header += f"🔗 [跳转原文]({link})\n"
        
        if is_edit:
            header += "✏️ (已编辑)\n"

        if fwd_from:
            try:
                fwd_name = fwd_from.from_name
                # Fallback to implicit handling for hidden senders if needed
                if fwd_name:
                     header += f"↩️ 转发自: {fwd_name}\n"
                else:
                     header += "↩️ 转发消息\n"
            except:
                header += "↩️ 转发消息\n"

        return header + ("─" * 30 + "\n")

    def _parse_raw_users(self, raw_list):
        parsed = set()
        for u in raw_list:
            if isinstance(u, int):
                parsed.add(u)
            elif isinstance(u, str):
                parsed.add(u.lstrip('@').lower())
        return parsed

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
            original_update = getattr(event, 'original_update', None)
            # Filter out Reaction updates that might trigger MessageEdited
            if isinstance(original_update, UpdateMessageReactions) or \
               (original_update and type(original_update).__name__ == 'UpdateMessageReactions'):
                return

            msg = event.message
            chat_id = msg.chat_id
            msg_id = msg.id
            
            update_type = type(original_update).__name__ if original_update else "Unknown"
            # 降低日志级别，并记录 Update 类型以便排查
            self.logger.debug(f"Message update received (checking for edit): Source {chat_id} Msg {msg_id} Type: {update_type}")

            # Filter out events without edit_date (e.g. spurious updates or reactions interpreted as edits)
            if not msg.edit_date:
                self.logger.debug(f"Ignored edit event without edit_date: {msg_id}")
                return

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
            self.logger.info(f"Processing edit for Target {target_id} BackupEntry {backup_entry.get('backup_msg_id')}")

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
                        
                        # Strict De-duplication Logic
                        should_skip = False
                        
                        # Case 1: Already has edits. Check the LAST edit entry.
                        if "\n----\n" in current_text:
                            last_segment = current_text.split("\n----\n")[-1]
                            # Remove the Time header line from segment
                            # Format: "🕐 修改时间: ...\nContent"
                            if "🕐 修改时间:" in last_segment:
                                try:
                                    # Split by first newline after time
                                    # Find first newline
                                    first_nl = last_segment.find('\n')
                                    if first_nl != -1:
                                        last_content = last_segment[first_nl+1:]
                                        if last_content.strip() == edited_text.strip():
                                            should_skip = True
                                except:
                                    pass
                        else:
                            # Case 2: No edits yet. Compare against original.
                            # Requires knowing the separator or structure.
                            # Original: Header + Separator + Text + (Footer)
                            # Separator: "─" * 30 + "\n"
                            separator = "─" * 30 + "\n"
                            
                            clean_current = current_text
                            if separator in clean_current:
                                clean_current = clean_current.split(separator)[-1]
                            
                            # Remove Footer if present (Footer is time `202X-...`)
                            # It's hard to distinguish footer from text.
                            # But if matches exactly, good.
                            if clean_current.strip() == edited_text.strip():
                                should_skip = True
                            
                            # Fallback: If `edited_text` is present in `clean_current` EXACTLY (wrap check?)
                            # If edited_text equals clean_current WITHOUT the footer?
                            # Assume footer is short timestamp.
                            # If clean_current starts with edited_text?
                            if clean_current.strip().startswith(edited_text.strip()):
                                 should_skip = True

                        if should_skip:
                            self.logger.debug(f"Edit skipped (Duplicate content) for {backup_msg_id}")
                            return 

                        self.logger.info(f"Applying edit to {backup_msg_id}")
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

    async def handle_reaction(self, event, target_info_list):
        """处理表情反应"""
        try:
            msg_id = event.msg_id
            chat_id = event.chat_id
            self.logger.info(f"Reaction event received: Source {chat_id} Msg {msg_id}")

            # We need to map Source Msg ID -> Target Msg ID
            backups = self.mapper.get_backup_msgs(chat_id, msg_id)
            if not backups:
                return
                
            # Dispatch
            for backup in backups:
                target_id = backup['backup_chat_id']
                topic_id = backup.get('target_topic_id')
                queue_key = (target_id, topic_id)
                
                queue = await self._get_queue(queue_key)
                await queue.put(('reaction', (event, target_id, backup)))

        except Exception as e:
            self.logger.error(f"Error dispatching reaction: {e}")

    async def _process_reaction_target(self, event, target_id, backup_entry):
        try:
            self.logger.info(f"Processing reaction for Target {target_id} BackupEntry {backup_entry.get('backup_msg_id')}")
            # Check ID
            if str(backup_entry['backup_chat_id']) != str(target_id):
                return
            
            backup_msg_id = backup_entry['backup_msg_id']
            # Get reaction
            # The event object varies.
            # Assuming event is MessageReact? No, it's usually Raw or specific.
            # If using events.CallbackQuery NO.
            # If using standard events, we need the reaction value.
            # Telethon Raw UpdateMessageReactions.
            # However, simpler if we just READ the message reactions?
            # Or use event.reaction string/emoticon?
            # Let's assume passed event is `events.Reaction` if available, or we inspect it.
            
            # If we simply want to "follow", we assume event has `.reaction` or similar.
            # If the user toggled, we might need to check if added or removed.
            # But user said "only keep one".
            # So whatever reaction happened, set it?
            
            reaction = None
            if hasattr(event, 'reaction'):
                # event.reaction is a specific reaction object or list?
                # On Reaction event it's typically the reaction changed.
                # Just taking the reaction from the event.
                reaction = event.reaction
            
            # If reaction is emtpy/None, it might be a removal.
            # If removal, we should clear reactions?
            # Telethon: client.send_reaction(chat, msg, reaction=None) clears?
            
            # Wrap in list for SendReactionRequest
            reactions_list = [reaction] if reaction else []
            await self.client(SendReactionRequest(
                peer=target_id, 
                msg_id=backup_msg_id, 
                reaction=reactions_list
            ))
            
        except Exception as e:
            self.logger.error(f"Reaction sync failed {backup_entry}: {e}")

    def _is_auto_delete_ignored(self, timestamp_str):
        if not timestamp_str: return False
        try:
             settings = self.config.get('settings', {})
             ignore_days = settings.get('auto_delete_ignore_days', 30)
             msg_time = datetime.fromisoformat(timestamp_str)
             return (datetime.now() - msg_time).days >= ignore_days
        except:
             return False
