"""API客户端"""
import requests
from typing import Dict, Optional, Tuple
from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class APIClient:
    """HTTP API客户端"""
    
    def __init__(self):
        self.base_url = Settings.API_BASE_URL.rstrip('/')
        self.endpoint = Settings.API_ENDPOINT.lstrip('/')
        self.timeout = Settings.API_TIMEOUT
        self.token = Settings.API_TOKEN
        # 如果启用了代理，配置代理
        self.proxies = None
        if Settings.PROXY_ENABLED:
            proxy_url = Settings.get_proxy_url()
            if proxy_url:
                self.proxies = {
                    "http": proxy_url,
                    "https": proxy_url
                }
                logger.info(f"✅ API客户端已配置代理: {Settings.PROXY_HOST}:{Settings.PROXY_PORT}")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def sync_workflow(self, workflow_data: dict) -> Tuple[bool, Optional[str]]:
        """
        同步工作流到外部API
        
        Args:
            workflow_data: 工作流数据
            
        Returns:
            (是否成功, 错误信息)
        """
        url = f"{self.base_url}/{self.endpoint}"
        
        # 准备请求数据
        payload = {
            "workflow_id": workflow_data.get("workflow_id"),
            "user_id": workflow_data.get("user_id"),
            "username": workflow_data.get("username"),
            "submission_data": workflow_data.get("submission_data"),
            "status": workflow_data.get("status"),
            "approver_id": workflow_data.get("approver_id"),
            "approval_time": workflow_data.get("approval_time"),
            "approval_comment": workflow_data.get("approval_comment"),
        }
        
        workflow_id = workflow_data.get('workflow_id', 'N/A')
        try:
            logger.info(f"开始同步工作流 {workflow_id} 到外部API - URL: {url}")
            logger.debug(f"请求数据: {payload}")
            
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout,
                proxies=self.proxies,  # 如果启用了代理，使用代理
            )
            
            logger.debug(f"API响应状态码: {response.status_code}")
            response.raise_for_status()
            
            logger.info(f"✅ 工作流 {workflow_id} 同步到API成功 - 状态码: {response.status_code}")
            return True, None
            
        except requests.exceptions.Timeout as e:
            error_msg = f"API请求超时: {str(e)}"
            logger.error(f"❌ 工作流 {workflow_id} API同步超时: {error_msg}")
            return False, error_msg
        except requests.exceptions.HTTPError as e:
            error_msg = f"API HTTP错误: {str(e)}, 状态码: {e.response.status_code if e.response else 'N/A'}"
            logger.error(f"❌ 工作流 {workflow_id} API同步HTTP错误: {error_msg}")
            if e.response:
                logger.debug(f"响应内容: {e.response.text}")
            return False, error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求异常: {str(e)}"
            logger.error(f"❌ 工作流 {workflow_id} API同步失败: {error_msg}", exc_info=True)
            return False, error_msg

