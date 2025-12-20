import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

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

    def cleanup_old_mappings(self, retention_days: int):
        """清理过期的映射记录"""
        if retention_days <= 0:
            return
            
        logging.info(f"开始清理超过 {retention_days} 天的消息映射记录...")
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        initial_count = len(self.mapping)
        keys_to_remove = []
        
        for key, entries in self.mapping.items():
            # Standardize to list
            if isinstance(entries, dict):
                entries = [entries]
            
            # Filter entries
            new_entries = []
            for entry in entries:
                ts_str = entry.get('timestamp')
                if not ts_str:
                    # Keep entries without timestamp to be safe? or drop?
                    # Let's keep them assuming they might be important old data 
                    # OR drop them if we want strict cleanup. 
                    # Assuming data migration added timestamps, old data might lack it.
                    # Current code adds timestamp. Old data (pre-v2) might not have it.
                    # Let's keep strict check: if has timestamp and older -> remove.
                    # If no timestamp, maybe keep (safer).
                    new_entries.append(entry)
                    continue
                    
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts > cutoff_date:
                        new_entries.append(entry)
                except ValueError:
                     new_entries.append(entry)

            if not new_entries:
                keys_to_remove.append(key)
            else:
                self.mapping[key] = new_entries
        
        for key in keys_to_remove:
            del self.mapping[key]
            
        final_count = len(self.mapping)
        removed_count = initial_count - final_count
        if removed_count > 0 or len(keys_to_remove) > 0:
            self._save_mapping()
            logging.info(f"清理完成: 移除了 {removed_count} 个过期条目 (剩余 {final_count})")
        else:
            logging.info("清理完成: 没有发现过期条目")
