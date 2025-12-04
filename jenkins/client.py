"""Jenkins API 客户端模块"""
import os
import time
import requests
import jenkins
from typing import Dict, Optional
from requests.auth import HTTPBasicAuth
from jenkins.config import JenkinsConfig
from utils.proxy import get_proxy_config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsClient:
    """Jenkins API 客户端"""
    
    def __init__(self, project_name: str):
        """
        初始化 Jenkins 客户端
        
        Args:
            project_name: 项目名称，用于获取该项目的 Jenkins 配置
        """
        self.project_name = project_name
        self.config = JenkinsConfig
        if not self.config.validate(project_name):
            logger.warning(f"项目 {project_name} 的 Jenkins 配置验证失败，请检查配置")
        
        # 初始化代理配置（使用项目配置的代理）
        self.proxies = get_proxy_config(project_name)
        
        # 初始化 Jenkins 服务器连接
        self._init_jenkins_server()
    
    def _init_jenkins_server(self):
        """初始化 Jenkins 服务器连接"""
        url = self.config.get_url(self.project_name)
        username, token = self.config.get_auth(self.project_name)
        
        # 如果配置了用户名，使用用户名+Token；否则只使用Token
        auth_username = username if username else token
        auth_token = token
        
        # 创建 Jenkins 服务器连接
        self.server = jenkins.Jenkins(
            url,
            username=auth_username,
            password=auth_token
        )
        
        # 如果配置了代理，需要为 python-jenkins 的底层 requests 会话配置代理
        if self.proxies:
            try:
                # python-jenkins 库内部使用 requests，我们需要配置其会话的代理
                # 访问 Jenkins 实例的 _session 属性（内部使用的 requests.Session）
                if hasattr(self.server, '_session') and self.server._session:
                    self.server._session.proxies.update(self.proxies)
                    logger.debug(f"Jenkins 客户端已配置代理: {self.proxies}")
                else:
                    # 如果无法直接访问 _session，通过设置环境变量来配置代理
                    if 'http' in self.proxies:
                        os.environ['HTTP_PROXY'] = self.proxies['http']
                        os.environ['http_proxy'] = self.proxies['http']
                    if 'https' in self.proxies:
                        os.environ['HTTPS_PROXY'] = self.proxies['https']
                        os.environ['https_proxy'] = self.proxies['https']
                    logger.debug(f"通过环境变量配置代理: {self.proxies}")
            except Exception as e:
                logger.warning(f"配置 Jenkins 代理失败: {e}，将尝试不使用代理")
    
    def _get_auth(self) -> Optional[HTTPBasicAuth]:
        """获取认证信息"""
        username, token = self.config.get_auth(self.project_name)
        if token:
            # 如果配置了用户名，使用用户名+Token；否则只使用Token（Jenkins支持）
            auth_username = username if username else token
            return HTTPBasicAuth(auth_username, token)
        return None
    
    def _build_url(self, path: str) -> str:
        """构建完整的 Jenkins API URL"""
        base_url = self.config.get_url(self.project_name).rstrip('/')
        path = path.lstrip('/')
        return f"{base_url}/{path}"
    
    def trigger_build(
        self,
        job_name: str,
        parameters: Optional[Dict] = None
    ) -> Dict:
        """
        触发 Jenkins Job 构建
        
        使用 python-jenkins 库的 build_job 方法来触发构建
        
        Args:
            job_name: Jenkins Job 名称（例如：'my-project/master' 或 'folder/job-name'）
            parameters: 构建参数（可选，如果提供则使用 buildWithParameters）
        
        Returns:
            构建信息字典，包含 queue_id, build_number 等
        """
        try:
            # 获取下一个构建号（在触发构建之前）
            job_info = self.server.get_job_info(job_name)
            next_build_number = job_info.get('nextBuildNumber', 0)
            
            # 触发构建（带参数或不带参数）
            if parameters:
                # 使用带参数的构建
                self.server.build_job(job_name, parameters=parameters)
                logger.info(f'✅ Jenkins Job {job_name} 触发成功，下一个构建号: {next_build_number}, 参数: {parameters}')
            else:
                # 不带参数的构建
                self.server.build_job(job_name)
                logger.info(f'✅ Jenkins Job {job_name} 触发成功，下一个构建号: {next_build_number}')
            
            # python-jenkins 的 build_job 方法不直接返回 queue_id
            # 这里返回 next_build_number，可以通过后续查询获取实际构建信息
            return {
                'queue_id': None,  # python-jenkins 不直接返回 queue_id
                'job_name': job_name,
                'next_build_number': next_build_number,
                'job_url': self._build_url(f"job/{job_name}"),
                'parameters': parameters or {}
            }
            
        except jenkins.JenkinsException as e:
            logger.error(f'❌ 触发Jenkins Job失败: {e}')
            raise
    
    def get_build_info(
        self,
        job_name: str,
        build_number: int
    ) -> Optional[Dict]:
        """
        获取构建信息
        
        使用 python-jenkins 库的 get_build_info 方法
        
        Args:
            job_name: Jenkins Job 名称
            build_number: 构建编号
        
        Returns:
            构建信息字典，包含状态、时长、URL 等
        """
        try:
            build_info = self.server.get_build_info(job_name, build_number)
            
            # 提取关键信息，保持与原接口兼容
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
            
        except jenkins.JenkinsException as e:
            logger.error(f"获取构建信息失败 - Job: {job_name}, Build: {build_number}, 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"获取构建信息时发生未知错误 - Job: {job_name}, Build: {build_number}, 错误: {e}")
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
        start: int = 0  # 保留参数以保持向后兼容，但 python-jenkins 不支持此参数
    ) -> Optional[str]:
        """
        获取构建控制台输出（可选，用于调试）
        
        使用 python-jenkins 库的 get_build_console_output 方法
        
        Args:
            job_name: Jenkins Job 名称
            build_number: 构建编号
            start: 起始行号（保留参数以保持向后兼容，但当前实现不支持）
        
        Returns:
            控制台输出文本，如果失败返回 None
        """
        try:
            console_output = self.server.get_build_console_output(job_name, build_number)
            return console_output
        except jenkins.JenkinsException as e:
            logger.error(f"获取构建控制台输出失败 - Job: {job_name}, Build: {build_number}, 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"获取构建控制台输出时发生未知错误 - Job: {job_name}, Build: {build_number}, 错误: {e}")
            return None
    
    def wait_for_build_to_start(
        self,
        job_name: str,
        queue_id: Optional[int] = None,
        next_build_number: Optional[int] = None,
        timeout: int = 60
    ) -> Optional[int]:
        """
        等待构建开始并返回构建编号
        
        Args:
            job_name: Jenkins Job 名称
            queue_id: 队列 ID（可选，如果有则优先使用队列 API）
            next_build_number: 预期的下一个构建号（可选，如果没有 queue_id 则使用此方式轮询）
            timeout: 超时时间（秒，默认60秒）
        
        Returns:
            构建编号，如果超时返回 None
        """
        start_time = time.time()
        poll_interval = 2  # 每2秒轮询一次
        
        # 优先使用 queue_id 方式（更准确）
        if queue_id:
            while time.time() - start_time < timeout:
                try:
                    # 使用队列信息查询方法（复用已配置的代理）
                    queue_info = self.get_queue_info(queue_id)
                    if not queue_info:
                        time.sleep(poll_interval)
                        continue
                    
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
                    
                except Exception as e:
                    logger.warning(f"查询队列状态失败 - Queue ID: {queue_id}, 错误: {e}")
                    time.sleep(poll_interval)
            
            logger.warning(f"⚠️ 等待构建开始超时 - Job: {job_name}, Queue ID: {queue_id}, 超时: {timeout}秒")
            return None
        
        # 如果没有 queue_id，使用 next_build_number 轮询方式
        elif next_build_number:
            while time.time() - start_time < timeout:
                try:
                    # 尝试获取构建信息
                    build_info = self.get_build_info(job_name, next_build_number)
                    if build_info:
                        logger.info(f"✅ 构建已开始 - Job: {job_name}, Build: {next_build_number}")
                        return next_build_number
                    
                    # 等待下一次轮询
                    time.sleep(poll_interval)
                    
                except Exception as e:
                    # 构建可能还未开始，继续等待
                    time.sleep(poll_interval)
            
            logger.warning(f"⚠️ 等待构建开始超时 - Job: {job_name}, 构建号: {next_build_number}, 超时: {timeout}秒")
            return None
        
        else:
            logger.error(f"⚠️ 无法等待构建开始：既没有 queue_id 也没有 next_build_number")
            return None
    
    def get_queue_info(self, queue_id: int) -> Optional[Dict]:
        """
        获取队列信息
        
        使用已配置的 server._session，自动复用代理配置
        
        Args:
            queue_id: 队列 ID
        
        Returns:
            队列信息字典，如果失败返回 None
        """
        url = self._build_url(f"queue/item/{queue_id}/api/json")
        
        try:
            # 复用 self.server 的 session，自动使用已配置的代理和认证
            session = getattr(self.server, '_session', None)
            if session:
                # 使用已配置的 session（已包含代理和认证）
                response = session.get(url, timeout=10)
            else:
                # 回退到手动配置（这种情况应该很少发生）
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

