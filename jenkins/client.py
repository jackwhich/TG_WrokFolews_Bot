"""Jenkins API 客户端模块"""
import time
import requests
from typing import Dict, Optional
from requests.auth import HTTPBasicAuth
from jenkins.config import JenkinsConfig
from utils.proxy import get_proxy_config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsClient:
    """Jenkins API 客户端"""
    
    def __init__(self):
        """初始化 Jenkins 客户端"""
        self.config = JenkinsConfig
        if not self.config.validate():
            logger.warning("Jenkins 配置验证失败，请检查配置")
        
        # 初始化代理配置（使用全局代理配置）
        self.proxies = get_proxy_config()
    
    def _get_auth(self) -> Optional[HTTPBasicAuth]:
        """获取认证信息"""
        username, token = self.config.get_auth()
        if token:
            # 如果配置了用户名，使用用户名+Token；否则只使用Token（Jenkins支持）
            auth_username = username if username else token
            return HTTPBasicAuth(auth_username, token)
        return None
    
    def _build_url(self, path: str) -> str:
        """构建完整的 Jenkins API URL"""
        base_url = self.config.get_url().rstrip('/')
        path = path.lstrip('/')
        return f"{base_url}/{path}"
    
    def trigger_build(
        self,
        job_name: str,
        parameters: Optional[Dict] = None
    ) -> Dict:
        """
        触发 Jenkins Job 构建
        
        Args:
            job_name: Jenkins Job 名称（例如：'my-project/master' 或 'folder/job-name'）
            parameters: 构建参数（可选，如果提供则使用 buildWithParameters）
        
        Returns:
            构建信息字典，包含 queue_id, build_number 等
        """
        # 转义 Job 名称（Jenkins API 需要 URL 编码）
        from urllib.parse import quote
        encoded_job_name = '/'.join(quote(part, safe='') for part in job_name.split('/'))
        
        if parameters:
            # 使用 buildWithParameters 端点
            url = self._build_url(f"job/{encoded_job_name}/buildWithParameters")
            response = requests.post(
                url,
                auth=self._get_auth(),
                params=parameters,
                proxies=self.proxies,
                timeout=30
            )
        else:
            # 使用 build 端点
            url = self._build_url(f"job/{encoded_job_name}/build")
            response = requests.post(
                url,
                auth=self._get_auth(),
                proxies=self.proxies,
                timeout=30
            )
        
        response.raise_for_status()
        
        # 从响应头获取队列 ID
        queue_id = None
        location = response.headers.get('Location', '')
        if location:
            # Location 格式: /queue/item/12345/
            import re
            match = re.search(r'/queue/item/(\d+)/', location)
            if match:
                queue_id = int(match.group(1))
        
        logger.info(f"✅ Jenkins 构建已触发 - Job: {job_name}, Queue ID: {queue_id}")
        
        return {
            'queue_id': queue_id,
            'job_name': job_name,
            'job_url': self._build_url(f"job/{encoded_job_name}"),
            'parameters': parameters or {}
        }
    
    def get_build_info(
        self,
        job_name: str,
        build_number: int
    ) -> Optional[Dict]:
        """
        获取构建信息
        
        Args:
            job_name: Jenkins Job 名称
            build_number: 构建编号
        
        Returns:
            构建信息字典，包含状态、时长、URL 等
        """
        from urllib.parse import quote
        encoded_job_name = '/'.join(quote(part, safe='') for part in job_name.split('/'))
        
        url = self._build_url(f"job/{encoded_job_name}/{build_number}/api/json")
        
        try:
            response = requests.get(
                url,
                auth=self._get_auth(),
                proxies=self.proxies,
                timeout=30
            )
            response.raise_for_status()
            
            build_info = response.json()
            
            # 提取关键信息
            result = {
                'build_number': build_number,
                'job_name': job_name,
                'status': build_info.get('result', 'BUILDING'),  # SUCCESS, FAILURE, ABORTED, UNSTABLE, None(BUILDING)
                'building': build_info.get('building', False),
                'duration': build_info.get('duration', 0),  # 毫秒
                'timestamp': build_info.get('timestamp', 0),  # 毫秒
                'url': build_info.get('url', ''),
                'fullDisplayName': build_info.get('fullDisplayName', ''),
                'description': build_info.get('description', '')
            }
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取构建信息失败 - Job: {job_name}, Build: {build_number}, 错误: {e}")
            return None
    
    def get_build_status(
        self,
        job_name: str,
        build_number: int
    ) -> Optional[str]:
        """
        获取构建状态
        
        Args:
            job_name: Jenkins Job 名称
            build_number: 构建编号
        
        Returns:
            构建状态（SUCCESS/FAILURE/BUILDING/ABORTED/UNSTABLE），如果失败返回 None
        """
        build_info = self.get_build_info(job_name, build_number)
        if not build_info:
            return None
        
        if build_info.get('building', False):
            return 'BUILDING'
        
        return build_info.get('status') or 'BUILDING'
    
    def get_build_console_output(
        self,
        job_name: str,
        build_number: int,
        start: int = 0
    ) -> Optional[str]:
        """
        获取构建控制台输出（可选，用于调试）
        
        Args:
            job_name: Jenkins Job 名称
            build_number: 构建编号
            start: 起始行号（默认0，从头开始）
        
        Returns:
            控制台输出文本，如果失败返回 None
        """
        from urllib.parse import quote
        encoded_job_name = '/'.join(quote(part, safe='') for part in job_name.split('/'))
        
        url = self._build_url(f"job/{encoded_job_name}/{build_number}/consoleText")
        if start > 0:
            url += f"?start={start}"
        
        try:
            response = requests.get(
                url,
                auth=self._get_auth(),
                proxies=self.proxies,
                timeout=30
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"获取构建控制台输出失败 - Job: {job_name}, Build: {build_number}, 错误: {e}")
            return None
    
    def wait_for_build_to_start(
        self,
        job_name: str,
        queue_id: int,
        timeout: int = 60
    ) -> Optional[int]:
        """
        等待构建开始并返回构建编号
        
        Args:
            job_name: Jenkins Job 名称
            queue_id: 队列 ID（从 trigger_build 返回）
            timeout: 超时时间（秒，默认60秒）
        
        Returns:
            构建编号，如果超时返回 None
        """
        from urllib.parse import quote
        encoded_job_name = '/'.join(quote(part, safe='') for part in job_name.split('/'))
        
        start_time = time.time()
        poll_interval = 2  # 每2秒轮询一次
        
        while time.time() - start_time < timeout:
            try:
                # 查询队列状态
                url = self._build_url(f"queue/item/{queue_id}/api/json")
                response = requests.get(
                    url,
                    auth=self._get_auth(),
                    proxies=self.proxies,
                    timeout=10
                )
                response.raise_for_status()
                
                queue_info = response.json()
                
                # 检查是否已开始构建
                if queue_info.get('executable'):
                    build_number = queue_info['executable'].get('number')
                    if build_number:
                        logger.info(f"✅ 构建已开始 - Job: {job_name}, Build: {build_number}")
                        return build_number
                
                # 检查是否被取消
                if queue_info.get('cancelled', False):
                    logger.warning(f"⚠️ 构建队列项已被取消 - Job: {job_name}, Queue ID: {queue_id}")
                    return None
                
                # 等待下一次轮询
                time.sleep(poll_interval)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"查询队列状态失败 - Queue ID: {queue_id}, 错误: {e}")
                time.sleep(poll_interval)
        
        logger.warning(f"⚠️ 等待构建开始超时 - Job: {job_name}, Queue ID: {queue_id}, 超时: {timeout}秒")
        return None
    
    def get_queue_info(self, queue_id: int) -> Optional[Dict]:
        """
        获取队列信息
        
        Args:
            queue_id: 队列 ID
        
        Returns:
            队列信息字典，如果失败返回 None
        """
        url = self._build_url(f"queue/item/{queue_id}/api/json")
        
        try:
            response = requests.get(
                url,
                auth=self._get_auth(),
                proxies=self.proxies,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取队列信息失败 - Queue ID: {queue_id}, 错误: {e}")
            return None

