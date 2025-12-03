"""Jenkins 配置管理模块"""
from typing import Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsConfig:
    """Jenkins 系统配置类（从数据库读取配置）"""
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用 Jenkins 集成"""
        from workflows.models import WorkflowManager
        value = WorkflowManager.get_app_config("JENKINS_ENABLED", "")
        return value.lower() == "true" if value else False
    
    @classmethod
    def get_url(cls) -> str:
        """获取 Jenkins 服务器 URL"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("JENKINS_URL", "")
    
    @classmethod
    def get_username(cls) -> str:
        """获取 Jenkins 用户名"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("JENKINS_USERNAME", "")
    
    @classmethod
    def get_api_token(cls) -> str:
        """获取 Jenkins API Token"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("JENKINS_API_TOKEN", "")
    
    @classmethod
    def get_auth(cls) -> Tuple[str, str]:
        """
        获取认证信息 (username, token)
        
        Returns:
            (username, token) 元组，如果使用 Token 认证，username 可能为空
        """
        username = cls.get_username()
        token = cls.get_api_token()
        return (username, token)
    
    @classmethod
    def validate(cls) -> bool:
        """验证 Jenkins 配置是否完整"""
        if not cls.is_enabled():
            logger.debug("Jenkins 集成未启用")
            return False
        
        url = cls.get_url()
        token = cls.get_api_token()
        
        if not url:
            logger.error("JENKINS_URL 未配置")
            return False
        
        if not token:
            logger.error("JENKINS_API_TOKEN 未配置")
            return False
        
        logger.debug("Jenkins 配置验证通过")
        return True

