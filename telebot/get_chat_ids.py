#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取群组ID的辅助脚本
"""

from telethon import TelegramClient
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def main():
    # 从环境变量获取配置
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    
    if not api_id or not api_hash:
        print("❌ 错误: 未设置 TELEGRAM_API_ID 或 TELEGRAM_API_HASH")
        print("请在 .env 文件中配置这些值")
        print("从 https://my.telegram.org 获取")
        return
    
    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ 错误: TELEGRAM_API_ID 必须是整数")
        return
    
    # 创建临时客户端
    client = TelegramClient('temp_get_chats', api_id, api_hash)
    
    print("正在连接到 Telegram...")
    await client.start()
    
    # 获取当前用户信息
    me = await client.get_me()
    print(f"\n✅ 已登录: {me.first_name} (@{me.username})")
    print("=" * 60)
    
    print("\n📋 你的对话列表:\n")
    print(f"{'类型':<10} {'名称':<30} {'ID':<15}")
    print("-" * 60)
    
    dialog_count = 0
    async for dialog in client.iter_dialogs():
        # 确定对话类型
        if dialog.is_group:
            dialog_type = "群组"
        elif dialog.is_channel:
            dialog_type = "频道"
        elif dialog.is_user:
            dialog_type = "私聊"
        else:
            dialog_type = "其他"
        
        # 只显示群组和频道
        if dialog.is_group or dialog.is_channel:
            name = dialog.name[:28] + ".." if len(dialog.name) > 30 else dialog.name
            print(f"{dialog_type:<10} {name:<30} {dialog.id:<15}")
            dialog_count += 1
    
    print("-" * 60)
    print(f"\n共找到 {dialog_count} 个群组/频道")
    
    print("\n💡 提示:")
    print("1. 复制你想要的群组ID")
    print("2. 在 .env 文件中设置 SOURCE_CHAT_ID 和 BACKUP_CHAT_ID")
    print("3. 群组ID已经是负数格式,可以直接使用")
    
    await client.disconnect()
    
    # 清理临时会话文件
    session_file = 'temp_get_chats.session'
    if os.path.exists(session_file):
        os.remove(session_file)
        print(f"\n🗑️  已清理临时会话文件")

if __name__ == '__main__':
    asyncio.run(main())
