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


async def deploy_build_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /deploy_build 命令（表单提交）"""
    logger.info(f"收到 /deploy_build 命令，用户: {update.effective_user.id}")
    try:
        result = await FormHandler.start_form(update, context)
        logger.info(f"/deploy_build 命令处理完成，返回状态: {result}")
        return result
    except Exception as e:
        logger.error(f"处理 /deploy_build 命令时发生错误: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ 处理命令失败: {str(e)}")
        return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cancel 命令"""
    await update.message.reply_text("❌ 已取消提交")
    return ConversationHandler.END


def setup_handlers(application):
    """设置所有处理器"""
    
    # 表单提交对话处理器（deploy_build，固定命令）
    # 混合使用 CallbackQueryHandler 和 MessageHandler 时，使用默认的 per_message=False
    # 这是推荐配置，功能正常（警告已在模块级别抑制）
    form_conv = ConversationHandler(
        entry_points=[CommandHandler("deploy_build", deploy_build_command)],
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
    
    # 注册处理器
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(form_conv)  # deploy_build 表单处理器
    # 审批回调处理器
    application.add_handler(
        CallbackQueryHandler(
            ApprovalHandler.handle_approval_callback,
            pattern="^(approve|reject):"
        )
    )
    
    logger.info("所有处理器已注册，表单命令: /deploy_build")

