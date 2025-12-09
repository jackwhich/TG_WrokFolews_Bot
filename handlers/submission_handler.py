"""提交信息处理器"""
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from workflows.models import WorkflowManager
from workflows.validator import validate_submission_data
from handlers.notification_handler import NotificationHandler
from utils.logger import setup_logger
from utils.helpers import get_user_info

logger = setup_logger(__name__)


class SubmissionHandler:
    """提交信息处理器"""
    
    @staticmethod
    async def handle_submission(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        submission_data: str,
        project: str = None,
        template_type: str = "default",
    ) -> bool:
        """
        处理用户提交信息
        
        Args:
            update: Telegram更新对象
            context: 上下文对象
            submission_data: 用户提交的数据
            project: 项目名称（可选，用于选择对应的群组）
            
        Returns:
            是否成功
        """
        try:
            logger.info(f"开始处理用户提交，用户ID: {update.effective_user.id}")
            
            # 验证数据
            is_valid, error_msg = validate_submission_data(submission_data)
            if not is_valid:
                logger.warning(f"用户 {update.effective_user.id} 提交的数据验证失败: {error_msg}")
                # 使用 effective_message 以支持 CallbackQuery 和 Message 两种更新类型
                message = update.effective_message
                if message:
                    await message.reply_text(f"❌ 验证失败: {error_msg}")
                return False
            
            # 如果没有传递项目信息，尝试从 submission_data 中解析
            if not project:
                # 尝试从提交数据中解析项目信息（格式：申请项目: xxx）
                import re
                match = re.search(r'申请项目[：:]\s*([^\n]+)', submission_data)
                if match:
                    project = match.group(1).strip()
                    logger.info(f"从提交数据中解析到项目: {project}")
            
            # 获取用户信息
            user_id, username = get_user_info(update)
            logger.debug(f"用户信息 - ID: {user_id}, 用户名: {username}")
            
            # 创建工作流（在线程池中执行，避免阻塞）
            logger.info(f"正在为用户 {username} ({user_id}) 创建工作流...")
            workflow_data = await asyncio.to_thread(
                WorkflowManager.create_workflow,
                user_id=user_id,
                username=username,
                submission_data=submission_data,
                project=project,
                template_type=template_type or "default",
            )
            workflow_id = workflow_data['workflow_id']
            logger.info(f"✅ 工作流创建成功 - ID: {workflow_id}, 用户: {username} ({user_id})")
            
            # 发送到群组并@审批人（根据项目选择对应的群组）
            logger.info(f"正在发送工作流 {workflow_id} 到群组...")
            # 将项目信息添加到 workflow_data 中，用于选择群组
            if project:
                workflow_data['project'] = project
            else:
                logger.error(f"工作流 {workflow_id} 缺少项目信息，无法发送到群组")
                message = update.effective_message
                if message:
                    await message.reply_text(
                        "❌ 提交失败：缺少项目信息，无法确定发送到哪个群组。\n"
                        "请使用表单提交（/deploy_build）或确保提交数据中包含项目信息。"
                    )
                return False
            
            try:
                group_messages = await NotificationHandler.send_to_group(
                    context=context,
                    workflow_data=workflow_data,
                )
            except ValueError as e:
                # 项目未配置群组ID或其他配置错误
                logger.error(f"❌ 发送工作流 {workflow_id} 到群组失败: {str(e)}")
                message = update.effective_message
                if message:
                    await message.reply_text(f"❌ 提交失败：{str(e)}")
                return False
            
            # 更新工作流的群组消息ID（SQLite 使用 group_messages 字典）- 在线程池中执行
            if group_messages:
                # 更新工作流的 group_messages（包含所有群组的消息ID）
                await asyncio.to_thread(
                    WorkflowManager.update_workflow,
                    workflow_id,
                    group_messages=group_messages,
                )
                logger.info(f"✅ 工作流 {workflow_id} 已发送到 {len(group_messages)} 个群组")
            else:
                logger.error(f"❌ 工作流 {workflow_id} 发送到群组失败")
                message = update.effective_message
                if message:
                    await message.reply_text("❌ 发送到群组失败，请稍后重试")
                return False
            
            # 回复用户（使用 effective_message 以支持 CallbackQuery 和 Message 两种更新类型）
            message = update.effective_message
            if message:
                await message.reply_text(
                    f"✅ 工作流提交成功！\n\n"
                    f"🆔 工作流ID: {workflow_id}\n"
                    f"📝 已发送到群组，等待审批..."
                )
            
            logger.info(f"✅ 工作流 {workflow_id} 提交流程完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 处理用户提交时发生错误: {str(e)}", exc_info=True)
            # 使用 effective_message 以支持 CallbackQuery 和 Message 两种更新类型
            message = update.effective_message
            if message:
                await message.reply_text("❌ 提交过程中发生错误，请稍后重试")
            return False

