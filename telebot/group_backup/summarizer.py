import logging
import json
import asyncio
from pathlib import Path
from datetime import datetime
import pytz

from telebot.ai_sdk import get_ai_provider

class GroupSummarizer:
    def __init__(self, client, config, mapper, logger=None):
        self.client = client
        self.config = config
        self.mapper = mapper
        self.logger = logger or logging.getLogger(__name__)
        
        self.summary_config = config.get('summary', {})
        self.enabled = self.summary_config.get('enabled', False)
        self.provider = get_ai_provider(self.summary_config)
        
        # State tracking for processed files
        self.data_dir = Path(config.get('settings', {}).get('backup_schedule', {}).get('local_export_dir', './data/exports'))
        self.state_file = self.data_dir / "summary_state.json"
        self.processed_files = self._load_state()

    def _load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return set(json.load(f))
            except:
                pass
        return set()

    def _save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(list(self.processed_files), f)
        except Exception as e:
            self.logger.error(f"Failed to save summary state: {e}")

    async def run_process(self, file_path: Path, target_id: int):
        """Process a single backup file for summary."""
        if not self.enabled or not self.provider:
            return

        file_key = file_path.name
        if file_key in self.processed_files:
            return

        self.logger.info(f"Generating summary for {file_key}...")
        
        messages = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        messages.append(json.loads(line))
        except Exception as e:
            self.logger.error(f"Failed to read backup file {file_path}: {e}")
            return

        if not messages:
            return

        # Group by Source
        source_groups = {} # source_id -> [msgs]
        
        for msg in messages:
            t_msg_id = msg.get('id')
            source_info = self.mapper.get_source_info(target_id, t_msg_id)
            
            source_id = None
            if source_info:
                source_id = source_info.get('source_chat_id')
                msg['_source_msg_id'] = source_info.get('source_msg_id')
            
            if not source_id:
                continue

            if source_id not in source_groups:
                source_groups[source_id] = []
            source_groups[source_id].append(msg)

        # Process each Source
        for source_id, msgs in source_groups.items():
            await self._summarize_source(source_id, msgs, file_key)

        # Mark as done
        self.processed_files.add(file_key)
        self._save_state()

    async def _summarize_source(self, source_id, msgs, file_key):
        # Find Source Config
        source_conf = self.config.get('groups', {}).get(source_id)
        if not source_conf:
            source_conf = self.config.get('groups', {}).get(str(source_id), {})
        
        # Determine Summary Target
        summary_target_id = source_conf.get('summary_target')
        
        if not summary_target_id:
            targets = source_conf.get('targets', [])
            if targets:
                t = targets[0]
                summary_target_id = t
            else:
                self.logger.warning(f"No target found for summary of source {source_id}")
                return

        # Parse Target ID / Topic
        target_chat_id = None
        target_topic_id = None
        
        if isinstance(summary_target_id, int):
             target_chat_id = summary_target_id
        elif isinstance(summary_target_id, str):
             if '.' in summary_target_id:
                 p = summary_target_id.split('.')
                 target_chat_id = int(p[0])
                 target_topic_id = int(p[1])
             else:
                 target_chat_id = int(summary_target_id)
        
        if not target_chat_id:
            return

        # Prepare Content for AI
        formatted_lines = []
        
        # Load focus users from config
        focus_users = set()
        raw_focus = self.summary_config.get('focus_users', [])
        for u in raw_focus:
            focus_users.add(str(u))
            
        found_focus_names = set()

        for m in msgs:
            clean_source_id = str(source_id)
            if clean_source_id.startswith("-100"):
                clean_source_id = clean_source_id[4:]
            
            real_src_id = m.get('_source_msg_id', m['id'])
            link = f"https://t.me/c/{clean_source_id}/{real_src_id}"
            
            text_content = m.get('text', '')
            if len(text_content) > 500:
                text_content = text_content[:500] + "..."
            
            # Check for followed user
            sender_id = str(m.get('sender_id', ''))
            sender_name = m.get('sender_name', 'Unknown')
            
            is_followed = sender_id in focus_users
            
            msg_header = f"Msg: {text_content}"
            if is_followed:
                msg_header = f"Msg (Followed User {sender_name}): {text_content}"
                found_focus_names.add(sender_name)
            elif sender_name and sender_name != 'Unknown':
                 msg_header = f"Msg ({sender_name}): {text_content}"
                
            formatted_lines.append(f"{msg_header}\nSourceLink: {link}\n---")

        context_text = "\n".join(formatted_lines)
        if not context_text.strip():
            return

        # Prompt
        group_tag = source_conf.get('tag', '')
        # Fix date format for tags (YYYY_MM_DD)
        date_str = datetime.now().strftime('%Y_%m_%d')
        
        custom_prompt = self.summary_config.get('prompt')
        
        # Inject emphasis instructions if focus users found
        if found_focus_names:
            names_list = ", ".join(found_focus_names)
            emphasis = (
                f"\n\nIMPORTANT: The following users are 'Followed Users': {names_list}. "
                "You MUST give their messages higher weight. "
                "When summarizing, explicitly mention their names and what they said."
            )
            if custom_prompt:
                custom_prompt += emphasis
            else:
                 custom_prompt = "Summarize the chat log." + emphasis
        
        summary_content = await self.provider.generate_summary(context_text, custom_prompt)
        
        # Build Final Message
        final_msg = f"#总结 {group_tag} #date_{date_str}\n\n{summary_content}"
        
        # Send
        try:
            await self.client.send_message(
                target_chat_id,
                final_msg,
                reply_to=target_topic_id,
                link_preview=False
            )
            self.logger.info(f"Sent summary for {source_id} to {target_chat_id}")
        except Exception as e:
            self.logger.error(f"Failed to send summary: {e}")

    async def run_batch_backfill(self):
        """Check all .bak files and process if missing."""
        if not self.enabled:
            return
            
        self.logger.info("Starting summary scan...")
        # Get all daily files
        for file_path in self.data_dir.glob("*_daily.bak"):
             if file_path.name in self.processed_files:
                 continue

             # Look for metadata file
             meta_path = file_path.with_suffix('.bak.meta')
             target_id = None
             
             if meta_path.exists():
                 try:
                     with open(meta_path, 'r') as f:
                         meta = json.load(f)
                         target_id = meta.get('target_id')
                 except:
                     pass
             
             if not target_id:
                 target_id = self._infer_target_id(file_path)

             if target_id:
                 await self.run_process(file_path, target_id)
             else:
                 self.logger.warning(f"Could not determine target ID for {file_path}")

    def _infer_target_id(self, file_path):
        try:
            messages_to_check = []
            with open(file_path, 'r') as f:
                for _ in range(5):
                    line = f.readline()
                    if line:
                        messages_to_check.append(json.loads(line))
            
            if not messages_to_check: return None
            
            candidates = {}
            for msg in messages_to_check:
                mid = msg['id']
                for (tid, r_mid) in self.mapper.reverse_mapping.keys():
                    if r_mid == mid:
                        candidates[tid] = candidates.get(tid, 0) + 1
            
            if candidates:
                best_tid = max(candidates, key=candidates.get)
                if candidates[best_tid] > 0:
                     return best_tid
        except:
            pass
        return None
