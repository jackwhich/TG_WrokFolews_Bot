"""通知处理器"""
import asyncio
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, TimedOut
from telegram.ext import ContextTypes
from config.settings import Settings
from config.constants import STATUS_PENDING, ACTION_APPROVE, ACTION_REJECT
from utils.formatter import format_workflow_message, format_approval_result
from utils.logger import setup_logger

logger = setup_logger(__name__)


class NotificationHandler:
    """通知处理器"""
    
    @staticmethod
    def _create_approval_keyboard(workflow_id: str) -> InlineKeyboardMarkup:
        """创建审批按钮键盘"""
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ 通过",
                    callback_data=f"{ACTION_APPROVE}:{workflow_id}"
                ),
                InlineKeyboardButton(
                    "❌ 拒绝",
                    callback_data=f"{ACTION_REJECT}:{workflow_id}"
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    async def send_to_group(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: dict,
    ) -> Optional[dict]:
        """
        发送工作流消息到群组（支持多个群组）
        
        Args:
            context: 上下文对象
            workflow_data: 工作流数据
            
        Returns:
            group_messages 字典 {group_id: message_id}，如果失败返回 None
        """
        workflow_id = workflow_data.get('workflow_id', 'N/A')
        try:
            logger.info(f"开始发送工作流 {workflow_id} 到群组...")
            
            # 格式化消息（使用配置的审批人用户名，或默认值）
            # 去掉 @ 符号（如果有），因为消息模板中已经包含了 @
            approver_username = Settings.APPROVER_USERNAME or "审批人"
            approver_username = approver_username.lstrip('@')  # 去掉开头的 @ 符号
            message_text = format_workflow_message(
                workflow_data,
                approver_username,
            )
            logger.debug(f"工作流消息已格式化，长度: {len(message_text)}")
            
            # 创建审批按钮
            keyboard = NotificationHandler._create_approval_keyboard(
                workflow_data["workflow_id"]
            )
            
            # 根据项目选择群组ID（必须提供项目信息）
            project = workflow_data.get('project')
            if not project:
                logger.error(f"工作流 {workflow_id} 缺少项目信息，无法确定发送到哪个群组")
                raise ValueError("工作流缺少项目信息，无法确定发送到哪个群组")
            
            # 从项目配置中获取群组ID（如果未配置会抛出异常）
            try:
                group_ids = await asyncio.to_thread(Settings.get_group_ids_by_project, project)
            except ValueError as e:
                logger.error(f"获取项目 {project} 的群组ID失败: {str(e)}")
                raise
            
            # 发送消息到所有配置的群组
            group_messages = {}
            for group_id in group_ids:
                try:
                    logger.debug(f"正在发送消息到群组 {group_id}...")
                    message = await context.bot.send_message(
                        chat_id=group_id,
                        text=message_text,
                        reply_markup=keyboard,
                    )
                    group_messages[group_id] = message.message_id
                    logger.info(f"✅ 工作流消息已发送到群组 {group_id}，消息ID: {message.message_id}")
                except Exception as e:
                    logger.error(f"❌ 发送消息到群组 {group_id} 失败: {str(e)}", exc_info=True)
                    # 继续发送到其他群组，不中断流程
            
            # 不再发送额外的 @ 提醒消息，因为消息内容中已经包含了 @审批人 请审批
            
            # 如果至少有一个群组发送成功，返回字典；否则返回 None
            return group_messages if group_messages else None
            
        except Exception as e:
            logger.error(f"❌ 发送群组消息失败 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    async def update_group_message(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: dict,
        message_id: int = None,
    ):
        """
        更新群组消息（支持多个群组）
        
        Args:
            context: 上下文对象
            workflow_data: 工作流数据
            message_id: 单个消息ID（可选，如果提供则只更新该消息）
                        如果不提供，则从 workflow_data 的 group_messages 中获取所有消息ID
        """
        try:
            workflow_id = workflow_data.get('workflow_id', 'N/A')
            
            # 使用实际审批人信息（自动捕获的）
            approver_username = workflow_data.get('approver_username', Settings.APPROVER_USERNAME or '审批人')
            
            # 格式化审批结果消息
            message_text = format_approval_result(
                workflow_data,
                approver_username,
            )
            
            # 获取要更新的消息列表
            if message_id:
                # 如果提供了单个消息ID，只更新该消息
                # 需要从 group_messages 中找到对应的 group_id
                group_messages = workflow_data.get('group_messages', {})
                messages_to_update = []
                for group_id, msg_id in group_messages.items():
                    if msg_id == message_id:
                        messages_to_update.append((group_id, msg_id))
                        break
            else:
                # 如果没有提供 message_id，更新所有群组的消息
                group_messages = workflow_data.get('group_messages', {})
                messages_to_update = list(group_messages.items())
            
            # 更新所有消息
            updated_count = 0
            for group_id, msg_id in messages_to_update:
                try:
                    await context.bot.edit_message_text(
                        chat_id=group_id,
                        message_id=msg_id,
                        text=message_text,
                    )
                    updated_count += 1
                    logger.debug(f"✅ 已更新群组 {group_id} 的消息 {msg_id}")
                except Exception as e:
                    logger.error(f"❌ 更新群组 {group_id} 的消息 {msg_id} 失败: {str(e)}")
            
            logger.info(
                f"工作流 {workflow_id} 群组消息已更新（{updated_count}/{len(messages_to_update)} 个群组）"
            )
            
        except Exception as e:
            logger.error(f"更新群组消息失败: {str(e)}", exc_info=True)
    
    @staticmethod
    async def notify_user(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: dict,
        user_id: int,
        timeout: float = 5.0,
    ):
        """
        通知提交用户审批结果（带超时处理）
        
        Args:
            context: 上下文对象
            workflow_data: 工作流数据
            user_id: 用户ID
            timeout: 超时时间（秒），默认5秒
        """
        workflow_id = workflow_data.get('workflow_id', 'N/A')
        try:
            logger.info(f"开始通知用户 - 工作流ID: {workflow_id}, 用户ID: {user_id}")
            
            status = workflow_data.get("status", STATUS_PENDING)
            logger.debug(f"工作流状态: {status}")
            
            # 使用实际审批人信息（自动捕获的）
            approver_username = workflow_data.get('approver_username', '未知用户')
            
            if status == "approved":
                message = (
                    f"✅ 您的工作流已通过审批！\n\n"
                    f"🆔 工作流ID: {workflow_id}\n"
                    f"✅ 审批人: @{approver_username}\n"
                    f"📅 审批时间: {workflow_data.get('approval_time', 'N/A')}"
                )
            elif status == "rejected":
                message = (
                    f"❌ 您的工作流已被拒绝\n\n"
                    f"🆔 工作流ID: {workflow_id}\n"
                    f"❌ 审批人: @{approver_username}\n"
                    f"📅 审批时间: {workflow_data.get('approval_time', 'N/A')}\n"
                    f"💬 审批意见: {workflow_data.get('approval_comment', '无')}"
                )
            else:
                logger.debug(f"工作流状态为 {status}，无需通知用户")
                return  # 待审批状态不需要通知
            
            # 使用超时包装，避免长时间阻塞
            try:
                await asyncio.wait_for(
                    context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                    ),
                    timeout=timeout
                )
                logger.info(f"✅ 已通知用户 {user_id} 工作流 {workflow_id} 的审批结果 - 状态: {status}")
            except asyncio.TimeoutError:
                logger.warning(
                    f"⚠️ 通知用户 {user_id} 超时（{timeout}秒）- 工作流ID: {workflow_id}，"
                    f"但审批流程已完成，不影响审批结果"
                )
            except TimedOut:
                logger.warning(
                    f"⚠️ Telegram API 超时 - 工作流ID: {workflow_id}, 用户ID: {user_id}，"
                    f"但审批流程已完成，不影响审批结果"
                )
            
        except Forbidden as e:
            # 用户可能还没有与 Bot 开始对话，这是正常情况，记录警告而不是错误
            logger.warning(
                f"⚠️ 无法通知用户 {user_id} - 工作流ID: {workflow_id}。"
                f"用户可能还没有与 Bot 开始对话（需要先发送 /start 命令）。"
                f"错误: {str(e)}"
            )
        except Exception as e:
            logger.error(f"❌ 通知用户失败 - 工作流ID: {workflow_id}, 用户ID: {user_id}, 错误: {str(e)}", exc_info=True)

