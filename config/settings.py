"""配置管理"""
from typing import Dict, List, Optional


class Settings:
    """应用配置类（API配置和项目配置管理）"""
    
    @classmethod
    def get_group_ids(cls) -> List[int]:
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
    
    # ============================================================================
    # API 配置和连接池配置（类属性，从数据库加载）
    # 注意：这些类属性的初始值只是占位符，实际值通过 load_from_db() 从数据库加载
    # 所有默认值都在 scripts/init_db.py 中定义
    # ============================================================================
    
    API_BASE_URL: str = ""  # 从数据库加载
    API_ENDPOINT: str = ""  # 从数据库加载
    API_TOKEN: str = ""  # 从数据库加载
    API_TIMEOUT: int = 30  # 从数据库加载（如果数据库中没有，使用此默认值）
    
    # 连接池配置（优化 Telegram API 性能）
    CONNECTION_POOL_SIZE: int = 50  # 从数据库加载（如果数据库中没有，使用此默认值）
    HTTP_READ_TIMEOUT: float = 30.0  # 从数据库加载（如果数据库中没有，使用此默认值）
    HTTP_WRITE_TIMEOUT: float = 10.0  # 从数据库加载（如果数据库中没有，使用此默认值）
    HTTP_CONNECT_TIMEOUT: float = 10.0  # 从数据库加载（如果数据库中没有，使用此默认值）
    
    @classmethod
    def load_from_db(cls):
        """从数据库加载 API 配置到类属性"""
        # 注意：数据库初始化需要通过 scripts/init_db.py 手动执行
        # 此方法只加载 API 配置和连接池配置到类属性
        # 其他配置（BOT_TOKEN、SSO配置等）直接通过 WorkflowManager.get_app_config() 从数据库读取
        
        # 从数据库加载 API 配置到类属性
        # 注意：如果数据库中没有配置，会使用类属性中定义的默认值作为后备
        from workflows.models import WorkflowManager
        cls.API_BASE_URL = WorkflowManager.get_app_config("API_BASE_URL", "") or cls.API_BASE_URL
        cls.API_ENDPOINT = WorkflowManager.get_app_config("API_ENDPOINT", "") or "/workflows/sync"
        cls.API_TOKEN = WorkflowManager.get_app_config("API_TOKEN", "") or cls.API_TOKEN
        api_timeout_str = WorkflowManager.get_app_config("API_TIMEOUT", "")
        cls.API_TIMEOUT = int(api_timeout_str) if api_timeout_str else cls.API_TIMEOUT
        
        # 从数据库加载连接池配置到类属性
        # 注意：如果数据库中没有配置，会使用类属性中定义的默认值作为后备
        connection_pool_size_str = WorkflowManager.get_app_config("CONNECTION_POOL_SIZE", "")
        cls.CONNECTION_POOL_SIZE = int(connection_pool_size_str) if connection_pool_size_str else cls.CONNECTION_POOL_SIZE
        http_read_timeout_str = WorkflowManager.get_app_config("HTTP_READ_TIMEOUT", "")
        cls.HTTP_READ_TIMEOUT = float(http_read_timeout_str) if http_read_timeout_str else cls.HTTP_READ_TIMEOUT
        http_write_timeout_str = WorkflowManager.get_app_config("HTTP_WRITE_TIMEOUT", "")
        cls.HTTP_WRITE_TIMEOUT = float(http_write_timeout_str) if http_write_timeout_str else cls.HTTP_WRITE_TIMEOUT
        http_connect_timeout_str = WorkflowManager.get_app_config("HTTP_CONNECT_TIMEOUT", "")
        cls.HTTP_CONNECT_TIMEOUT = float(http_connect_timeout_str) if http_connect_timeout_str else cls.HTTP_CONNECT_TIMEOUT
    
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
            raise ValueError(
                f"项目 '{project}' 未配置 group_ids。"
                f"请修改 config/options.json 后运行 python3 scripts/init_db.py 更新数据库配置"
            )
        
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
        from workflows.models import WorkflowManager
        if not WorkflowManager.get_app_config("BOT_TOKEN", ""):
            raise ValueError("缺少必要的配置项: BOT_TOKEN，请先运行 python3 scripts/init_db.py 初始化数据库")
        
        # 检查数据库中是否有项目配置了 group_ids
        options = cls.load_options()
        projects = options.get("projects", {})
        if not projects:
            raise ValueError(
                "缺少项目配置。请修改 config/options.json 后运行 python3 scripts/init_db.py 更新数据库配置"
            )
        
        # 检查每个项目是否配置了 group_ids
        missing_group_ids = []
        for project_name, project_data in projects.items():
            group_ids = project_data.get("group_ids", [])
            if not group_ids:
                missing_group_ids.append(project_name)
        
        if missing_group_ids:
            raise ValueError(
                f"以下项目未配置 group_ids: {', '.join(missing_group_ids)}。"
                f"请修改 config/options.json 后运行 python3 scripts/init_db.py 更新数据库配置"
            )
        
        return True
    
    @classmethod
    def is_api_enabled(cls) -> bool:
        """检查是否启用了外部API同步"""
        return bool(cls.API_BASE_URL)
