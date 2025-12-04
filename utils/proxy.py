"""代理配置工具模块"""
from typing import Optional, Dict
from urllib.parse import quote
from utils.logger import setup_logger

logger = setup_logger(__name__)


def get_proxy_config(project_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    获取代理配置（用于 requests 库）
    
    如果提供了 project_name，从项目配置中读取；否则从全局配置读取（用于 Telegram Bot）
    支持 SOCKS5 和 HTTP 代理协议
    
    注意：HTTP代理和SOCKS5代理都会同时支持HTTP和HTTPS请求
    - HTTP代理：通过CONNECT方法处理HTTPS请求
    - SOCKS5代理：原生支持所有协议
    
    Args:
        project_name: 项目名称（可选），如果提供则从项目配置读取，否则从全局配置读取
    
    Returns:
        代理字典，格式为 {"http": "proxy_url", "https": "proxy_url"}
        同时包含HTTP和HTTPS的代理配置，确保两种协议都能正常工作
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
        proxy_type = proxy_config.get('type', 'socks5').lower()  # 默认为socks5
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
        # 获取代理类型，默认为socks5（兼容旧配置）
        proxy_type = WorkflowManager.get_app_config("PROXY_TYPE", "socks5").lower()
    
    if not proxy_host or not proxy_port:
        return None
    
    # 支持的代理类型：socks5, socks5h, http, https
    # socks5h 表示 DNS 解析通过代理服务器进行（推荐用于 Telegram Bot）
    # socks5 表示 DNS 解析在客户端进行
    if proxy_type not in ['socks5', 'socks5h', 'http', 'https']:
        logger.warning(f"⚠️ 不支持的代理类型: {proxy_type}，使用默认值 socks5h")
        proxy_type = 'socks5h'
    
    # 如果用户指定了 socks5，自动转换为 socks5h（DNS 解析通过代理）
    # 这对于访问 Telegram API 很重要，因为本地可能无法解析 Telegram 域名
    if proxy_type == 'socks5':
        proxy_type = 'socks5h'
        logger.debug("将 socks5 转换为 socks5h（DNS 解析通过代理服务器）")
    
    # 构建代理URL（支持有/无用户名密码认证）
    if proxy_username and proxy_password:
        # 有用户名和密码：protocol://username:password@host:port
        username = quote(proxy_username, safe='')
        password = quote(proxy_password, safe='')
        proxy_url = f"{proxy_type}://{username}:{password}@{proxy_host}:{proxy_port}"
    else:
        # 无用户名和密码：protocol://host:port
        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
    
    # HTTP代理和SOCKS5代理都可以同时支持HTTP和HTTPS请求
    # HTTP代理通过CONNECT方法处理HTTPS请求，SOCKS5代理原生支持所有协议
    proxies = {
        "http": proxy_url,   # HTTP请求使用此代理
        "https": proxy_url   # HTTPS请求也使用此代理（HTTP代理通过CONNECT方法支持）
    }
    logger.debug(f"代理配置已获取: {proxy_type}://{proxy_host}:{proxy_port} (项目: {project_name or '全局'})，同时支持HTTP和HTTPS")
    return proxies


def get_proxy_url(project_name: Optional[str] = None) -> Optional[str]:
    """
    获取代理 URL（用于 Telegram Bot 的 HTTPXRequest proxy 参数）
    
    如果提供了 project_name，从项目配置中读取；否则从全局配置读取（用于 Telegram Bot）
    支持 SOCKS5 和 HTTP 代理协议
    
    根据官方文档，HTTPXRequest 的 proxy 参数可以是：
    - str: 代理 URL 字符串，例如 'socks5://127.0.0.1:3128' 或 'http://127.0.0.1:3128'
    - httpx.Proxy 对象
    - httpx.URL 对象
    
    注意：SOCKS5 支持需要安装 python-telegram-bot[socks]
    
    Args:
        project_name: 项目名称（可选），如果提供则从项目配置读取，否则从全局配置读取
    
    Returns:
        代理 URL 字符串，格式为 "socks5://proxy_host:proxy_port" 或 "http://proxy_host:proxy_port"
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
        proxy_type = proxy_config.get('type', 'socks5').lower()  # 默认为socks5
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
        # 获取代理类型，默认为socks5（兼容旧配置）
        proxy_type = WorkflowManager.get_app_config("PROXY_TYPE", "socks5").lower()
    
    if not proxy_host or not proxy_port:
        return None
    
    # 支持的代理类型：socks5, socks5h, http, https
    # socks5h 表示 DNS 解析通过代理服务器进行（推荐用于 Telegram Bot）
    # socks5 表示 DNS 解析在客户端进行
    if proxy_type not in ['socks5', 'socks5h', 'http', 'https']:
        logger.warning(f"⚠️ 不支持的代理类型: {proxy_type}，使用默认值 socks5h")
        proxy_type = 'socks5h'
    
    # 如果用户指定了 socks5，自动转换为 socks5h（DNS 解析通过代理）
    # 这对于访问 Telegram API 很重要，因为本地可能无法解析 Telegram 域名
    if proxy_type == 'socks5':
        proxy_type = 'socks5h'
        logger.debug("将 socks5 转换为 socks5h（DNS 解析通过代理服务器）")
    
    # 构建代理URL（支持有/无用户名密码认证）
    if proxy_username and proxy_password:
        # 有用户名和密码：protocol://username:password@host:port
        username = quote(proxy_username, safe='')
        password = quote(proxy_password, safe='')
        proxy_url = f"{proxy_type}://{username}:{password}@{proxy_host}:{proxy_port}"
    else:
        # 无用户名和密码：protocol://host:port
        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
    
    logger.debug(f"代理 URL 已获取: {proxy_type}://{proxy_host}:{proxy_port} (项目: {project_name or '全局'})")
    return proxy_url


def get_proxy_for_httpx(project_name: Optional[str] = None):
    """
    获取代理配置（用于 HTTPXRequest 的 proxy 参数）
    
    返回可以直接用于 HTTPXRequest 的代理对象：
    - SOCKS5 代理：返回 httpx.Proxy 对象（如果创建成功）或字符串 URL
    - HTTP/HTTPS 代理：返回字符串 URL
    
    如果提供了 project_name，从项目配置中读取；否则从全局配置读取（用于 Telegram Bot）
    
    Args:
        project_name: 项目名称（可选），如果提供则从项目配置读取，否则从全局配置读取
    
    Returns:
        代理对象（httpx.Proxy 或 str），如果未启用代理或配置不完整，返回 None
    """
    proxy_url = get_proxy_url(project_name)
    
    if not proxy_url:
        return None
    
    # 对于 SOCKS5 代理，尝试使用 httpx.Proxy 对象以确保正确支持
    if proxy_url.startswith("socks5://") or proxy_url.startswith("socks5h://"):
        try:
            import httpx
            proxy_obj = httpx.Proxy(proxy_url)
            return proxy_obj
        except Exception:
            # 如果创建 Proxy 对象失败，回退到字符串格式
            return proxy_url
    else:
        # 对于 HTTP/HTTPS 代理，直接使用字符串
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

