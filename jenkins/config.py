"""Jenkins 配置管理模块"""
from typing import Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsConfig:
    """Jenkins 系统配置类（从项目配置中读取，按项目区分）"""
    
    @classmethod
    def _get_project_config(cls, project_name: str) -> dict:
        """获取项目配置"""
        from workflows.models import WorkflowManager
        options = WorkflowManager.get_project_options()
        projects = options.get('projects', {})
        project_config = projects.get(project_name, {})
        return project_config.get('jenkins', {})
    
    @classmethod
    def is_enabled(cls, project_name: str) -> bool:
        """
        检查指定项目的 Jenkins 集成是否启用
        
        Args:
            project_name: 项目名称
        
        Returns:
            如果启用返回 True，否则返回 False
        """
        jenkins_config = cls._get_project_config(project_name)
        return jenkins_config.get('enabled', False)
    
    @classmethod
    def get_url(cls, project_name: str) -> str:
        """
        获取指定项目的 Jenkins 服务器 URL
        
        Args:
            project_name: 项目名称
        
        Returns:
            Jenkins 服务器 URL
        """
        jenkins_config = cls._get_project_config(project_name)
        return jenkins_config.get('url', '')
    
    @classmethod
    def get_username(cls, project_name: str) -> str:
        """
        获取指定项目的 Jenkins 用户名
        
        Args:
            project_name: 项目名称
        
        Returns:
            Jenkins 用户名
        """
        jenkins_config = cls._get_project_config(project_name)
        return jenkins_config.get('username', '')
    
    @classmethod
    def get_api_token(cls, project_name: str) -> str:
        """
        获取指定项目的 Jenkins API Token
        
        Args:
            project_name: 项目名称
        
        Returns:
            Jenkins API Token
        """
        jenkins_config = cls._get_project_config(project_name)
        return jenkins_config.get('api_token', '')
    
    @classmethod
    def get_auth(cls, project_name: str) -> Tuple[str, str]:
        """
        获取指定项目的认证信息 (username, token)
        
        Args:
            project_name: 项目名称
        
        Returns:
            (username, token) 元组，如果使用 Token 认证，username 可能为空
        """
        username = cls.get_username(project_name)
        token = cls.get_api_token(project_name)
        return (username, token)
    
    @classmethod
    def validate(cls, project_name: str) -> bool:
        """
        验证指定项目的 Jenkins 配置是否完整
        
        Args:
            project_name: 项目名称
        
        Returns:
            如果配置完整返回 True，否则返回 False
        """
        if not cls.is_enabled(project_name):
            logger.debug(f"项目 {project_name} 的 Jenkins 集成未启用")
            return False
        
        url = cls.get_url(project_name)
        token = cls.get_api_token(project_name)
        
        if not url:
            logger.error(f"项目 {project_name} 的 JENKINS_URL 未配置")
            return False
        
        if not token:
            logger.error(f"项目 {project_name} 的 JENKINS_API_TOKEN 未配置")
            return False
        
        logger.debug(f"项目 {project_name} 的 Jenkins 配置验证通过")
        return True

