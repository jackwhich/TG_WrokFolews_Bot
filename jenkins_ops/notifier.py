"""Jenkins 通知模块 - 发送 Telegram 通知"""
import re
from typing import Dict
from telegram.ext import ContextTypes
from workflows.models import WorkflowManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JenkinsNotifier:
    """Jenkins 通知器 - 负责发送 Telegram 通知"""
    
    @staticmethod
    async def notify_build_status(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: Dict,
        build_data: Dict
    ):
        """
        通知构建状态（成功/失败/终止）
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 工作流数据
            build_data: 构建数据（包含 build_status, job_name, build_number 等）
        """
        try:
            job_name = build_data.get('job_name', 'N/A')
            status = build_data.get('build_status', 'UNKNOWN')
            
            # 获取项目名称（优先从 workflow_data.project，否则从 submission_data 解析）
            project_name = workflow_data.get('project')
            if not project_name:
                submission_data = workflow_data.get('submission_data', '')
                match = re.search(r'申请项目[：:]\s*([^\n]+)', submission_data)
                if match:
                    project_name = match.group(1).strip()

            # 获取项目级 OPS 用户列表
            options = WorkflowManager.get_project_options()
            project_config = options.get('projects', {}).get(project_name or '', {}) if project_name else {}
            ops_usernames = project_config.get('ops_usernames') or []
            
            # 调试日志
            logger.debug(f"Jenkins 通知 - 项目: {project_name}, OPS 用户: {ops_usernames}, 状态: {status}")
            
            # 获取构建编号和 hash（如果有）
            build_number = build_data.get('build_number')
            # 使用完整的 job_name（包含环境前缀），格式：job_name#build_number
            service_display = f"{job_name}#{build_number}" if build_number else job_name
            git_hash = build_data.get('git_hash')
            
            # 根据状态构建通知消息（使用HTML格式）
            import html
            safe_service_display = html.escape(str(service_display))
            safe_git_hash = html.escape(str(git_hash)) if git_hash else None
            
            if status == 'SUCCESS':
                message = "✅ <b>构建成功</b>\n\n"
                message += f"📦 服务: {safe_service_display}\n"
                if safe_git_hash:
                    message += f"🔑 Hash: <code>{safe_git_hash}</code>\n"
                message += f"✅ 状态: 构建完成"
            elif status == 'FAILURE':
                message = "❌ <b>构建失败</b>\n\n"
                message += f"📦 服务: {safe_service_display}\n"
                if safe_git_hash:
                    message += f"🔑 Hash: <code>{safe_git_hash}</code>\n"
                message += f"❌ 状态: 构建失败\n\n"
                if ops_usernames:
                    mentions = " ".join([f"@{html.escape(str(u))}" for u in ops_usernames if u])
                    if mentions:
                        message += f"{mentions}\n"
                message += "请让运维ops 协助查看错误日志"
            elif status == 'ABORTED':
                message = "⚠️ <b>构建已终止</b>\n\n"
                message += f"📦 服务: {safe_service_display}\n"
                if safe_git_hash:
                    message += f"🔑 Hash: <code>{safe_git_hash}</code>\n"
                message += f"⚠️ 状态: 构建已被终止"
            elif status == 'UNSTABLE':
                message = "⚠️ <b>构建不稳定</b>\n\n"
                message += f"📦 服务: {safe_service_display}\n"
                if safe_git_hash:
                    message += f"🔑 Hash: <code>{safe_git_hash}</code>\n"
                message += f"⚠️ 状态: 构建不稳定（可能有测试失败）"
            else:
                safe_status = html.escape(str(status))
                message = "❓ <b>构建状态未知</b>\n\n"
                message += f"📦 服务: {safe_service_display}\n"
                if safe_git_hash:
                    message += f"🔑 Hash: <code>{safe_git_hash}</code>\n"
                message += f"❓ 状态: {safe_status}"
            
            # 发送到工作流的原始群组
            await JenkinsNotifier._send_to_workflow_groups(context, workflow_data, message)
            
        except Exception as e:
            logger.error(f"发送 Jenkins 构建状态通知失败: {e}", exc_info=True)
    
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
                options = WorkflowManager.get_project_options()
                
                # 解析项目名称
                submission_data = workflow_data.get('submission_data', '')
                match = re.search(r'申请项目[：:]\s*([^\n]+)', submission_data)
                if match:
                    project_name = match.group(1).strip()
                    projects = options.get('projects', {})
                    project_config = projects.get(project_name, {})
                    group_ids = project_config.get('group_ids', [])
                    
                    if group_ids:
                        # 如果没有 group_messages，无法回复，只能直接发送
                        logger.warning(f"⚠️ 未找到原始审批消息ID，无法回复，将直接发送新消息")
                        for group_id in group_ids:
                            try:
                                await context.bot.send_message(
                                    chat_id=group_id,
                                    text=message,
                                    parse_mode='HTML'
                                )
                                logger.info(f"Jenkins 通知已发送到群组 {group_id}")
                            except Exception as e:
                                logger.error(f"发送 Jenkins 通知到群组 {group_id} 失败: {e}")
                        return
            
            # 使用群组消息映射发送（回复到原始审批消息）
            for group_id, original_message_id in group_messages.items():
                try:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=message,
                        parse_mode='HTML',
                        reply_to_message_id=original_message_id  # 回复到原始审批消息
                    )
                    logger.info(f"✅ Jenkins 通知已回复到群组 {group_id} 的原始消息 (消息ID: {original_message_id})")
                except Exception as e:
                    logger.error(f"❌ 发送 Jenkins 通知到群组 {group_id} 失败: {e}")
                    
        except Exception as e:
            logger.error(f"发送 Jenkins 通知到群组失败: {e}", exc_info=True)

