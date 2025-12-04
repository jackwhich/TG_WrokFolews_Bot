"""Jenkins API 客户端模块"""
import os
import re
import time
from typing import Dict, Optional
import jenkins
from jenkins_ops.config import JenkinsConfig
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
        
        url = self.config.get_url(project_name)
        username, token = self.config.get_auth(project_name)
        proxies = get_proxy_config(project_name)
        self.server = jenkins.Jenkins(
            url=url,
            username=username,
            password=token,
            timeout=30,
            proxies=proxies
        )
    
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
            job_name: Jenkins Job 名称
            build_number: 构建编号
        
        Returns:
            构建信息字典，包含状态、时长、URL 等
        """
        try:
            return self.server.get_build_info(job_name, build_number)
        except Exception as e:
            logger.error(f"获取构建信息失败: {e}")
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
        
        return build_info.get('result') or 'BUILDING'
    
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
            return self.server.get_build_console_output(job_name, build_number)
        except Exception as e:
            logger.error(f"获取控制台输出失败: {e}")
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
