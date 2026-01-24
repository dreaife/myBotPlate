import logging
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json
from telethon import TelegramClient, events, utils
from telethon.tl.types import UpdateMessageReactions
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .mapper import MessageMapper
from .handlers import MessageHandler
from .summarizer import GroupSummarizer

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
        
        # source_id -> [ {target_id, name, tag} ]
        self.source_map = {}
        # target_id -> {last_sender_id}
        self.chat_states = {}
        
        self._parse_config()
        self.handler = MessageHandler(None, config, self.mapper, self.chat_states) # Client not set yet
        self.summarizer = GroupSummarizer(None, config, self.mapper, logger)

    def _parse_entity_id(self, id_val):
        """Parses ID into (chat_id, topic_id)"""
        s = str(id_val)
        topic_id = None
        
        # Check for group_id.topic_id format
        if '.' in s:
            try:
                parts = s.split('.')
                chat_id = int(parts[0])
                topic_id = int(parts[1])
                return chat_id, topic_id
            except ValueError:
                self.logger.error(f"Invalid ID format: {id_val}")
                return None, None
                
        try:
            return int(s), None
        except ValueError:
            self.logger.error(f"Invalid ID: {id_val}")
            return None, None

    def _parse_config(self):
        """解析配置构建快速查找表 (Source-Centric Config)"""
        groups = self.config.get('groups', {})
        # groups structure:
        # SOURCE_ID or SOURCE_ID.TOPIC_ID:
        #   targets: [TARGET_ID, TARGET_ID.TOPIC_ID]
        #   name: "..."
        #   tag: "..."
        
        for source_key, source_info in groups.items():
            source_id, source_topic_id = self._parse_entity_id(source_key)
            if source_id is None:
                continue
                
            if source_id not in self.source_map:
                self.source_map[source_id] = []
            
            info = source_info or {}
            
            # 兼容旧格式或直接读取 targets
            targets = info.get('targets', [])
            if not isinstance(targets, list):
                if isinstance(targets, (int, str, float)):
                    targets = [targets]
                else:
                    self.logger.warning(f"Source {source_key} has invalid targets format: {targets}")
                    continue
            
            for tid in targets:
                target_id, target_topic_id = self._parse_entity_id(tid)
                if target_id is None:
                    continue
                    
                entry = {
                    'target_id': target_id,
                    'target_topic_id': target_topic_id,
                    'source_topic_id': source_topic_id,
                    'name': info.get('name'),
                    'tag': info.get('tag')
                }
                self.source_map[source_id].append(entry)

    def start_scheduler(self):
        """启动定时任务"""
        settings = self.config.get('settings', {})
        schedule_config = settings.get('backup_schedule', {})
        
        scheduler = AsyncIOScheduler()
        timezone = settings.get('timezone', 'Asia/Tokyo')
        
        # Daily Backup
        if schedule_config.get('daily_time'):
            daily_time = schedule_config.get('daily_time', '04:00')
            h, m = map(int, daily_time.split(':'))
            scheduler.add_job(self.run_daily_backup, 'cron', hour=h, minute=m, timezone=timezone)
            self.logger.info(f"已计划每日备份: {daily_time}")

        # Weekly Backup
        if schedule_config.get('weekly_time'):
            weekly_time = schedule_config.get('weekly_time', '04:00')
            wd = schedule_config.get('weekly_day', 'mon')
            wh, wm = map(int, weekly_time.split(':'))
            scheduler.add_job(self.run_weekly_backup, 'cron', day_of_week=wd, hour=wh, minute=wm, timezone=timezone)
            self.logger.info(f"已计划每周备份: {wd} {weekly_time}")
            
        # Cleanup Job (Daily at 03:00)
        retention_days = settings.get('mapping_retention_days', 90)
        if retention_days > 0:
            scheduler.add_job(
                lambda: self.mapper.cleanup_old_mappings(retention_days),
                'cron', hour=3, minute=0, timezone=timezone
            )
            self.logger.info(f"已计划每日清理过期映射 (保留{retention_days}天)")

        scheduler.start()

    async def _export_messages(self, chat_id, start_time, export_dir, suffix=""):
        messages = []
        sender_ids = set()
        try:
            async for msg in self.client.iter_messages(chat_id, offset_date=start_time, reverse=True):
                if not msg.text and not msg.media: continue
                messages.append({
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "sender_id": msg.sender_id,
                    "text": msg.text,
                    "reply_to": msg.reply_to_msg_id
                })
                if msg.sender_id:
                    sender_ids.add(msg.sender_id)
        except Exception as e:
            self.logger.error(f"Export fetch failed for {chat_id}: {e}")
            return None

        if not messages: return None

        # Resolve Sender Names
        sender_map = {}
        if sender_ids:
            try:
                # Batch fetch entities (should be cached by iter_messages)
                users = await self.client.get_entity(list(sender_ids))
                # Single result handling?
                if not isinstance(users, list):
                    users = [users]
                    
                for u in users:
                    name = getattr(u, 'first_name', '') or ''
                    if getattr(u, 'last_name', None):
                        name += f" {u.last_name}"
                    sender_map[u.id] = name.strip() or "Unknown"
            except Exception as e:
                self.logger.warning(f"Failed to resolve sender names for export: {e}")
        
        # Inject names
        for m in messages:
            m['sender_name'] = sender_map.get(m['sender_id'], 'Unknown')

        try:
            entity = await self.client.get_entity(chat_id)
            chat_title = getattr(entity, 'title', str(chat_id))
        except:
            chat_title = str(chat_id)
            
        safe_title = "".join([c for c in chat_title if c.isalnum() or c in (' ', '-', '_')]).strip()
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"{safe_title}_{date_str}{suffix}.bak"
        
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            for m in messages:
                f.write(json.dumps(m, ensure_ascii=False) + '\n')
        
        # Write metadata
        try:
            meta_path = file_path.with_suffix('.bak.meta')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({"target_id": chat_id, "timestamp": datetime.now().isoformat()}, f)
        except Exception as e:
            self.logger.error(f"Failed to write metadata for {filename}: {e}")
            
        return file_path

    async def run_daily_backup(self):
        """每日备份 (从备份群导出)"""
        try:
            self.logger.info("开始每日备份...")
            schedule = self.config.get('settings', {}).get('backup_schedule', {})
            export_dir = Path(schedule.get('local_export_dir', './data/exports'))
            start_time = datetime.now(pytz.utc) - timedelta(hours=24)
            
            # 获取所有唯一的备份群ID
            unique_targets = set()
            for targets in self.source_map.values():
                for target in targets:
                    unique_targets.add(target['target_id'])
            
            for target_id in unique_targets:
                path = await self._export_messages(target_id, start_time, export_dir, suffix="_daily")
                # Trigger Summary
                if path and self.summarizer:
                    await self.summarizer.run_process(path, target_id)

        except Exception as e:
            self.logger.error(f"每日备份异常: {e}")

    async def run_weekly_backup(self):
        """每周备份 (从备份群导出并上传)"""
        try:
            self.logger.info("开始每周备份...")
            export_dir = Path("./data/temp_weekly")
            start_time = datetime.now(pytz.utc) - timedelta(days=7)
            
            # 获取所有唯一的备份群ID
            unique_targets = set()
            for targets in self.source_map.values():
                for target in targets:
                    unique_targets.add(target['target_id'])
            
            for target_id in unique_targets:
                path = await self._export_messages(target_id, start_time, export_dir, suffix="_weekly")
                if path:
                    caption = f"#备份 (Weekly) {datetime.now().strftime('%Y-%m-%d')}"
                    try:
                        await self.client.send_file(target_id, path, caption=caption)
                    except Exception as e:
                        self.logger.error(f"Failed to upload to {target_id}: {e}")
                        
                    if os.path.exists(path):
                        os.remove(path)
        except Exception as e:
            self.logger.error(f"每周备份异常: {e}")

    async def start(self):
        self.logger.info("Starting backup bot (Refactored)...")
        self.client = TelegramClient(str(self.session_file), self.api_id, self.api_hash)
        self.handler.client = self.client # Inject client into handler
        self.summarizer.client = self.client # Inject client into summarizer
        
        await self.client.start()
        self.start_scheduler()
        
        # Trigger async backfill check
        asyncio.create_task(self.summarizer.run_batch_backfill())
        
        source_chats = list(self.source_map.keys())
        self.logger.info(f"Monitoring {len(source_chats)} source groups")
        
        @self.client.on(events.NewMessage(chats=source_chats))
        async def handler_new(event):
            # Pass list of targets for this source
            targets = self.source_map.get(event.chat_id, [])
            await self.handler.handle_new_message(event, targets)
            
        @self.client.on(events.MessageEdited(chats=source_chats))
        async def handler_edit(event):
            # Strict filter at source: Ignore if triggered by Reaction
            original_update = getattr(event, 'original_update', None)
            if isinstance(original_update, UpdateMessageReactions) or \
               (original_update and type(original_update).__name__ == 'UpdateMessageReactions'):
                return
            
            targets = self.source_map.get(event.chat_id, [])
            # Also try matching without -100 prefix if needed? Usually event.chat_id is correct for high-level events.
            await self.handler.handle_edit_message(event, targets)

        @self.client.on(events.MessageDeleted(chats=source_chats))
        async def handler_delete(event):
            if hasattr(event, 'chat_id') and event.chat_id:
                targets = self.source_map.get(event.chat_id, [])
                await self.handler.handle_deleted_message(event, targets)

        @self.client.on(events.Raw)
        async def handler_reaction(event):
            if isinstance(event, UpdateMessageReactions):
                peer_id = utils.get_peer_id(event.peer)
                
                # Telethon raw peer_id for channels lacks -100 prefix, but config has it.
                # Try raw, then -100 prefixed.
                targets = self.source_map.get(peer_id)
                if not targets and peer_id > 0:
                    potential_id = int(f"-100{peer_id}")
                    targets = self.source_map.get(potential_id)

                if not targets:
                    return

                # Pick the first reaction to satisfy "keep only one"
                reaction_to_send = None
                if event.reactions and event.reactions.results:
                    reaction_to_send = event.reactions.results[0].reaction
                    # Debug log
                    # self.logger is not available in core?
                    # Core `GroupBackupClient` has `self.logger`.
                    self.logger.info(f"Reaction update on {peer_id} msg {event.msg_id}. Found {len(event.reactions.results)} reactions. Selected: {reaction_to_send}")
                else:
                     self.logger.info(f"Reaction update on {peer_id} msg {event.msg_id}. No reactions found (Clear).")
                
                # Mock event object for handler
                class ReactionEvent:
                    def __init__(self, m_id, c_id, react):
                        self.msg_id = m_id
                        self.chat_id = c_id # Use the ID that matched in source_map (to keep consistency)
                        self.reaction = react
                
                # Which ID to pass as chat_id? The one used for lookup in Mapper.
                matched_id = peer_id
                if peer_id not in self.source_map and peer_id > 0:
                     pid = int(f"-100{peer_id}")
                     if pid in self.source_map:
                         matched_id = pid
                
                mock_event = ReactionEvent(event.msg_id, matched_id, reaction_to_send)
                await self.handler.handle_reaction(mock_event, targets)
            
        await self.client.run_until_disconnected()

    def run(self):
        asyncio.run(self.start())
