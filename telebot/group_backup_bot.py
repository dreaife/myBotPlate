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
    parser.add_argument('--log-dir', type=str, default=None,
                        help='日志目录路径 (默认: /logs/bot/<session-name>/)')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='数据目录路径 (默认: /data/bot/<session-name>/)')
    return parser.parse_args()


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
        """添加消息映射"""
        key = f"{source_chat_id}_{source_msg_id}"
        self.mapping[key] = {
            "source_chat_id": source_chat_id,
            "source_msg_id": source_msg_id,
            "backup_chat_id": backup_chat_id,
            "backup_msg_id": backup_msg_id,
            "timestamp": datetime.now().isoformat()
        }
        self._save_mapping()
    
    def get_backup_msg(self, source_chat_id: int, source_msg_id: int) -> dict:
        """获取对应的备份消息信息"""
        key = f"{source_chat_id}_{source_msg_id}"
        return self.mapping.get(key)


class GroupBackupClient:
    """群消息备份客户端 (使用用户账号)"""
    
    def __init__(self, api_id: int, api_hash: str, source_chat_id: int, 
                 backup_chat_id: int, data_dir: Path, logger: logging.Logger,
                 session_name: str = 'group_backup'):
        self.api_id = api_id
        self.api_hash = api_hash
        self.source_chat_id = source_chat_id
        self.backup_chat_id = backup_chat_id
        self.logger = logger
        self.mapper = MessageMapper(data_dir)
        self.session_file = data_dir / f"{session_name}.session"
        self.client = None
    
    async def handle_new_message(self, event):
        """处理新消息 - 转发到备份群"""
        try:
            message = event.message
            
            # 忽略服务消息
            if isinstance(message, MessageService):
                return
            
            # 获取发送者信息
            sender = await message.get_sender()
            sender_name = getattr(sender, 'first_name', 'Unknown')
            if hasattr(sender, 'last_name') and sender.last_name:
                sender_name += f" {sender.last_name}"
            sender_username = f"@{sender.username}" if hasattr(sender, 'username') and sender.username else ""
            
            # 构建消息头部信息
            header = f"👤 {sender_name} {sender_username}\n"
            header += f"🕐 {message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if message.edit_date:
                header += "✏️ (已编辑)\n"
            
            header += "─" * 30 + "\n"
            
            # 转发消息到备份群
            try:
                # 使用 Telethon 的转发功能,同时添加说明文字
                if message.text:
                    # 文本消息
                    full_text = header + message.text
                    backup_msg = await self.client.send_message(
                        self.backup_chat_id,
                        full_text
                    )
                else:
                    # 先发送头部信息
                    await self.client.send_message(
                        self.backup_chat_id,
                        header
                    )
                    # 再转发原消息(保留媒体)
                    backup_msg = await self.client.forward_messages(
                        self.backup_chat_id,
                        message
                    )
                
                # 保存消息映射
                self.mapper.add_mapping(
                    self.source_chat_id, message.id,
                    self.backup_chat_id, backup_msg.id
                )
                self.logger.info(
                    f"消息已备份: {message.id} -> {backup_msg.id}"
                )
            
            except Exception as e:
                self.logger.error(f"转发消息失败: {e}")
        
        except Exception as e:
            self.logger.error(f"处理消息时出错: {e}", exc_info=True)
    
    async def handle_deleted_message(self, event):
        """处理撤回的消息"""
        try:
            # 获取被删除的消息ID
            deleted_id = event.deleted_id
            if not deleted_id:
                return
            
            # 查找对应的备份消息
            backup_info = self.mapper.get_backup_msg(
                self.source_chat_id, 
                deleted_id
            )
            
            if backup_info:
                # 在备份群发送撤回提示
                warning_text = (
                    f"⚠️ 消息已被撤回 ⚠️\n"
                    f"🕐 撤回时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📝 原消息ID: {deleted_id}"
                )
                
                # 回复原备份消息
                await self.client.send_message(
                    self.backup_chat_id,
                    warning_text,
                    reply_to=backup_info['backup_msg_id']
                )
                
                self.logger.info(f"检测到撤回消息: {deleted_id}")
        
        except Exception as e:
            self.logger.error(f"处理撤回消息时出错: {e}", exc_info=True)
    
    async def start(self):
        """启动客户端"""
        self.logger.info("正在启动群消息备份程序...")
        self.logger.info(f"源群ID: {self.source_chat_id}")
        self.logger.info(f"备份群ID: {self.backup_chat_id}")
        
        # 创建客户端
        self.client = TelegramClient(
            str(self.session_file),
            self.api_id,
            self.api_hash
        )
        
        # 连接并登录
        await self.client.start()
        
        # 验证登录
        me = await self.client.get_me()
        self.logger.info(f"已登录账号: {me.first_name} (@{me.username})")
        
        # 注册事件处理器
        
        # 处理源群的新消息
        @self.client.on(events.NewMessage(chats=self.source_chat_id))
        async def new_message_handler(event):
            await self.handle_new_message(event)
        
        # 处理源群的消息编辑
        @self.client.on(events.MessageEdited(chats=self.source_chat_id))
        async def edited_message_handler(event):
            await self.handle_new_message(event)
        
        # 处理源群的消息删除
        @self.client.on(events.MessageDeleted(chats=self.source_chat_id))
        async def deleted_message_handler(event):
            await self.handle_deleted_message(event)
        
        self.logger.info("客户端已启动,正在监听消息...")
        
        # 保持运行
        await self.client.run_until_disconnected()
    
    def run(self):
        """同步运行方法"""
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
