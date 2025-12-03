"""代理配置工具模块"""
from typing import Optional, Dict
from urllib.parse import quote
from utils.logger import setup_logger

logger = setup_logger(__name__)


def get_proxy_config(project_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    获取代理配置（用于 requests 库）
    
    如果提供了 project_name，从项目配置中读取；否则从全局配置读取（用于 Telegram Bot）
    
    Args:
        project_name: 项目名称（可选），如果提供则从项目配置读取，否则从全局配置读取
    
    Returns:
        代理字典，格式为 {"http": "http://proxy_url", "https": "http://proxy_url"}
        如果未启用代理或配置不完整，返回 None
    """
    # 延迟导入，避免循环导入
    from workflows.models import WorkflowManager
    
    if project_name:
        # 从项目配置中读取
        options = WorkflowManager.get_project_options()
        projects = options.get('projects', {})
        project_config = projects.get(project_name, {})
        proxy_config = project_config.get('proxy', {})
        
        proxy_enabled = proxy_config.get('enabled', False)
        if not proxy_enabled:
            return None
        
        proxy_host = proxy_config.get('host', '')
        proxy_port = proxy_config.get('port', 0)
        proxy_username = proxy_config.get('username', '')
        proxy_password = proxy_config.get('password', '')
    else:
        # 从全局配置读取（用于 Telegram Bot）
        proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
        if not proxy_enabled or proxy_enabled.lower() != "true":
            return None
        
        proxy_host = WorkflowManager.get_app_config("PROXY_HOST", "")
        proxy_port_str = WorkflowManager.get_app_config("PROXY_PORT", "")
        try:
            proxy_port = int(proxy_port_str) if proxy_port_str else 0
        except ValueError:
            proxy_port = 0
        
        proxy_username = WorkflowManager.get_app_config("PROXY_USERNAME", "")
        proxy_password = WorkflowManager.get_app_config("PROXY_PASSWORD", "")
    
    if not proxy_host or not proxy_port:
        return None
    
    # 构建代理URL（支持有/无用户名密码认证）
    # 如果配置了用户名和密码，使用认证格式；否则使用无认证格式
    if proxy_username and proxy_password:
        # 有用户名和密码：http://username:password@host:port
        username = quote(proxy_username, safe='')
        password = quote(proxy_password, safe='')
        proxy_url = f"http://{username}:{password}@{proxy_host}:{proxy_port}"
    else:
        # 无用户名和密码：http://host:port
        proxy_url = f"http://{proxy_host}:{proxy_port}"
    
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    logger.debug(f"代理配置已获取: {proxy_host}:{proxy_port} (项目: {project_name or '全局'})")
    return proxies


def get_proxy_url(project_name: Optional[str] = None) -> Optional[str]:
    """
    获取代理 URL（用于 Telegram Bot 的 proxy_url 参数）
    
    如果提供了 project_name，从项目配置中读取；否则从全局配置读取（用于 Telegram Bot）
    
    Args:
        project_name: 项目名称（可选），如果提供则从项目配置读取，否则从全局配置读取
    
    Returns:
        代理 URL 字符串，格式为 "http://proxy_host:proxy_port" 或 "http://username:password@proxy_host:proxy_port"
        如果未启用代理或配置不完整，返回 None
    """
    # 延迟导入，避免循环导入
    from workflows.models import WorkflowManager
    
    if project_name:
        # 从项目配置中读取
        options = WorkflowManager.get_project_options()
        projects = options.get('projects', {})
        project_config = projects.get(project_name, {})
        proxy_config = project_config.get('proxy', {})
        
        proxy_enabled = proxy_config.get('enabled', False)
        if not proxy_enabled:
            return None
        
        proxy_host = proxy_config.get('host', '')
        proxy_port = proxy_config.get('port', 0)
        proxy_username = proxy_config.get('username', '')
        proxy_password = proxy_config.get('password', '')
    else:
        # 从全局配置读取（用于 Telegram Bot）
        proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
        if not proxy_enabled or proxy_enabled.lower() != "true":
            return None
        
        proxy_host = WorkflowManager.get_app_config("PROXY_HOST", "")
        proxy_port_str = WorkflowManager.get_app_config("PROXY_PORT", "")
        try:
            proxy_port = int(proxy_port_str) if proxy_port_str else 0
        except ValueError:
            proxy_port = 0
        
        proxy_username = WorkflowManager.get_app_config("PROXY_USERNAME", "")
        proxy_password = WorkflowManager.get_app_config("PROXY_PASSWORD", "")
    
    if not proxy_host or not proxy_port:
        return None
    
    # 构建代理URL（支持有/无用户名密码认证）
    # 如果配置了用户名和密码，使用认证格式；否则使用无认证格式
    if proxy_username and proxy_password:
        # 有用户名和密码：http://username:password@host:port
        username = quote(proxy_username, safe='')
        password = quote(proxy_password, safe='')
        proxy_url = f"http://{username}:{password}@{proxy_host}:{proxy_port}"
    else:
        # 无用户名和密码：http://host:port
        proxy_url = f"http://{proxy_host}:{proxy_port}"
    
    logger.debug(f"代理 URL 已获取: {proxy_host}:{proxy_port} (项目: {project_name or '全局'})")
    return proxy_url


def is_proxy_enabled() -> bool:
    """
    检查代理是否启用
    
    Returns:
        如果代理已启用返回 True，否则返回 False
    """
    # 延迟导入，避免循环导入
    from workflows.models import WorkflowManager
    
    proxy_enabled = WorkflowManager.get_app_config("PROXY_ENABLED", "")
    return proxy_enabled.lower() == "true" if proxy_enabled else False

