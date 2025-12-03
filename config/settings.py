"""配置管理"""
from typing import Dict, List, Optional


class Settings:
    """应用配置类（从数据库读取配置）"""
    
    _config_cache: Dict[str, str] = {}
    _cache_loaded = False
    
    @classmethod
    def _get_config(cls, key: str, default: str = "") -> str:
        """从数据库获取配置值（如果数据库中没有，返回默认值）"""
        # 首次加载时，从数据库加载所有配置到缓存
        if not cls._cache_loaded:
            try:
                # 延迟导入避免循环依赖
                from workflows.models import WorkflowManager
                all_config = WorkflowManager.get_all_app_config()
                cls._config_cache.update(all_config)
                cls._cache_loaded = True
            except Exception:
                # 如果数据库未初始化，返回默认值
                cls._cache_loaded = True
                return default
        
        # 如果缓存中有，直接返回
        if key in cls._config_cache:
            return cls._config_cache[key]
        
        # 如果数据库中没有，返回默认值
        return default
    
    @classmethod
    def _refresh_cache(cls):
        """刷新配置缓存（从数据库重新加载）"""
        try:
            # 延迟导入避免循环依赖
            from workflows.models import WorkflowManager
            all_config = WorkflowManager.get_all_app_config()
            cls._config_cache.clear()
            cls._config_cache.update(all_config)
            cls._cache_loaded = True
        except Exception:
            cls._cache_loaded = False
    
    # Telegram Bot配置
    # 在这里配置你的 BOT_TOKEN（首次启动时会自动写入数据库）
    # 在这里填入你的 BOT_TOKEN，例如: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    DEFAULT_BOT_TOKEN = "xxxxx"
    
    @classmethod
    def _get_bot_token(cls) -> str:
        return cls._get_config("BOT_TOKEN", cls.DEFAULT_BOT_TOKEN)
    BOT_TOKEN = ""
    
    # 从数据库获取所有项目的群组ID（合并所有项目的 group_ids）
    @classmethod
    def _get_group_ids(cls) -> List[int]:
        """从数据库读取所有项目的群组ID并合并去重"""
        # 延迟导入避免循环依赖
        from workflows.models import WorkflowManager
        options = WorkflowManager.get_project_options()
        projects = options.get("projects", {})
        
        # 收集所有项目的 group_ids
        all_group_ids = set()  # 使用 set 自动去重
        for project_name, project_data in projects.items():
            group_ids = project_data.get("group_ids", [])
            if group_ids:
                # 确保是列表格式
                if isinstance(group_ids, list):
                    for gid in group_ids:
                        try:
                            all_group_ids.add(int(gid))
                        except (ValueError, TypeError):
                            continue
                elif isinstance(group_ids, (int, str)):
                    try:
                        all_group_ids.add(int(group_ids))
                    except (ValueError, TypeError):
                        continue
        
        return sorted(list(all_group_ids))  # 返回排序后的列表
    
    GROUP_IDS: List[int] = []
    
    # 审批人配置
    # 在这里配置审批人用户名（首次启动时会自动写入数据库）
    # 在这里填入审批人的 Telegram 用户名，例如: "xxxxx"（不带 @ 符号）
    DEFAULT_APPROVER_USERNAME = "xxxx"  
    
    @classmethod
    def _get_approver_user_id(cls) -> int:
        value = cls._get_config("APPROVER_USER_ID", "0")
        try:
            return int(value) if value else 0
        except ValueError:
            return 0
    
    APPROVER_USER_ID: int = 0
    APPROVER_USERNAME: str = ""
    
    @classmethod
    def is_approver_restricted(cls) -> bool:
        """检查是否限制了审批人"""
        return cls.APPROVER_USER_ID != 0 or bool(cls.APPROVER_USERNAME)
    
    # 外部API配置
    API_BASE_URL: str = ""
    API_ENDPOINT: str = "/workflows/sync"
    API_TOKEN: str = ""
    API_TIMEOUT: int = 30
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/bot.log"
    
    # 表单选项配置文件路径
    OPTIONS_FILE: str = "./config/options.json"
    
    # 连接池配置（优化 Telegram API 性能）
    CONNECTION_POOL_SIZE: int = 200
    HTTP_READ_TIMEOUT: float = 30.0
    HTTP_WRITE_TIMEOUT: float = 10.0
    HTTP_CONNECT_TIMEOUT: float = 10.0
    
    # 代理配置
    PROXY_ENABLED: bool = False
    PROXY_HOST: str = ""
    PROXY_PORT: int = 0
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""
    
    # SSO 配置
    # 在这里配置 SSO 系统相关参数（首次启动时会自动写入数据库）
    DEFAULT_SSO_ENABLED: bool = True
    DEFAULT_SSO_URL: str = "https://xxxxx"
    DEFAULT_SSO_AUTH_TOKEN: str = ""
    DEFAULT_SSO_AUTHORIZATION: str = ""
    
    SSO_ENABLED: bool = False
    SSO_URL: str = ""
    SSO_AUTH_TOKEN: str = ""
    SSO_AUTHORIZATION: str = ""
    
    @classmethod
    def get_sso_enabled(cls) -> bool:
        """获取 SSO 是否启用"""
        value = cls._get_config("SSO_ENABLED", "true" if cls.DEFAULT_SSO_ENABLED else "false")
        return value.lower() == "true"
    
    @classmethod
    def get_sso_url(cls) -> str:
        """获取 SSO 系统 URL"""
        return cls._get_config("SSO_URL", cls.DEFAULT_SSO_URL)
    
    @classmethod
    def get_sso_auth_token(cls) -> str:
        """获取 SSO Auth Token"""
        return cls._get_config("SSO_AUTH_TOKEN", cls.DEFAULT_SSO_AUTH_TOKEN)
    
    @classmethod
    def get_sso_authorization(cls) -> str:
        """获取 SSO Authorization"""
        return cls._get_config("SSO_AUTHORIZATION", cls.DEFAULT_SSO_AUTHORIZATION)
    
    @classmethod
    def load_from_db(cls):
        """从数据库加载所有配置（在初始化后调用）"""
        cls._refresh_cache()
        
        # 如果数据库中没有配置但代码中有默认值，自动初始化到数据库
        try:
            from workflows.models import WorkflowManager
            from utils.logger import setup_logger
            logger = setup_logger(__name__)
            
            # 初始化 BOT_TOKEN
            current_token = cls._get_config("BOT_TOKEN", cls.DEFAULT_BOT_TOKEN)
            if not current_token and cls.DEFAULT_BOT_TOKEN:
                WorkflowManager.update_app_config("BOT_TOKEN", cls.DEFAULT_BOT_TOKEN)
                cls._refresh_cache()  # 刷新缓存
                logger.info("✅ BOT_TOKEN 已从 settings.py 初始化到数据库")
            
            # 初始化 APPROVER_USERNAME
            current_approver = cls._get_config("APPROVER_USERNAME", cls.DEFAULT_APPROVER_USERNAME)
            if not current_approver and cls.DEFAULT_APPROVER_USERNAME:
                WorkflowManager.update_app_config("APPROVER_USERNAME", cls.DEFAULT_APPROVER_USERNAME)
                cls._refresh_cache()  # 刷新缓存
                logger.info("✅ APPROVER_USERNAME 已从 settings.py 初始化到数据库")
            
            # 初始化 SSO 配置（如果数据库中没有，则从 settings.py 中的默认值初始化）
            sso_initialized = False
            
            # SSO_ENABLED（如果默认值与数据库中的值不同，则更新）
            current_sso_enabled = cls._get_config("SSO_ENABLED", "")
            default_enabled_str = "true" if cls.DEFAULT_SSO_ENABLED else "false"
            if not current_sso_enabled or current_sso_enabled.lower() != default_enabled_str.lower():
                WorkflowManager.update_app_config("SSO_ENABLED", default_enabled_str)
                logger.info(f"✅ SSO_ENABLED 已从 settings.py 更新到数据库: {default_enabled_str}")
                sso_initialized = True
            
            # SSO_URL（仅在数据库中没有且默认值不为空时初始化）
            current_sso_url = cls._get_config("SSO_URL", "")
            if not current_sso_url and cls.DEFAULT_SSO_URL:
                WorkflowManager.update_app_config("SSO_URL", cls.DEFAULT_SSO_URL)
                logger.info(f"✅ SSO_URL 已从 settings.py 初始化到数据库: {cls.DEFAULT_SSO_URL}")
                sso_initialized = True
            
            # SSO_AUTH_TOKEN（仅在数据库中没有且默认值不为空时初始化）
            current_sso_token = cls._get_config("SSO_AUTH_TOKEN", "")
            if not current_sso_token and cls.DEFAULT_SSO_AUTH_TOKEN:
                WorkflowManager.update_app_config("SSO_AUTH_TOKEN", cls.DEFAULT_SSO_AUTH_TOKEN)
                logger.info("✅ SSO_AUTH_TOKEN 已从 settings.py 初始化到数据库")
                sso_initialized = True
            
            # SSO_AUTHORIZATION（仅在数据库中没有且默认值不为空时初始化）
            current_sso_auth = cls._get_config("SSO_AUTHORIZATION", "")
            if not current_sso_auth and cls.DEFAULT_SSO_AUTHORIZATION:
                WorkflowManager.update_app_config("SSO_AUTHORIZATION", cls.DEFAULT_SSO_AUTHORIZATION)
                logger.info("✅ SSO_AUTHORIZATION 已从 settings.py 初始化到数据库")
                sso_initialized = True
            
            if sso_initialized:
                cls._refresh_cache()  # 刷新缓存
        except Exception as e:
            logger.warning(f"初始化配置到数据库时发生错误: {e}")
            pass  # 如果数据库未初始化，忽略
        
        # 更新类属性
        cls.BOT_TOKEN = cls._get_config("BOT_TOKEN", cls.DEFAULT_BOT_TOKEN)
        cls.GROUP_IDS = cls._get_group_ids()
        cls.APPROVER_USER_ID = cls._get_approver_user_id()
        cls.APPROVER_USERNAME = cls._get_config("APPROVER_USERNAME", cls.DEFAULT_APPROVER_USERNAME)
        cls.API_BASE_URL = cls._get_config("API_BASE_URL", "")
        cls.API_ENDPOINT = cls._get_config("API_ENDPOINT", "/workflows/sync")
        cls.API_TOKEN = cls._get_config("API_TOKEN", "")
        cls.API_TIMEOUT = int(cls._get_config("API_TIMEOUT", "30"))
        cls.LOG_LEVEL = cls._get_config("LOG_LEVEL", "INFO")
        cls.LOG_FILE = cls._get_config("LOG_FILE", "./logs/bot.log")
        cls.OPTIONS_FILE = cls._get_config("OPTIONS_FILE", "./config/options.json")
        # 连接池配置
        cls.CONNECTION_POOL_SIZE = int(cls._get_config("CONNECTION_POOL_SIZE", "50"))
        cls.HTTP_READ_TIMEOUT = float(cls._get_config("HTTP_READ_TIMEOUT", "30.0"))
        cls.HTTP_WRITE_TIMEOUT = float(cls._get_config("HTTP_WRITE_TIMEOUT", "10.0"))
        cls.HTTP_CONNECT_TIMEOUT = float(cls._get_config("HTTP_CONNECT_TIMEOUT", "10.0"))
        # 代理配置
        cls.PROXY_ENABLED = cls._get_config("PROXY_ENABLED", "false").lower() == "true"
        cls.PROXY_HOST = cls._get_config("PROXY_HOST", "")
        cls.PROXY_PORT = int(cls._get_config("PROXY_PORT", "0"))
        cls.PROXY_USERNAME = cls._get_config("PROXY_USERNAME", "")
        cls.PROXY_PASSWORD = cls._get_config("PROXY_PASSWORD", "")
        # SSO 配置
        cls.SSO_ENABLED = cls.get_sso_enabled()
        cls.SSO_URL = cls.get_sso_url()
        cls.SSO_AUTH_TOKEN = cls.get_sso_auth_token()
        cls.SSO_AUTHORIZATION = cls.get_sso_authorization()
    
    # 表单选项配置（从数据库加载，缓存）
    _options_data: Dict = None
    
    @classmethod
    def load_options(cls) -> Dict:
        """从数据库加载选项配置"""
        if cls._options_data is not None:
            return cls._options_data
        
        # 延迟导入避免循环导入
        from workflows.models import WorkflowManager
        from utils.logger import setup_logger
        logger = setup_logger(__name__)
        
        try:
            # 从数据库加载配置
            cls._options_data = WorkflowManager.get_project_options()
            logger.info("✅ 从数据库加载项目配置成功")
            return cls._options_data
        except Exception as e:
            logger.error(f"从数据库加载项目配置失败: {str(e)}", exc_info=True)
            # 如果数据库中没有配置，返回空字典
            cls._options_data = {"projects": {}}
            return cls._options_data
    
    @classmethod
    def get_projects(cls) -> List[str]:
        """获取项目列表"""
        options = cls.load_options()
        return list(options.get("projects", {}).keys())
    
    @classmethod
    def get_environments(cls, project: str) -> List[str]:
        """根据项目获取环境列表"""
        options = cls.load_options()
        project_data = options.get("projects", {}).get(project, {})
        return project_data.get("environments", [])
    
    @classmethod
    def get_services(cls, project: str, environment: str = None) -> List[str]:
        """
        根据项目和环境获取服务列表
        
        Args:
            project: 项目名称
            environment: 环境名称（可选，如果提供则返回该环境对应的服务）
        
        Returns:
            服务列表
        """
        options = cls.load_options()
        project_data = options.get("projects", {}).get(project, {})
        services = project_data.get("services", [])
        
        # 如果 services 是字典（按环境区分），根据环境返回对应服务
        if isinstance(services, dict):
            if environment:
                return services.get(environment, [])
            else:
                # 如果没有指定环境，返回所有环境的服务（去重）
                all_services = []
                for env_services in services.values():
                    all_services.extend(env_services)
                return list(set(all_services))  # 去重
        
        # 如果 services 是列表（旧格式，兼容性处理）
        return services if isinstance(services, list) else []
    
    @classmethod
    def get_group_ids_by_project(cls, project: str) -> List[int]:
        """
        根据项目获取群组ID列表
        
        Args:
            project: 项目名称
        
        Returns:
            群组ID列表
        
        Raises:
            ValueError: 如果项目未配置群组ID
        """
        options = cls.load_options()
        project_data = options.get("projects", {}).get(project, {})
        group_ids = project_data.get("group_ids", [])
        
        # 如果项目未配置群组ID，抛出异常
        if not group_ids:
            raise ValueError(f"项目 '{project}' 未配置 group_ids，请在 config/options.json 中为该项目配置 group_ids")
        
        # 确保返回的是整数列表
        if isinstance(group_ids, list):
            result = [int(gid) for gid in group_ids if str(gid).lstrip('-').isdigit()]
            if not result:
                raise ValueError(f"项目 '{project}' 的 group_ids 配置无效，请确保配置的是有效的群组ID（整数）")
            return result
        elif isinstance(group_ids, (int, str)):
            # 如果是单个值，转换为列表
            try:
                return [int(group_ids)]
            except (ValueError, TypeError):
                raise ValueError(f"项目 '{project}' 的 group_ids 配置无效，请确保配置的是有效的群组ID（整数）")
        
        raise ValueError(f"项目 '{project}' 的 group_ids 配置格式不正确")
    
    @classmethod
    def validate(cls):
        """验证必要的配置项"""
        # 检查 BOT_TOKEN
        if not cls.BOT_TOKEN:
            raise ValueError("缺少必要的配置项: BOT_TOKEN")
        
        # 检查 options.json 中是否有项目配置了 group_ids
        options = cls.load_options()
        projects = options.get("projects", {})
        if not projects:
            raise ValueError("缺少项目配置，请在 config/options.json 中配置至少一个项目")
        
        # 检查每个项目是否配置了 group_ids
        missing_group_ids = []
        for project_name, project_data in projects.items():
            group_ids = project_data.get("group_ids", [])
            if not group_ids:
                missing_group_ids.append(project_name)
        
        if missing_group_ids:
            raise ValueError(
                f"以下项目未配置 group_ids: {', '.join(missing_group_ids)}。"
                f"请在 config/options.json 中为这些项目配置 group_ids"
            )
        
        return True
    
    @classmethod
    def is_api_enabled(cls) -> bool:
        """检查是否启用了外部API同步"""
        return bool(cls.API_BASE_URL)
    
    @classmethod
    def get_proxy_url(cls) -> Optional[str]:
        """
        获取代理URL（如果启用了代理）
        
        Returns:
            代理URL字符串，格式: http://username:password@host:port
            如果未启用代理或配置不完整，返回 None
        """
        if not cls.PROXY_ENABLED:
            return None
        
        if not cls.PROXY_HOST or not cls.PROXY_PORT:
            return None
        
        # 构建代理URL
        if cls.PROXY_USERNAME and cls.PROXY_PASSWORD:
            # 需要URL编码用户名和密码
            from urllib.parse import quote
            username = quote(cls.PROXY_USERNAME, safe='')
            password = quote(cls.PROXY_PASSWORD, safe='')
            return f"http://{username}:{password}@{cls.PROXY_HOST}:{cls.PROXY_PORT}"
        else:
            return f"http://{cls.PROXY_HOST}:{cls.PROXY_PORT}"

