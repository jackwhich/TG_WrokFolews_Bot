"""SSO 配置管理模块"""
from typing import Optional
from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSOConfig:
    """SSO 系统配置类（从 Settings 读取配置）"""
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用 SSO 集成"""
        from workflows.models import WorkflowManager
        value = WorkflowManager.get_app_config("SSO_ENABLED", "")
        return value.lower() == "true" if value else False
    
    @classmethod
    def get_url(cls) -> str:
        """获取 SSO 系统 URL"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("SSO_URL", "")
    
    @classmethod
    def get_auth_token(cls) -> str:
        """获取 SSO Auth Token"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("SSO_AUTH_TOKEN", "")
    
    @classmethod
    def get_authorization(cls) -> str:
        """获取 SSO Authorization"""
        from workflows.models import WorkflowManager
        return WorkflowManager.get_app_config("SSO_AUTHORIZATION", "")
    
    @classmethod
    def get_headers(cls) -> dict:
        """获取 SSO API 请求头"""
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "Auth-token": cls.get_auth_token(),
            "Authorization": cls.get_authorization()
        }
    
    @classmethod
    def validate(cls) -> bool:
        """验证 SSO 配置是否完整"""
        if not cls.is_enabled():
            logger.debug("SSO 集成未启用")
            return False
        
        url = cls.get_url()
        auth_token = cls.get_auth_token()
        authorization = cls.get_authorization()
        
        if not url:
            logger.error("SSO_URL 未配置")
            return False
        
        if not auth_token:
            logger.error("SSO_AUTH_TOKEN 未配置")
            return False
        
        if not authorization:
            logger.error("SSO_AUTHORIZATION 未配置")
            return False
        
        logger.debug("SSO 配置验证通过")
        return True
