"""Jenkins API 客户端模块"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional
import jenkins
from jenkins_ops.config import JenkinsConfig
from utils.proxy import get_proxy_config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsBuildLimiter:
    """控制 Jenkins 并发触发数量的轻量级限流器"""

    _semaphores: Dict[str, asyncio.Semaphore] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def _get_semaphore(cls, project_name: str, max_concurrent: int) -> asyncio.Semaphore:
        """按项目获取/创建信号量"""
        async with cls._lock:
            sem = cls._semaphores.get(project_name)
            if sem is None:
                # 防御：最少允许 1 并发，避免 0 或负值导致死锁
                capacity = max(1, max_concurrent)
                sem = asyncio.Semaphore(capacity)
                cls._semaphores[project_name] = sem
                logger.info(f"为项目 {project_name} 初始化 Jenkins 并发上限: {capacity}")
            return sem

    @classmethod
    @asynccontextmanager
    async def reserve(cls, project_name: str, max_concurrent: int):
        """
        以 async context 方式申请一个构建槽位

        Args:
            project_name: 项目名，用于区分不同项目的限流
            max_concurrent: 该项目允许的最大并发触发数
        """
        sem = await cls._get_semaphore(project_name, max_concurrent)
        logger.debug(f"Jenkins 构建并发控制等待中: {project_name} (上限 {max_concurrent})")
        await sem.acquire()
        try:
            yield
        finally:
            sem.release()


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
        
        url = self.config.get_url(project_name)
        username, token = self.config.get_auth(project_name)
        proxies = get_proxy_config(project_name)
        
        # 创建 Jenkins 服务器连接
        self.server = jenkins.Jenkins(
            url=url,
            username=username,
            password=token,
            timeout=30
        )
        
        # 配置代理（如果有）
        if proxies:
            try:
                # python-jenkins 库内部使用 requests.Session，通过 _session 配置代理
                if hasattr(self.server, '_session') and self.server._session:
                    self.server._session.proxies.update(proxies)
                    logger.debug(f"Jenkins 客户端已配置代理: {proxies}")
                else:
                    # 如果无法直接访问 _session，通过环境变量配置代理
                    if 'http' in proxies:
                        os.environ['HTTP_PROXY'] = proxies['http']
                        os.environ['http_proxy'] = proxies['http']
                    if 'https' in proxies:
                        os.environ['HTTPS_PROXY'] = proxies['https']
                        os.environ['https_proxy'] = proxies['https']
                    logger.debug(f"通过环境变量配置代理: {proxies}")
            except Exception as e:
                logger.warning(f"配置 Jenkins 代理失败: {e}，将尝试不使用代理")
    
    def trigger_build(
        self,
        job_name: str,
        parameters: Optional[Dict] = None
    ) -> Dict:
        """
        触发 Jenkins Job 构建
        
        使用 python-jenkins 库
        
        Args:
            job_name: Jenkins Job 名称（例如：'my-project/master' 或 'folder/job-name'）
            parameters: 构建参数（可选，如果提供则使用 buildWithParameters）
        
        Returns:
            构建信息字典，包含 queue_id, build_number 等
        """
        try:
            job_info = self.server.get_job_info(job_name)
            next_build_number = job_info["nextBuildNumber"]
            queue_id = self.server.build_job(job_name, parameters or {})
            logger.info(f"🍺 Jenkins 构建已触发: {job_name}, queue_id={queue_id}, next={next_build_number}")
            return {
                "queue_id": queue_id,
                "job_name": job_name,
                "next_build_number": next_build_number,
                "parameters": parameters or {},
            }
        except Exception as e:
            logger.error(f"❌ 触发 Jenkins 构建失败: {e}")
            raise
    
    def get_build_info(
        self,
        job_name: str,
        build_number: int
    ) -> Optional[Dict]:
        """
        获取构建信息
        
        使用 python-jenkins 库
        
        Args:
            job_name: Jenkins Job 名称（例如：'uat/pre-blockchain-external-wallet-service'）
            build_number: 构建编号
        
        Returns:
            构建信息字典，包含状态、时长、URL 等
        """
        try:
            build_info = self.server.get_build_info(job_name, build_number)
            if build_info:
                # 记录查询信息（用于调试）
                build_url = build_info.get('url', '')
                is_building = build_info.get('building', False)
                status = build_info.get('result', 'BUILDING' if is_building else 'UNKNOWN')
                logger.debug(f"查询构建状态 - Job: {job_name}, Build: #{build_number}, 状态: {status}, URL: {build_url}")
            return build_info
        except Exception as e:
            logger.error(f"❌ 获取构建信息失败 - Job: {job_name}, Build: #{build_number}, 错误: {e}")
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
        start = time.time()
        while time.time() - start < timeout:
            try:
                queue_item = self.server.get_queue_item(queue_id)
                if "executable" in queue_item and queue_item["executable"]:
                    build_number = queue_item["executable"]["number"]
                    logger.info(f"🚀 构建正式开始: {job_name} #{build_number}")
                    return build_number
            except Exception:
                pass
            time.sleep(2)
        logger.warning(f"⏳ 等待构建开始超时: {job_name}, queue_id={queue_id}")
        return None
