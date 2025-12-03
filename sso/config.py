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
        return Settings.get_sso_enabled()
    
    @classmethod
    def get_url(cls) -> str:
        """获取 SSO 系统 URL"""
        return Settings.get_sso_url()
    
    @classmethod
    def get_auth_token(cls) -> str:
        """获取 SSO Auth Token"""
        return Settings.get_sso_auth_token()
    
    @classmethod
    def get_authorization(cls) -> str:
        """获取 SSO Authorization"""
        return Settings.get_sso_authorization()
    
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
