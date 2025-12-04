"""Bot主程序入口"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from telegram import Update, BotCommand
from telegram.ext import Application, ContextTypes
from telegram.error import NetworkError, TimedOut, RetryAfter
from config.settings import Settings
from utils.logger import setup_logger
from bot.handlers import setup_handlers
from workflows.models import WorkflowManager

logger = setup_logger(__name__)

# 重要：在导入 HTTPXRequest 之前，先导入 httpx
# 这样可以确保如果 httpx-socks 已安装，SOCKS5 支持会被正确注册
# 必须在导入 telegram.request 之前完成，因为 HTTPXRequest 内部会使用 httpx
import httpx
# HTTPXRequest 延迟导入，在 main() 函数中需要时再导入
# 这样可以确保 httpx 已经导入，httpx-socks 支持已注册


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
    
    # 获取代理配置（封装在 proxy.py 中，返回可直接用于 HTTPXRequest 的代理对象）
    from utils.proxy import get_proxy_for_httpx, get_proxy_url
    proxy = get_proxy_for_httpx()
    
    # 获取代理 URL 用于日志显示
    proxy_url = get_proxy_url()
    proxy_info = ""
    if proxy:
        request_kwargs["proxy"] = proxy
        if proxy_url:
            # 提取代理主机和端口用于日志显示（隐藏用户名密码）
            display_url = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
            logger.info(f"✅ 已配置代理: {display_url}")
            # 从 URL 中提取主机和端口
            if '@' in proxy_url:
                url_part = proxy_url.split('@')[-1]
            else:
                url_part = proxy_url.split('://')[-1] if '://' in proxy_url else proxy_url
            if ':' in url_part:
                host_port = url_part.split('/')[0]  # 移除路径部分
                proxy_info = f", 代理: {host_port}"
            if proxy_url.startswith("socks5h://"):
                logger.info("   ℹ️ 使用 socks5h:// 协议（DNS 解析通过代理服务器）")
    else:
        logger.info("ℹ️ 未启用代理")
    
    # 延迟导入 HTTPXRequest，确保 httpx 已经导入（httpx-socks 支持已注册）
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(**request_kwargs)
    
    # 创建应用（使用优化的请求客户端）
    # 注意：需要同时设置 request 和 get_updates_request，确保普通请求和轮询更新都使用代理
    bot_token = WorkflowManager.get_app_config("BOT_TOKEN", "")
    application = (
        Application.builder()
        .token(bot_token)
        .request(request)
        .get_updates_request(request)
        .build()
    )
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