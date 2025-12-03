"""SSO API 客户端模块"""
import json
import requests
from typing import List, Dict, Optional, Union
from sso.config import SSOConfig
from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSOClient:
    """SSO API 客户端"""
    
    def __init__(self):
        """初始化 SSO 客户端"""
        self.config = SSOConfig
        if not self.config.validate():
            logger.warning("SSO 配置验证失败，请检查配置")
        
        # 初始化代理配置（使用与 TG bot 相同的代理配置）
        from utils.proxy import get_proxy_config
        self.proxies = get_proxy_config()
    
    def get_job_ids(
        self,
        server_names: Union[str, List[str]],
        project_name: str,
        env: str
    ) -> List[str]:
        """
        根据服务名、项目、环境获取 Jenkins Job ID
        
        Args:
            server_names: 服务名（字符串或列表）
            project_name: 项目名称
            env: 环境（如 "UAT" 或 "GRAY-UAT"）
            
        Returns:
            Job ID 列表
        """
        url = f"{self.config.get_url()}/api/publish3/publish/jenkinsJob/queryOaSameJob"
        params = {
            "env": env,
            "projects": project_name
        }
        
        headers = self.config.get_headers()
        
        try:
            logger.info(f"请求 Job ID - 项目: {project_name}, 环境: {env}, 服务: {server_names}")
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                proxies=self.proxies,
                timeout=30
            )
            response.raise_for_status()
            
            js = response.json()
            job_data = js.get('data', [])
            
            if isinstance(server_names, str):
                # 单个服务名
                job_ids = [
                    item['jobId'] for item in job_data
                    if server_names in item.get('jobName', '')
                ]
            else:
                # 多个服务名
                job_ids_all = []
                for server_name in server_names:
                    for item in job_data:
                        if server_name in item.get('jobName', ''):
                            job_ids_all.append(item['jobId'])
                            break
                job_ids = job_ids_all
            
            logger.info(f"获取到 Job IDs: {job_ids}")
            return job_ids
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取 Job ID 失败 - 项目: {project_name}, 环境: {env}, 错误: {e}")
            raise
    
    def submit_order(self, order_data: Dict) -> Dict:
        """
        提交发布工单到 SSO 系统
        
        Args:
            order_data: SSO 工单数据
            
        Returns:
            SSO 提交响应
        """
        url = f"{self.config.get_url()}/api/flow/task/startnew/dcAutoReleaseProcess"
        headers = self.config.get_headers()
        
        # SSO 要求 detail 字段必须是 JSON 字符串
        order_data_copy = order_data.copy()
        if 'detail' in order_data_copy and isinstance(order_data_copy['detail'], list):
            order_data_copy['detail'] = json.dumps(order_data_copy['detail'], ensure_ascii=False)
        
        try:
            logger.info(f"提交 SSO 工单 - 项目: {order_data.get('title', 'N/A')}")
            response = requests.post(
                url, 
                headers=headers, 
                json=order_data_copy, 
                proxies=self.proxies,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"SSO 工单提交成功 - 响应: {result}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"提交 SSO 工单失败: {e}")
            raise
    
    def get_release_ids(self, process_instance_id: str) -> List[int]:
        """
        获取发布 ID 列表
        
        Args:
            process_instance_id: SSO 工单ID (processInstanceId)
            
        Returns:
            发布 ID 列表
        """
        url = f"{self.config.get_url()}/api/flow/publish/hisitory/getReleaseId"
        params = {
            "proId": process_instance_id
        }
        headers = self.config.get_headers()
        
        try:
            logger.info(f"获取发布 ID - 工单ID: {process_instance_id}")
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                proxies=self.proxies,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            release_ids = result.get('object', [])
            
            if release_ids:
                release_ids = [int(rid) for rid in release_ids if rid]
                logger.info(f"获取到发布 ID: {release_ids}")
            else:
                logger.warning(f"未获取到发布 ID - 工单ID: {process_instance_id}")
                release_ids = []
            
            return release_ids
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取发布 ID 失败 - 工单ID: {process_instance_id}, 错误: {e}")
            raise
    
    def get_build_detail(self, release_id: int) -> Optional[Dict]:
        """
        查询构建详情
        
        Args:
            release_id: 发布 ID
            
        Returns:
            构建状态详情，如果失败返回 None
        """
        url = f"{self.config.get_url()}/api/flow/publish/hisitory/buildDetail"
        params = {
            "id": release_id
        }
        headers = self.config.get_headers()
        
        try:
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                proxies=self.proxies,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            build_data = result.get('data', {})
            
            return build_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"查询构建详情失败 - 发布ID: {release_id}, 错误: {e}")
            return None

