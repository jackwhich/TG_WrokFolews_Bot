"""消息处理器"""
import warnings
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

# 抑制 ConversationHandler 的 per_message 警告
# 因为混合使用 CallbackQueryHandler 和 MessageHandler 时，必须使用 per_message=False
# 这是推荐配置，功能正常，只是库会发出警告
warnings.filterwarnings(
    "ignore",
    category=PTBUserWarning,
    message=".*per_message.*"
)
from handlers.submission_handler import SubmissionHandler
from handlers.approval_handler import ApprovalHandler
from handlers.form_handler import FormHandler
from config.constants import (
    SELECTING_PROJECT,
    SELECTING_ENVIRONMENT,
    SELECTING_SERVICE,
    INPUTTING_ADDRESS,
    INPUTTING_HASH,
    INPUTTING_BRANCH,
    INPUTTING_CONTENT,
    CONFIRMING_FORM,
    ACTION_SELECT_PROJECT,
    ACTION_SELECT_ENV,
    ACTION_SELECT_SERVICE,
    ACTION_CONFIRM_SERVICE_SELECTION,
    ACTION_CONFIRM_FORM,
    ACTION_CANCEL_FORM,
)
from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        f"👋 欢迎使用工作流审批机器人！\n\n"
        f"使用 /deploy_build 命令提交工作流信息。"
    )


def create_deploy_command_handler(project_name: str):
    """创建部署命令处理器（为每个项目生成独立的处理器）"""
    async def deploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理部署命令（表单提交）"""
        logger.info(f"收到项目 {project_name} 的部署命令，用户: {update.effective_user.id}")
        try:
            # 将项目名称存储到 context 中，供表单处理器使用
            context.user_data['project_name'] = project_name
            result = await FormHandler.start_form(update, context, project_name=project_name)
            logger.info(f"项目 {project_name} 的部署命令处理完成，返回状态: {result}")
            return result
        except Exception as e:
            logger.error(f"处理项目 {project_name} 的部署命令时发生错误: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 处理命令失败: {str(e)}")
            return ConversationHandler.END
    return deploy_command


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cancel 命令"""
    await update.message.reply_text("❌ 已取消提交")
    return ConversationHandler.END


def setup_handlers(application):
    """设置所有处理器"""
    
    # 从数据库加载项目配置，动态注册每个项目的命令
    from workflows.models import WorkflowManager
    options = WorkflowManager.get_project_options()
    projects = options.get("projects", {})
    
    # 为每个项目创建独立的命令处理器
    registered_commands = []
    for project_name, project_data in projects.items():
        command = project_data.get("command")
        if not command:
            logger.warning(f"项目 {project_name} 未配置 command 字段，跳过注册")
            continue
        
        # 移除命令前缀的斜杠（如果有）
        command = command.lstrip("/")
        
        # 创建该项目的命令处理器
        command_handler = create_deploy_command_handler(project_name)
        
        # 创建表单对话处理器
        form_conv = ConversationHandler(
            entry_points=[CommandHandler(command, command_handler)],
            states={
                SELECTING_PROJECT: [
                    CallbackQueryHandler(FormHandler.handle_project_selection, pattern=f"^{ACTION_SELECT_PROJECT}:")
                ],
                SELECTING_ENVIRONMENT: [
                    CallbackQueryHandler(FormHandler.handle_environment_selection, pattern=f"^{ACTION_SELECT_ENV}:")
                ],
                SELECTING_SERVICE: [
                    CallbackQueryHandler(
                        FormHandler.handle_service_selection, 
                        pattern=f"^{ACTION_SELECT_SERVICE}:|^{ACTION_CONFIRM_SERVICE_SELECTION}"
                    )
                ],
                INPUTTING_ADDRESS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, FormHandler.handle_address_input)
                ],
                INPUTTING_HASH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, FormHandler.handle_hash_input)
                ],
                INPUTTING_BRANCH: [
                    CallbackQueryHandler(FormHandler.handle_branch_input, pattern="^branch:"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, FormHandler.handle_branch_input)
                ],
                INPUTTING_CONTENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, FormHandler.handle_content_input)
                ],
                CONFIRMING_FORM: [
                    CallbackQueryHandler(FormHandler.handle_confirmation, pattern=f"^{ACTION_CONFIRM_FORM}|^{ACTION_CANCEL_FORM}")
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_command)],
            # 使用默认设置：per_chat=True, per_user=True, per_message=False
            # 这是混合使用 CallbackQueryHandler 和 MessageHandler 时的推荐配置
        )
        
        # 注册该项目的命令处理器
        application.add_handler(form_conv)
        registered_commands.append(f"/{command} ({project_name})")
        logger.info(f"✅ 已注册项目 {project_name} 的命令: /{command}")
    
    # 注册基础命令
    application.add_handler(CommandHandler("start", start_command))
    
    # 审批回调处理器
    application.add_handler(
        CallbackQueryHandler(
            ApprovalHandler.handle_approval_callback,
            pattern="^(approve|reject):"
        )
    )
    
    logger.info(f"✅ 所有处理器已注册，共注册 {len(registered_commands)} 个项目命令: {', '.join(registered_commands)}")

