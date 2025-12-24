"""SSO 通知模块 - 发送 Telegram 通知"""
from typing import Dict, Optional
from telegram.ext import ContextTypes
from handlers.notification_handler import NotificationHandler
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSONotifier:
    """SSO 通知器 - 负责发送 Telegram 通知"""
    
    @staticmethod
    async def notify_submission_success(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: Dict,
        sso_submission: Dict
    ):
        """
        通知 SSO 提交成功
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 工作流数据
            sso_submission: SSO 提交记录
        """
        try:
            workflow_id = workflow_data.get('workflow_id', 'N/A')
            process_instance_id = sso_submission.get('process_instance_id', 'N/A')
            submit_time = sso_submission.get('submit_time', 'N/A')
            
            # 解析服务列表
            sso_order_data = sso_submission.get('sso_order_data', {})
            detail = sso_order_data.get('detail', [])
            services_text = "无服务信息"
            
            if detail and len(detail) > 0:
                application_data = None
                for item in detail[0]:
                    if isinstance(item, dict) and item.get('id') == 'application':
                        application_data = item
                        break
                
                if application_data:
                    account_data = application_data.get('account_data', [])
                    if account_data:
                        service_names = [item.get('name', '') for item in account_data]
                        services_text = '\n'.join([f"  • {name}" for name in service_names if name])
            
            # 构建通知消息（使用HTML格式）
            import html
            safe_workflow_id = html.escape(str(workflow_id))
            safe_process_instance_id = html.escape(str(process_instance_id))
            safe_submit_time = html.escape(str(submit_time))
            safe_services_text = html.escape(str(services_text))
            
            message = (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ SSO 工单提交成功\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                f"📋 SSO 工单ID: <code>{safe_process_instance_id}</code>\n"
                f"📅 提交时间: {safe_submit_time}\n\n"
                f"🚀 发布服务:\n{safe_services_text}\n\n"
                f"⏳ 构建正在进行中，完成后将自动通知..."
            )
            
            # 发送到工作流的原始群组
            await SSONotifier._send_to_workflow_groups(context, workflow_data, message)
            
        except Exception as e:
            logger.error(f"发送 SSO 提交成功通知失败: {e}", exc_info=True)
    
    @staticmethod
    async def notify_submission_failed(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: Dict,
        error_message: str
    ):
        """
        通知 SSO 提交失败
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 工作流数据
            error_message: 错误信息
        """
        try:
            workflow_id = workflow_data.get('workflow_id', 'N/A')
            
            # 构建通知消息（使用HTML格式）
            import html
            safe_workflow_id = html.escape(str(workflow_id))
            safe_approval_time = html.escape(str(workflow_data.get('approval_time', 'N/A')))
            safe_error_message = html.escape(str(error_message))
            
            message = (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"❌ SSO 工单提交失败\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                f"📅 提交时间: {safe_approval_time}\n\n"
                f"❌ 错误信息: {safe_error_message}\n\n"
                f"请检查配置或联系管理员"
            )
            
            # 发送到工作流的原始群组
            await SSONotifier._send_to_workflow_groups(context, workflow_data, message)
            
        except Exception as e:
            logger.error(f"发送 SSO 提交失败通知失败: {e}", exc_info=True)
    
    @staticmethod
    async def notify_build_status(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: Dict,
        build_status: Dict
    ):
        """
        通知构建状态
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 工作流数据
            build_status: 构建状态记录
        """
        try:
            workflow_id = workflow_data.get('workflow_id', 'N/A')
            job_name = build_status.get('job_name', 'N/A')
            status = build_status.get('build_status', 'UNKNOWN')
            build_start_time = build_status.get('build_start_time')
            build_end_time = build_status.get('build_end_time')
            
            # 计算构建时长
            build_duration = "未知"
            if build_start_time and build_end_time:
                duration_seconds = build_end_time - build_start_time
                minutes = duration_seconds // 60
                seconds = duration_seconds % 60
                build_duration = f"{minutes}分{seconds}秒"
            
            # HTML转义
            import html
            safe_workflow_id = html.escape(str(workflow_id))
            safe_job_name = html.escape(str(job_name))
            safe_build_duration = html.escape(str(build_duration))
            safe_status = html.escape(str(status))
            
            if status == 'SUCCESS':
                message = (
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ 构建成功\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                    f"📋 服务名称: {safe_job_name}\n"
                    f"⏱️ 构建时间: {safe_build_duration}\n\n"
                    f"✅ 构建状态: 成功\n"
                    f"💡 请研发查看服务启动日志"
                )
            elif status == 'FAILURE':
                approver_username = workflow_data.get('approver_username', '')
                safe_approver_username = html.escape(str(approver_username)) if approver_username else ''
                message = (
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"❌ 构建失败\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                    f"📋 服务名称: {safe_job_name}\n"
                    f"⏱️ 构建时间: {safe_build_duration}\n\n"
                    f"❌ 构建状态: 失败\n"
                    f"🔍 请查看日志排查问题\n\n"
                )
                if safe_approver_username:
                    message += f"@{safe_approver_username} 请查看日志"
            elif status == 'ABORTED':
                message = (
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ 构建已终止\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                    f"📋 服务名称: {safe_job_name}\n\n"
                    f"⚠️ 构建状态: 已终止"
                )
            else:
                message = (
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"❓ 构建状态未知\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 工作流ID: <code>{safe_workflow_id}</code>\n"
                    f"📋 服务名称: {safe_job_name}\n"
                    f"状态: {safe_status}"
                )
            
            # 发送到工作流的原始群组
            await SSONotifier._send_to_workflow_groups(context, workflow_data, message)
            
        except Exception as e:
            logger.error(f"发送构建状态通知失败: {e}", exc_info=True)
    
    @staticmethod
    async def _send_to_workflow_groups(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: Dict,
        message: str
    ):
        """
        发送消息到工作流的原始群组
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 工作流数据
            message: 消息内容
        """
        try:
            group_messages = workflow_data.get('group_messages', {})
            if not group_messages:
                # 如果没有群组消息映射，尝试从项目配置获取群组ID
                from workflows.models import WorkflowManager
                options = WorkflowManager.get_project_options()
                
                # 解析项目名称
                submission_data = workflow_data.get('submission_data', '')
                import re
                match = re.search(r'申请项目[：:]\s*([^\n]+)', submission_data)
                if match:
                    project_name = match.group(1).strip()
                    projects = options.get('projects', {})
                    project_config = projects.get(project_name, {})
                    group_ids = project_config.get('group_ids', [])
                    
                    if group_ids:
                        for group_id in group_ids:
                            try:
                                await context.bot.send_message(
                                    chat_id=group_id,
                                    text=message,
                                    parse_mode='HTML'
                                )
                                logger.info(f"SSO 通知已发送到群组 {group_id}")
                            except Exception as e:
                                logger.error(f"发送 SSO 通知到群组 {group_id} 失败: {e}")
                        return
            
            # 使用群组消息映射发送
            for group_id, message_id in group_messages.items():
                try:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"SSO 通知已发送到群组 {group_id}")
                except Exception as e:
                    logger.error(f"发送 SSO 通知到群组 {group_id} 失败: {e}")
                    
        except Exception as e:
            logger.error(f"发送 SSO 通知到群组失败: {e}", exc_info=True)

