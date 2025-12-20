#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import sys
import logging
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler

# Import from new package
# Ensure module path is accessible
sys.path.append(str(Path(__file__).parent.parent))

from telebot.group_backup.core import GroupBackupClient

def parse_args():
    parser = argparse.ArgumentParser(description='Telegram Group Backup')
    parser.add_argument('--session-name', type=str, default='group_backup', help='Session name')
    parser.add_argument('--config', type=str, default='telebot/group_backup_config.yml', help='Config file path')
    parser.add_argument('--log-dir', type=str, default=None, help='Log directory')
    parser.add_argument('--data-dir', type=str, default=None, help='Data directory')
    return parser.parse_args()

def load_config(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

def setup_logging(session_name, log_dir=None):
    if log_dir is None:
        log_dir = Path("/logs") / "bot" / session_name
    else:
        log_dir = Path(log_dir)
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "backup.log"

    handler = TimedRotatingFileHandler(str(log_file), when="midnight", interval=1, backupCount=30, encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
    return logging.getLogger(__name__)

def main():
    load_dotenv()
    args = parse_args()
    logger = setup_logging(args.session_name, args.log_dir)
    
    # Data Dir
    if args.data_dir is None:
        data_dir = Path("/data") / "bot" / args.session_name
    else:
        data_dir = Path(args.data_dir)
        
    config = load_config(args.config)
    if not config:
        logger.error("Config load failed")
        sys.exit(1)
        
    telegram_config = config.get('telegram', {})
    api_id = telegram_config.get('api_id')
    api_hash = telegram_config.get('api_hash')
    
    if not api_id or not api_hash:
        logger.error("Missing telegram.api_id or telegram.api_hash in config")
        sys.exit(1)
        
    try:
        client = GroupBackupClient(int(api_id), api_hash, config, data_dir, logger, args.session_name)
        client.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

