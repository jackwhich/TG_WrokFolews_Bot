"""Bot主程序入口"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from telegram import Update, BotCommand
from telegram.ext import Application, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut, RetryAfter
from config.settings import Settings
from utils.logger import setup_logger
from bot.handlers import setup_handlers
from workflows.models import WorkflowManager

logger = setup_logger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理器"""
    error = context.error
    
    # 处理网络错误（通常是临时性的，不应该作为错误记录）
    if isinstance(error, NetworkError):
        error_msg = str(error)
        # Bad Gateway、Gateway Timeout 等通常是临时性网络问题
        # python-telegram-bot 会自动重试，我们只需要记录警告
        if "Bad Gateway" in error_msg or "Gateway Timeout" in error_msg:
            logger.warning(
                f"⚠️ Telegram API 网络错误（临时性，将自动重试）: {error_msg}"
            )
            return  # 不尝试发送错误消息给用户
        
        # 其他网络错误也记录为警告
        logger.warning(f"⚠️ Telegram API 网络错误: {error_msg}")
        return
    
    # 处理超时错误（也是临时性的）
    if isinstance(error, TimedOut):
        logger.warning(f"⚠️ Telegram API 请求超时（将自动重试）: {str(error)}")
        return
    
    # 处理速率限制错误（RetryAfter）
    if isinstance(error, RetryAfter):
        logger.warning(f"⚠️ Telegram API 速率限制，将在 {error.retry_after} 秒后重试")
        return
    
    # 对于其他错误，记录详细信息
    if update is None:
        # update 为 None 时，通常是轮询过程中的错误
        logger.error(f"轮询更新时发生错误: {error}", exc_info=error)
    else:
        logger.error(f"更新 {update.update_id if hasattr(update, 'update_id') else 'N/A'} 导致错误: {error}", exc_info=error)
        
        # 添加调试信息
        if update.message:
            logger.debug(f"错误时的消息内容: {update.message.text}")
        if update.callback_query:
            logger.debug(f"错误时的回调数据: {update.callback_query.data}")
        
        # 尝试向用户发送错误消息（仅当有有效消息时）
        if update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ 发生了一个错误，请稍后重试。"
                )
            except Exception as e:
                # 记录异常但不中断程序
                logger.debug(f"发送错误消息失败: {str(e)}")


def main():
    """主函数"""
    # 从数据库加载配置到 Settings（不进行初始化）
    # 注意：数据库初始化需要通过 scripts/init_db.py 手动执行
    try:
        # 确保数据库连接可用（但不初始化表结构）
        WorkflowManager._get_connection()
        
        # 从数据库加载配置到 Settings
        Settings.load_from_db()
        logger.info("✅ 配置已从数据库加载到 Settings")
    except Exception as e:
        logger.error(f"❌ 从数据库加载配置失败: {str(e)}", exc_info=True)
        logger.error("请先运行初始化脚本: python3 scripts/init_db.py")
        return
    
    # 验证配置（在从数据库加载后）
    try:
        Settings.validate()
    except ValueError as e:
        logger.error(f"配置验证失败: {e}")
        logger.warning("请检查数据库中的配置项，如需初始化或更新配置，请运行: python3 scripts/init_db.py")
        return
    
    # 创建优化的 HTTP 请求客户端（使用连接池和长连接）
    # 配置连接池以复用连接，减少连接建立时间，提升性能
    # 连接池配置从环境变量/数据库读取，方便调整
    request_kwargs = {
        "connection_pool_size": Settings.CONNECTION_POOL_SIZE,  # 连接池大小（可配置）
        "read_timeout": Settings.HTTP_READ_TIMEOUT,             # 读取超时（可配置）
        "write_timeout": Settings.HTTP_WRITE_TIMEOUT,           # 写入超时（可配置）
        "connect_timeout": Settings.HTTP_CONNECT_TIMEOUT,       # 连接超时（可配置）
        "http_version": "1.1"                                   # 使用 HTTP/1.1（Telegram API 支持）
    }
    
    # 如果启用了代理，添加代理配置
    proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
    proxy_url = None
    if proxy_enabled and proxy_enabled.lower() == "true":
        proxy_host = WorkflowManager.get_app_config("PROXY_HOST", "")
        proxy_port_str = WorkflowManager.get_app_config("PROXY_PORT", "")
        try:
            proxy_port = int(proxy_port_str) if proxy_port_str else 0
        except ValueError:
            proxy_port = 0
        
        if proxy_host and proxy_port:
            proxy_username = WorkflowManager.get_app_config("PROXY_USERNAME", "")
            proxy_password = WorkflowManager.get_app_config("PROXY_PASSWORD", "")
            if proxy_username and proxy_password:
                from urllib.parse import quote
                username = quote(proxy_username, safe='')
                password = quote(proxy_password, safe='')
                proxy_url = f"http://{username}:{password}@{proxy_host}:{proxy_port}"
            else:
                proxy_url = f"http://{proxy_host}:{proxy_port}"
    
    if proxy_url:
        request_kwargs["proxy_url"] = proxy_url
        logger.info(f"✅ 已配置代理: {proxy_host}:{proxy_port}")
    else:
        logger.info("ℹ️ 未启用代理")
    
    request = HTTPXRequest(**request_kwargs)
    
    # 创建应用（使用优化的请求客户端）
    bot_token = WorkflowManager.get_app_config("BOT_TOKEN", "")
    application = Application.builder().token(bot_token).request(request).build()
    
    proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
    proxy_info = ""
    if proxy_enabled and proxy_enabled.lower() == "true":
        proxy_host = WorkflowManager.get_app_config("PROXY_HOST", "")
        proxy_port = WorkflowManager.get_app_config("PROXY_PORT", "")
        if proxy_host and proxy_port:
            proxy_info = f", 代理: {proxy_host}:{proxy_port}"
    logger.info(
        f"✅ Bot应用已创建（连接池优化 - 连接池大小: {Settings.CONNECTION_POOL_SIZE}, "
        f"读取超时: {Settings.HTTP_READ_TIMEOUT}s, 写入超时: {Settings.HTTP_WRITE_TIMEOUT}s, "
        f"连接超时: {Settings.HTTP_CONNECT_TIMEOUT}s{proxy_info}）"
    )
    
    # 设置处理器
    setup_handlers(application)
    
    # 设置错误处理器
    application.add_error_handler(error_handler)
    
    # 注册Bot命令列表（让用户在输入 / 时看到命令）
    async def register_commands(application: Application) -> None:
        """注册Bot命令列表"""
        commands = [
            BotCommand("start", "开始使用Bot"),
            BotCommand("deploy_build", "申请测试环境服务发版"),
            BotCommand("cancel", "取消当前操作"),
        ]
        
        try:
            await application.bot.set_my_commands(commands)
            logger.info(f"✅ Bot命令列表已注册: {[cmd.command for cmd in commands]}")
        except Exception as e:
            logger.error(f"❌ 注册Bot命令列表失败: {str(e)}", exc_info=True)
    
    # 设置post_init回调（在Bot启动后立即执行）
    application.post_init = register_commands
    
    # 启动Bot
    logger.info("Bot启动中...")
    logger.info("🤖 Bot已启动，按 Ctrl+C 停止")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("👋 Bot已停止")


if __name__ == "__main__":
    main()