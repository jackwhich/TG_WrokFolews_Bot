"""辅助函数"""
from datetime import datetime
from typing import Tuple
from telegram import Update
import uuid


def generate_workflow_id() -> str:
    """生成工作流ID"""
    timestamp = datetime.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"WF-{timestamp}-{unique_id}"


def get_current_timestamp() -> str:
    """获取当前时间戳（ISO格式）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_user_info(update: Update) -> Tuple[int, str]:
    """
    从 Update 对象获取用户信息
    
    Args:
        update: Telegram Update 对象
        
    Returns:
        (user_id, username) 元组
    """
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "未知用户"
    return user_id, username


async def reply_or_edit(update: Update, text: str, **kwargs):
    """
    统一处理回复消息或编辑消息
    
    如果 update 有 callback_query，则编辑消息
    如果 update 有 message，则回复消息
    
    Args:
        update: Telegram Update 对象
        text: 消息文本
        **kwargs: 其他参数（如 reply_markup）
    """
    if update.callback_query:
        await update.callback_query.edit_message_text(text, **kwargs)
    elif update.message:
        await update.message.reply_text(text, **kwargs)

