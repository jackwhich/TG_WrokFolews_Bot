"""Jenkins 构建状态监控模块"""
import asyncio
import time
from typing import Dict, Optional
from jenkins_ops.client import JenkinsClient
from jenkins_ops.notifier import JenkinsNotifier
from workflows.models import WorkflowManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsMonitor:
    """Jenkins 构建状态监控器"""
    
    def __init__(self, project_name: str):
        """
        初始化监控器
        
        Args:
            project_name: 项目名称，用于获取该项目的 Jenkins 配置
        """
        self.project_name = project_name
        self.client = JenkinsClient(project_name)
    
    async def monitor_build(
        self,
        workflow_id: str,
        job_name: str,
        build_number: int,
        context=None,
        max_poll_count: int = 60,
        poll_interval: int = 10
    ):
        """
        监控构建状态（异步）
        
        Args:
            workflow_id: 工作流ID
            job_name: Jenkins Job 名称
            build_number: 构建编号
            max_poll_count: 最大轮询次数（默认60次，即10分钟）
            poll_interval: 轮询间隔（秒，默认10秒）
        """
        logger.info(f"🔍 开始监控 Jenkins 构建状态")
        logger.info(f"   工作流ID: {workflow_id}")
        logger.info(f"   Job: {job_name}")
        logger.info(f"   构建编号: #{build_number}")
        logger.info(f"   查询路径: job/{job_name}/{build_number}/api/json")
        
        build_id = None
        build_status = 'BUILDING'
        
        try:
            # 获取或创建构建记录
            build_record = await asyncio.to_thread(
                self._get_or_create_build_record,
                workflow_id=workflow_id,
                job_name=job_name,
                build_number=build_number
            )
            build_id = build_record.get('build_id')
            
            # 轮询构建状态，持续查询直到构建完成（成功或失败）
            for attempt in range(max_poll_count):
                try:
                    # 在线程池中执行同步的 API 调用
                    build_info = await asyncio.to_thread(
                        self.client.get_build_info,
                        job_name=job_name,
                        build_number=build_number
                    )
                    
                    if not build_info:
                        # 构建信息不存在，可能还在队列中等待或构建尚未开始，继续查询
                        if attempt % 10 == 0:  # 每10次尝试输出一次日志（减少日志噪音）
                            logger.info(f"⏳ 构建 #{build_number} 仍在队列中等待或尚未开始... - Job: {job_name}, 已等待: {(attempt + 1) * poll_interval}秒")
                        
                        # 更新数据库状态为队列中（如果 build_id 存在）
                        if build_id:
                            await asyncio.to_thread(
                                self._update_build_status,
                                build_id=build_id,
                                build_info=None,
                                build_status='QUEUED'
                            )
                        
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    # 判断构建状态（参考用户示例代码的逻辑）
                    is_building = build_info.get('building', False)
                    result = build_info.get('result')  # Jenkins 使用 'result' 字段
                    
                    # 构建状态判断
                    if is_building:
                        # 正在构建中
                        build_status = 'BUILDING'
                        # 每10次轮询输出一次日志（让用户知道监控在进行中）
                        if attempt % 10 == 0:
                            logger.info(f"⏳ 构建 #{build_number} 正在进行中... - Job: {job_name}, 已等待: {(attempt + 1) * poll_interval}秒")
                        
                        # 更新数据库中的构建状态
                        await asyncio.to_thread(
                            self._update_build_status,
                            build_id=build_id,
                            build_info=build_info,
                            build_status=build_status
                        )
                        
                        # 继续等待，不退出循环
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    elif result == 'SUCCESS':
                        # 构建完成，结果: SUCCESS
                        build_status = 'SUCCESS'
                        logger.info(f"✅ 构建 #{build_number} 已完成，结果: SUCCESS - Job: {job_name}")
                        
                        # 更新数据库中的构建状态
                        await asyncio.to_thread(
                            self._update_build_status,
                            build_id=build_id,
                            build_info=build_info,
                            build_status=build_status
                        )
                        # 构建成功，退出轮询循环
                        break
                    
                    elif result == 'FAILURE':
                        # 构建完成，结果: FAILURE
                        build_status = 'FAILURE'
                        logger.info(f"❌ 构建 #{build_number} 已完成，结果: FAILURE - Job: {job_name}")
                        
                        # 更新数据库中的构建状态
                        await asyncio.to_thread(
                            self._update_build_status,
                            build_id=build_id,
                            build_info=build_info,
                            build_status=build_status
                        )
                        # 构建失败，退出轮询循环
                        break
                    
                    elif result in ['ABORTED', 'UNSTABLE']:
                        # 构建完成，但被终止或不稳定
                        build_status = result
                        logger.info(f"⚠️ 构建 #{build_number} 已完成，结果: {result} - Job: {job_name}")
                        
                        # 更新数据库中的构建状态
                        await asyncio.to_thread(
                            self._update_build_status,
                            build_id=build_id,
                            build_info=build_info,
                            build_status=build_status
                        )
                        # 构建完成（非成功状态），退出轮询循环
                        break
                    
                    else:
                        # 构建结果未知
                        build_status = result or 'UNKNOWN'
                        logger.warning(f"⚠️ 构建 #{build_number} 结果未知: {result} - Job: {job_name}")
                        # 更新数据库状态，但继续轮询（可能还在初始化）
                        await asyncio.to_thread(
                            self._update_build_status,
                            build_id=build_id,
                            build_info=build_info,
                            build_status='BUILDING'  # 暂时标记为构建中
                        )
                        await asyncio.sleep(poll_interval)
                        continue
                        
                except Exception as e:
                    # 查询异常，记录错误并重试
                    if attempt % 5 == 0:  # 每5次尝试输出一次错误
                        logger.warning(f"⚠️ 获取构建状态失败 (第 {attempt + 1} 次尝试): {e} - Job: {job_name}, Build: #{build_number}")
                    await asyncio.sleep(poll_interval)
                    continue
            else:
                # 如果循环正常结束（未遇到 break），说明超时了
                logger.warning(f"⚠️ 构建监控超时 - 工作流ID: {workflow_id}, Job: {job_name}, Build: {build_number}")
                build_status = 'TIMEOUT'
                await asyncio.to_thread(
                    self._update_build_status,
                    build_id=build_id,
                    build_info=None,
                    build_status=build_status
                )
            
            # 构建完成后，根据最终状态发送通知（成功、失败、终止、不稳定、超时、错误）
            if build_status in ['SUCCESS', 'FAILURE', 'ABORTED', 'UNSTABLE', 'TIMEOUT', 'ERROR']:
                logger.info(f"📢 构建完成，准备发送通知 - 工作流ID: {workflow_id}, Job: {job_name}, Build: #{build_number}, 状态: {build_status}")
                
                if context:
                    # 获取工作流数据
                    workflow_data = await asyncio.to_thread(WorkflowManager.get_workflow, workflow_id)
                    if workflow_data:
                        # 获取最新的构建数据
                        build_record = await asyncio.to_thread(
                            WorkflowManager.get_jenkins_build_by_workflow,
                            workflow_id
                        )
                        if build_record:
                            # 发送通知到 TG 群
                            await JenkinsNotifier.notify_build_status(
                                context=context,
                                workflow_data=workflow_data,
                                build_data={
                                    'job_name': build_record.get('job_name', job_name),
                                    'build_status': build_status
                                }
                            )
                            # 标记为已通知
                            await asyncio.to_thread(
                                WorkflowManager.mark_jenkins_build_notified,
                                build_id
                            )
                            logger.info(f"✅ 构建通知已发送到 TG 群 - 工作流ID: {workflow_id}, Job: {job_name}, Build: #{build_number}, 状态: {build_status}")
                        else:
                            logger.warning(f"⚠️ 未找到构建记录，无法发送通知 - 工作流ID: {workflow_id}, Build ID: {build_id}")
                    else:
                        logger.warning(f"⚠️ 未找到工作流数据，无法发送通知 - 工作流ID: {workflow_id}")
                else:
                    logger.warning(f"⚠️ 未提供 context，无法发送通知 - 工作流ID: {workflow_id}, Job: {job_name}, Build: {build_number}")
            else:
                logger.warning(f"⚠️ 构建状态异常，不发送通知 - 工作流ID: {workflow_id}, Job: {job_name}, Build: {build_number}, 状态: {build_status}")
            
            logger.info(f"构建监控完成 - 工作流ID: {workflow_id}, Job: {job_name}, Build: {build_number}, 状态: {build_status}")
            
        except Exception as e:
            logger.error(f"监控构建状态时发生异常 - 工作流ID: {workflow_id}, Job: {job_name}, Build: {build_number}, 错误: {e}", exc_info=True)
            build_status = 'ERROR'
            if build_id:
                await asyncio.to_thread(
                    self._update_build_status,
                    build_id=build_id,
                    build_info=None,
                    build_status=build_status
                )
    
    def _get_or_create_build_record(
        self,
        workflow_id: str,
        job_name: str,
        build_number: int
    ) -> Dict:
        """获取或创建构建记录（同步方法，在线程池中调用）"""
        try:
            # 先尝试获取现有记录
            existing_build = WorkflowManager.get_jenkins_build_by_workflow(workflow_id)
            if existing_build and existing_build.get('build_number') == build_number:
                return existing_build
            
            # 创建新记录
            build_record = WorkflowManager.create_jenkins_build(
                workflow_id=workflow_id,
                job_name=job_name,
                build_number=build_number,
                build_status='BUILDING'
            )
            return build_record
        except Exception as e:
            logger.error(f"获取或创建构建记录失败: {e}", exc_info=True)
            raise
    
    def _update_build_status(
        self,
        build_id: str,
        build_info: Optional[Dict],
        build_status: str
    ):
        """更新构建状态（同步方法，在线程池中调用）"""
        try:
            update_data = {
                'build_status': build_status
            }
            
            if build_info:
                # 更新构建信息
                if not build_info.get('building', False) and build_info.get('status'):
                    # 构建完成，记录结束时间和时长
                    build_end_time = int(time.time())
                    duration_ms = build_info.get('duration', 0)
                    update_data['build_end_time'] = build_end_time
                    update_data['build_duration'] = duration_ms
                
                # 更新 Job URL
                if build_info.get('url'):
                    update_data['job_url'] = build_info.get('url')
            
            WorkflowManager.update_jenkins_build(build_id, **update_data)
            logger.debug(f"更新构建状态 - Build ID: {build_id}, 状态: {build_status}")
        except Exception as e:
            logger.error(f"更新构建状态失败: {e}", exc_info=True)

