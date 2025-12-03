"""SSO 构建状态监控模块"""
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from sso.client import SSOClient
from workflows.models import WorkflowManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSOMonitor:
    """SSO 构建状态监控器"""
    
    def __init__(self):
        """初始化监控器"""
        self.client = SSOClient()
    
    async def monitor_build_status(
        self,
        release_ids: List[int],
        workflow_id: str,
        submission_id: str,
        max_poll_count: int = 20,
        poll_interval: int = 30
    ):
        """
        监控构建状态（异步）
        
        Args:
            release_ids: 发布 ID 列表
            workflow_id: 工作流ID
            submission_id: SSO 提交ID
            max_poll_count: 最大轮询次数（默认20次）
            poll_interval: 轮询间隔（秒，默认30秒）
        """
        logger.info(f"开始监控构建状态 - 工作流ID: {workflow_id}, 发布ID数: {len(release_ids)}")
        
        # 为每个发布 ID 创建监控任务
        tasks = []
        for release_id in release_ids:
            task = asyncio.create_task(
                self._monitor_single_build(
                    release_id=release_id,
                    workflow_id=workflow_id,
                    submission_id=submission_id,
                    max_poll_count=max_poll_count,
                    poll_interval=poll_interval
                )
            )
            tasks.append(task)
        
        # 等待所有监控任务完成
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"所有构建监控任务完成 - 工作流ID: {workflow_id}")
    
    async def _monitor_single_build(
        self,
        release_id: int,
        workflow_id: str,
        submission_id: str,
        max_poll_count: int,
        poll_interval: int
    ):
        """
        监控单个构建状态
        
        Args:
            release_id: 发布 ID
            workflow_id: 工作流ID
            submission_id: SSO 提交ID
            max_poll_count: 最大轮询次数
            poll_interval: 轮询间隔（秒）
        """
        job_name = None
        build_status = 'BUILDING'
        build_detail = None
        
        try:
            # 创建构建状态记录
            build_record = await asyncio.to_thread(
                self._create_build_status_record,
                submission_id=submission_id,
                workflow_id=workflow_id,
                release_id=release_id
            )
            build_id = build_record.get('build_id')
            
            # 轮询构建状态
            for attempt in range(max_poll_count):
                # 在线程池中执行同步的 API 调用
                build_detail = await asyncio.to_thread(
                    self.client.get_build_detail,
                    release_id
                )
                
                if not build_detail:
                    logger.warning(f"未获取到构建详情 - 发布ID: {release_id}, 尝试: {attempt + 1}/{max_poll_count}")
                    await asyncio.sleep(poll_interval)
                    continue
                
                job_name = build_detail.get('jobName', '')
                publish_status = build_detail.get('publishStatus', '')
                
                logger.info(
                    f"构建状态检查 - 发布ID: {release_id}, Job: {job_name}, "
                    f"状态: {publish_status}, 尝试: {attempt + 1}/{max_poll_count}"
                )
                
                # 更新数据库中的构建状态
                await asyncio.to_thread(
                    self._update_build_status,
                    build_id=build_id,
                    status=publish_status,
                    build_detail=build_detail
                )
                
                # 如果构建完成，退出循环
                if publish_status in ['SUCCESS', 'FAILURE', 'ABORTED']:
                    build_status = publish_status
                    logger.info(f"构建完成 - 发布ID: {release_id}, Job: {job_name}, 状态: {build_status}")
                    break
                
                # 等待下一次轮询
                await asyncio.sleep(poll_interval)
            else:
                # 如果循环正常结束（未遇到 break），说明超时了
                logger.warning(f"构建监控超时 - 发布ID: {release_id}, Job: {job_name}")
                build_status = 'TIMEOUT'
            
            # 触发通知（在 notifier 中处理）
            logger.info(f"构建监控完成 - 发布ID: {release_id}, 状态: {build_status}")
            
        except Exception as e:
            logger.error(f"监控构建状态时发生异常 - 发布ID: {release_id}, 错误: {e}", exc_info=True)
            build_status = 'ERROR'
        
        finally:
            # 确保最终状态已更新
            if build_detail:
                await asyncio.to_thread(
                    self._update_build_status,
                    build_id=build_id if 'build_id' in locals() else None,
                    status=build_status,
                    build_detail=build_detail
                )
    
    def _create_build_status_record(
        self,
        submission_id: str,
        workflow_id: str,
        release_id: int
    ) -> Dict:
        """创建构建状态记录（同步方法，在线程池中调用）"""
        try:
            build_record = WorkflowManager.create_sso_build_status(
                submission_id=submission_id,
                workflow_id=workflow_id,
                release_id=release_id,
                job_name='',  # 首次创建时可能还不知道 job_name
                build_status='BUILDING'
            )
            return build_record
        except Exception as e:
            logger.error(f"创建构建状态记录失败: {e}", exc_info=True)
            raise
    
    def _update_build_status(
        self,
        build_id: str,
        status: str,
        build_detail: Dict
    ):
        """更新构建状态（同步方法，在线程池中调用）"""
        try:
            job_name = build_detail.get('jobName', '')
            WorkflowManager.update_sso_build_status(
                build_id=build_id,
                status=status,
                build_detail=build_detail
            )
            logger.debug(f"更新构建状态 - Build ID: {build_id}, Job: {job_name}, 状态: {status}")
        except Exception as e:
            logger.error(f"更新构建状态失败: {e}", exc_info=True)

