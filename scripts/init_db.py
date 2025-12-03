#!/usr/bin/env python3
"""
数据库初始化脚本

用于初始化数据库表结构、导入项目配置和应用配置。
这个脚本需要手动执行，不会在 Bot 启动时自动运行。

使用方法:
    python3 scripts/init_db.py

或者:
    python3 -m scripts.init_db
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from workflows.models import WorkflowManager
from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ============================================================================
# 敏感配置默认值（请在这里配置，运行脚本时会写入数据库）
# ============================================================================

# Telegram Bot Token
# 在这里填入你的 BOT_TOKEN，例如: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
DEFAULT_BOT_TOKEN = "xxxxxx"

# 审批人用户名
# 在这里填入审批人的 Telegram 用户名，例如: "username"（不带 @ 符号）
DEFAULT_APPROVER_USERNAME = "xxxxx"

# SSO 配置
DEFAULT_SSO_ENABLED: bool = True
DEFAULT_SSO_URL: str = "https://xxxxx"
DEFAULT_SSO_AUTH_TOKEN: str = ""
DEFAULT_SSO_AUTHORIZATION: str = ""

# 代理配置（如果需要，取消注释并填写）
# DEFAULT_PROXY_ENABLED: bool = True
# DEFAULT_PROXY_HOST: str = "proxy.example.com"
# DEFAULT_PROXY_PORT: int = 8080
# DEFAULT_PROXY_USERNAME: str = "username"
# DEFAULT_PROXY_PASSWORD: str = "password"

# ============================================================================


def init_database_structure():
    """初始化数据库表结构"""
    logger.info("=" * 60)
    logger.info("步骤 1/3: 初始化数据库表结构")
    logger.info("=" * 60)
    
    try:
        WorkflowManager._init_database()
        logger.info("✅ 数据库表结构初始化完成")
        return True
    except Exception as e:
        logger.error(f"❌ 数据库表结构初始化失败: {str(e)}", exc_info=True)
        return False


def init_project_options(options_file: Path = None):
    """从 options.json 导入项目配置到数据库"""
    logger.info("=" * 60)
    logger.info("步骤 2/3: 导入项目配置（从 options.json）")
    logger.info("=" * 60)
    
    if options_file is None:
        options_file = Path("config/options.json")
    
    if not options_file.exists():
        logger.error(f"❌ 项目配置文件不存在: {options_file}")
        logger.warning("请先创建 config/options.json 文件")
        return False
    
    try:
        # 检查数据库中是否已有配置
        conn = WorkflowManager._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM project_options WHERE config_key = 'projects'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.warning("⚠️  项目配置已存在于数据库中")
            response = input("是否要覆盖现有配置？(y/N): ").strip().lower()
            if response != 'y':
                logger.info("跳过项目配置导入")
                return True
        
        # 导入配置
        WorkflowManager._init_project_options(options_file)
        logger.info("✅ 项目配置已导入到数据库")
        return True
    except Exception as e:
        logger.error(f"❌ 项目配置导入失败: {str(e)}", exc_info=True)
        return False


def init_app_config():
    """从本脚本中定义的默认值初始化应用配置到数据库"""
    logger.info("=" * 60)
    logger.info("步骤 3/3: 初始化应用配置（从本脚本的默认值）")
    logger.info("=" * 60)
    
    try:
        # 初始化应用配置表结构
        WorkflowManager._init_app_config()
        
        # 从本脚本中定义的默认值初始化配置到数据库
        logger.info("正在从初始化脚本的默认值初始化配置...")
        
        # 初始化 BOT_TOKEN
        if DEFAULT_BOT_TOKEN and DEFAULT_BOT_TOKEN != "xxxxx":
            current_token = WorkflowManager.get_app_config("BOT_TOKEN", "")
            if not current_token:
                WorkflowManager.update_app_config("BOT_TOKEN", DEFAULT_BOT_TOKEN)
                logger.info("✅ BOT_TOKEN 已初始化到数据库")
            elif current_token != DEFAULT_BOT_TOKEN:
                # 如果数据库中的值与脚本中的默认值不同，提示是否更新
                logger.warning(f"⚠️  BOT_TOKEN 已存在于数据库中（当前值: {current_token[:10]}...）")
                logger.info(f"   脚本中的默认值: {DEFAULT_BOT_TOKEN[:10]}...")
                response = input("是否要更新 BOT_TOKEN？(y/N): ").strip().lower()
                if response == 'y':
                    WorkflowManager.update_app_config("BOT_TOKEN", DEFAULT_BOT_TOKEN)
                    logger.info("✅ BOT_TOKEN 已更新到数据库")
                else:
                    logger.info("跳过 BOT_TOKEN 更新")
            else:
                logger.info("ℹ️  BOT_TOKEN 已存在于数据库中，值与默认值相同，跳过初始化")
        else:
            logger.warning("⚠️  BOT_TOKEN 默认值为空或未配置，请稍后手动配置")
        
        # 初始化 APPROVER_USERNAME
        if DEFAULT_APPROVER_USERNAME and DEFAULT_APPROVER_USERNAME != "xxxx":
            current_approver = WorkflowManager.get_app_config("APPROVER_USERNAME", "")
            if not current_approver:
                WorkflowManager.update_app_config("APPROVER_USERNAME", DEFAULT_APPROVER_USERNAME)
                logger.info("✅ APPROVER_USERNAME 已初始化到数据库")
            else:
                logger.info("ℹ️  APPROVER_USERNAME 已存在于数据库中，跳过初始化")
        else:
            logger.warning("⚠️  APPROVER_USERNAME 默认值为空或未配置，请稍后手动配置")
        
        # 初始化 SSO 配置
        sso_initialized = False
        
        # SSO_ENABLED
        default_enabled_str = "true" if DEFAULT_SSO_ENABLED else "false"
        current_sso_enabled = WorkflowManager.get_app_config("SSO_ENABLED", "")
        if not current_sso_enabled:
            WorkflowManager.update_app_config("SSO_ENABLED", default_enabled_str)
            logger.info(f"✅ SSO_ENABLED 已初始化到数据库: {default_enabled_str}")
            sso_initialized = True
        else:
            logger.info(f"ℹ️  SSO_ENABLED 已存在于数据库中: {current_sso_enabled}")
        
        # SSO_URL
        if DEFAULT_SSO_URL and DEFAULT_SSO_URL != "https://xxxxx":
            current_sso_url = WorkflowManager.get_app_config("SSO_URL", "")
            if not current_sso_url:
                WorkflowManager.update_app_config("SSO_URL", DEFAULT_SSO_URL)
                logger.info(f"✅ SSO_URL 已初始化到数据库: {DEFAULT_SSO_URL}")
                sso_initialized = True
            else:
                logger.info(f"ℹ️  SSO_URL 已存在于数据库中")
        else:
            logger.warning("⚠️  SSO_URL 默认值为空或未配置，请稍后手动配置")
        
        # SSO_AUTH_TOKEN
        if DEFAULT_SSO_AUTH_TOKEN:
            current_sso_token = WorkflowManager.get_app_config("SSO_AUTH_TOKEN", "")
            if not current_sso_token:
                WorkflowManager.update_app_config("SSO_AUTH_TOKEN", DEFAULT_SSO_AUTH_TOKEN)
                logger.info("✅ SSO_AUTH_TOKEN 已初始化到数据库")
                sso_initialized = True
            else:
                logger.info("ℹ️  SSO_AUTH_TOKEN 已存在于数据库中，跳过初始化")
        else:
            logger.warning("⚠️  SSO_AUTH_TOKEN 默认值为空，请稍后手动配置")
        
        # SSO_AUTHORIZATION
        if DEFAULT_SSO_AUTHORIZATION:
            current_sso_auth = WorkflowManager.get_app_config("SSO_AUTHORIZATION", "")
            if not current_sso_auth:
                WorkflowManager.update_app_config("SSO_AUTHORIZATION", DEFAULT_SSO_AUTHORIZATION)
                logger.info("✅ SSO_AUTHORIZATION 已初始化到数据库")
                sso_initialized = True
            else:
                logger.info("ℹ️  SSO_AUTHORIZATION 已存在于数据库中，跳过初始化")
        else:
            logger.warning("⚠️  SSO_AUTHORIZATION 默认值为空，请稍后手动配置")
        
        # 初始化代理配置（如果在本脚本中定义了默认值）
        # 注意：代理配置通常不设置默认值，如果需要，请在本脚本开头取消注释并填写
        proxy_initialized = False
        
        # 获取当前模块的全局变量
        current_module = sys.modules[__name__]
        
        # PROXY_ENABLED（如果在本脚本中定义了默认值）
        if hasattr(current_module, 'DEFAULT_PROXY_ENABLED'):
            default_proxy_enabled_val = getattr(current_module, 'DEFAULT_PROXY_ENABLED')
            default_proxy_enabled = "true" if default_proxy_enabled_val else "false"
            current_proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
            if not current_proxy_enabled:
                WorkflowManager.update_app_config("PROXY_ENABLED", default_proxy_enabled)
                logger.info(f"✅ PROXY_ENABLED 已初始化到数据库: {default_proxy_enabled}")
                proxy_initialized = True
            else:
                logger.info(f"ℹ️  PROXY_ENABLED 已存在于数据库中: {current_proxy_enabled}")
        
        # PROXY_HOST（如果在本脚本中定义了默认值）
        if hasattr(current_module, 'DEFAULT_PROXY_HOST'):
            default_proxy_host = getattr(current_module, 'DEFAULT_PROXY_HOST')
            if default_proxy_host:
                current_proxy_host = WorkflowManager.get_app_config("PROXY_HOST", "")
                if not current_proxy_host:
                    WorkflowManager.update_app_config("PROXY_HOST", default_proxy_host)
                    logger.info("✅ PROXY_HOST 已初始化到数据库")
                    proxy_initialized = True
                else:
                    logger.info("ℹ️  PROXY_HOST 已存在于数据库中，跳过初始化")
        
        # PROXY_PORT（如果在本脚本中定义了默认值）
        if hasattr(current_module, 'DEFAULT_PROXY_PORT'):
            default_proxy_port = getattr(current_module, 'DEFAULT_PROXY_PORT')
            if default_proxy_port:
                current_proxy_port = WorkflowManager.get_app_config("PROXY_PORT", "")
                if not current_proxy_port:
                    WorkflowManager.update_app_config("PROXY_PORT", str(default_proxy_port))
                    logger.info("✅ PROXY_PORT 已初始化到数据库")
                    proxy_initialized = True
                else:
                    logger.info("ℹ️  PROXY_PORT 已存在于数据库中，跳过初始化")
        
        # PROXY_USERNAME（如果在本脚本中定义了默认值）
        if hasattr(current_module, 'DEFAULT_PROXY_USERNAME'):
            default_proxy_username = getattr(current_module, 'DEFAULT_PROXY_USERNAME')
            if default_proxy_username:
                current_proxy_username = WorkflowManager.get_app_config("PROXY_USERNAME", "")
                if not current_proxy_username:
                    WorkflowManager.update_app_config("PROXY_USERNAME", default_proxy_username)
                    logger.info("✅ PROXY_USERNAME 已初始化到数据库")
                    proxy_initialized = True
                else:
                    logger.info("ℹ️  PROXY_USERNAME 已存在于数据库中，跳过初始化")
        
        # PROXY_PASSWORD（如果在本脚本中定义了默认值）
        if hasattr(current_module, 'DEFAULT_PROXY_PASSWORD'):
            default_proxy_password = getattr(current_module, 'DEFAULT_PROXY_PASSWORD')
            if default_proxy_password:
                current_proxy_password = WorkflowManager.get_app_config("PROXY_PASSWORD", "")
                if not current_proxy_password:
                    WorkflowManager.update_app_config("PROXY_PASSWORD", default_proxy_password)
                    logger.info("✅ PROXY_PASSWORD 已初始化到数据库")
                    proxy_initialized = True
                else:
                    logger.info("ℹ️  PROXY_PASSWORD 已存在于数据库中，跳过初始化")
        
        # 注意：日志配置（LOG_LEVEL, LOG_FILE）在 utils/logger.py 中直接配置，不需要写入数据库
        
        logger.info("✅ 应用配置初始化完成")
        return True
    except Exception as e:
        logger.error(f"❌ 应用配置初始化失败: {str(e)}", exc_info=True)
        return False


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("数据库初始化脚本")
    logger.info("=" * 60)
    logger.info("")
    logger.info("此脚本将执行以下操作:")
    logger.info("  1. 初始化数据库表结构")
    logger.info("  2. 从 config/options.json 导入项目配置到数据库")
    logger.info("  3. 从本脚本中定义的默认值初始化应用配置到数据库")
    logger.info("")
    
    # 确认执行
    response = input("是否继续？(Y/n): ").strip().lower()
    if response and response != 'y':
        logger.info("已取消初始化")
        return
    
    logger.info("")
    
    # 执行初始化步骤
    success = True
    
    # 步骤 1: 初始化数据库表结构
    if not init_database_structure():
        success = False
        logger.error("❌ 数据库表结构初始化失败，终止初始化")
        return
    
    logger.info("")
    
    # 步骤 2: 导入项目配置
    if not init_project_options():
        success = False
        logger.error("❌ 项目配置导入失败，终止初始化")
        return
    
    logger.info("")
    
    # 步骤 3: 初始化应用配置
    if not init_app_config():
        success = False
        logger.error("❌ 应用配置初始化失败")
    
    logger.info("")
    logger.info("=" * 60)
    if success:
        logger.info("✅ 数据库初始化完成！")
        logger.info("")
        logger.info("提示:")
        logger.info("  - 如果配置了敏感信息（如 BOT_TOKEN、SSO_AUTH_TOKEN 等），请确保已正确设置")
        logger.info("  - 后续如需更新配置，可以:")
        logger.info("    1. 修改本脚本中的默认值后重新运行此脚本（会提示是否覆盖）")
        logger.info("    2. 修改 config/options.json 后重新运行此脚本（会提示是否覆盖）")
        logger.info("    3. 直接修改数据库中的配置")
    else:
        logger.error("❌ 数据库初始化未完全成功，请检查错误信息")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

