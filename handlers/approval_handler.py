"""审批处理器"""
from telegram import Update
from telegram.ext import ContextTypes
from workflows.models import WorkflowManager
from workflows.state_machine import WorkflowStateMachine
from api.sync import sync_workflow_to_api
from handlers.notification_handler import NotificationHandler
from config.settings import Settings
from config.constants import ACTION_APPROVE, ACTION_REJECT
from utils.logger import setup_logger
from utils.helpers import get_user_info

logger = setup_logger(__name__)


class ApprovalHandler:
    """审批处理器"""
    
    @staticmethod
    async def handle_approval_callback(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        """处理审批回调"""
        query = update.callback_query
        
        try:
            logger.info(f"收到审批回调，用户ID: {query.from_user.id}, 回调数据: {query.data}")
            
            # 解析回调数据
            data = query.data
            if ":" not in data:
                logger.warning(f"无效的审批回调数据: {data}")
                await query.answer("❌ 无效的审批操作", show_alert=True)
                return
            
            action, workflow_id = data.split(":", 1)
            logger.info(f"解析审批操作 - 动作: {action}, 工作流ID: {workflow_id}")
            
            # 获取审批人信息（自动捕获点击按钮的用户）
            approver_id, approver_username = get_user_info(update)
            logger.debug(f"审批人信息 - ID: {approver_id}, 用户名: {approver_username}")
            
            # 先快速响应按钮点击，让按钮立即消失（在权限检查之前）
            if action == ACTION_APPROVE:
                await query.answer("✅ 正在处理审批...")
            else:
                await query.answer("❌ 正在处理拒绝...")
            
            # 只有"通过"操作需要权限检查，"拒绝"操作所有人都可以执行（相当于取消按钮）
            if action == ACTION_APPROVE:
                # 如果配置了审批人限制，则验证权限（在 answer 之后检查，因为按钮已经消失了）
                # 检查是否配置了审批人限制（从数据库读取）
                approver_username_config = WorkflowManager.get_app_config("APPROVER_USERNAME", "")
                approver_user_id_str = WorkflowManager.get_app_config("APPROVER_USER_ID", "")
                try:
                    approver_user_id_config = int(approver_user_id_str) if approver_user_id_str else 0
                except ValueError:
                    approver_user_id_config = 0
                
                is_restricted = approver_user_id_config != 0 or bool(approver_username_config)
                
                if is_restricted:
                    has_permission = False
                    
                    # 优先使用用户名验证（更直观）
                    if approver_username_config:
                        # 去掉 @ 符号（如果有）
                        configured_username = approver_username_config.lstrip('@')
                        user_username = (query.from_user.username or "").lower()
                        if user_username == configured_username.lower():
                            has_permission = True
                            logger.info(f"审批权限验证通过（通过用户名） - 用户名: {approver_username}")
                    
                    # 如果用户名验证失败，且配置了用户ID，则使用用户ID验证
                    if not has_permission and approver_user_id_config != 0:
                        if approver_id == approver_user_id_config:
                            has_permission = True
                            logger.info(f"审批权限验证通过（通过用户ID） - 用户ID: {approver_id}")
                    
                    # 如果都没有权限，拒绝审批并显示提示
                    if not has_permission:
                        configured_info = []
                        if approver_username_config:
                            configured_info.append(f"用户名: @{approver_username_config}")
                        if approver_user_id_config != 0:
                            configured_info.append(f"用户ID: {approver_user_id_config}")
                        logger.warning(
                            f"用户 {approver_id} ({approver_username}) 尝试审批但无权限，"
                            f"配置的审批人: {', '.join(configured_info)}"
                        )
                        # 显示无权限提示（使用 show_alert=True 显示弹窗）
                        await query.answer("❌ 你无权同意此次服务发版", show_alert=True)
                        return
            elif action == ACTION_REJECT:
                # 拒绝操作不需要权限检查，所有人都可以拒绝（相当于取消按钮）
                logger.info(f"用户 {approver_id} ({approver_username}) 执行拒绝操作（无需权限检查）")
            
            # 将整个审批流程放到后台任务中，立即返回，不阻塞响应
            import asyncio
            
            async def _process_approval():
                """在后台处理整个审批流程"""
                try:
                    # 使用线程池执行数据库操作，避免阻塞事件循环
                    # 获取工作流
                    workflow = await asyncio.to_thread(WorkflowManager.get_workflow, workflow_id)
                    if not workflow:
                        logger.error(f"工作流不存在 - ID: {workflow_id}")
                        try:
                            await query.edit_message_text("❌ 工作流不存在或已过期")
                        except:
                            pass
                        return
                    
                    logger.info(f"找到工作流 - ID: {workflow_id}, 当前状态: {workflow.get('status')}")
                    
                    # 检查状态
                    if workflow["status"] != "pending":
                        logger.warning(f"工作流 {workflow_id} 已被审批，当前状态: {workflow['status']}")
                        try:
                            await query.answer("⚠️ 该工作流已被审批", show_alert=True)
                        except:
                            pass
                        return
                    
                    # 执行审批（自动捕获审批人信息）- 在线程池中执行
                    logger.info(f"开始执行审批操作 - 工作流ID: {workflow_id}, 动作: {action}, 审批人: {approver_username} ({approver_id})")
                    success = False
                    if action == ACTION_APPROVE:
                        # 使用 lambda 包装以支持关键字参数
                        success = await asyncio.to_thread(
                            lambda: WorkflowStateMachine.approve_workflow(
                                workflow_id=workflow_id,
                                approver_id=approver_id,
                                approver_username=approver_username,
                            )
                        )
                        logger.info(f"审批通过操作 {'成功' if success else '失败'} - 工作流ID: {workflow_id}")
                    elif action == ACTION_REJECT:
                        # 使用 lambda 包装以支持关键字参数
                        success = await asyncio.to_thread(
                            lambda: WorkflowStateMachine.reject_workflow(
                                workflow_id=workflow_id,
                                approver_id=approver_id,
                                approver_username=approver_username,
                            )
                        )
                        logger.info(f"审批拒绝操作 {'成功' if success else '失败'} - 工作流ID: {workflow_id}")
                    else:
                        logger.warning(f"未知的审批动作: {action}")
                    
                    if not success:
                        logger.error(f"审批操作失败 - 工作流ID: {workflow_id}, 动作: {action}")
                        try:
                            await query.edit_message_text("❌ 审批操作失败")
                        except:
                            pass
                        return
                    
                    # 获取更新后的工作流数据（在线程池中执行）
                    updated_workflow = await asyncio.to_thread(WorkflowManager.get_workflow, workflow_id)
                    if not updated_workflow:
                        logger.error(f"无法获取更新后的工作流数据 - ID: {workflow_id}")
                        try:
                            await query.edit_message_text("❌ 获取工作流数据失败")
                        except:
                            pass
                        return
                    
                    logger.info(f"工作流状态已更新 - ID: {workflow_id}, 新状态: {updated_workflow.get('status')}")
                    
                    # 同步到外部API（如果配置了）- 使用线程池执行同步HTTP请求，避免阻塞事件循环
                    if Settings.is_api_enabled():
                        logger.info(f"开始同步工作流 {workflow_id} 到外部API...")
                        try:
                            # 使用 asyncio.to_thread 在线程池中执行同步的API调用，不阻塞事件循环
                            sync_success, sync_error = await asyncio.to_thread(
                                sync_workflow_to_api, updated_workflow
                            )
                            if sync_success:
                                logger.info(f"✅ 工作流 {workflow_id} 已成功同步到外部API，外部系统已收到审批结果")
                            else:
                                logger.error(f"❌ 工作流 {workflow_id} API同步失败: {sync_error}")
                                # 即使API同步失败，也继续处理审批结果（Telegram内已完成）
                        except Exception as e:
                            logger.error(f"❌ 同步到外部API时发生异常 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
                    else:
                        logger.info(f"⚠️ 工作流 {workflow_id} 未配置外部API，仅完成Telegram内审批流程")
                    
                    # SSO 提交（仅在审批通过时执行）
                    if action == ACTION_APPROVE:
                        await ApprovalHandler._submit_to_sso(
                            context=context,
                            workflow_data=updated_workflow,
                            approver_username=approver_username
                        )
                    
                        # Jenkins 构建触发（仅在审批通过时执行）
                        await ApprovalHandler._trigger_jenkins_build(
                            context=context,
                            workflow_data=updated_workflow,
                            approver_username=approver_username
                        )
                    
                    # 更新群组消息（会自动更新所有群组的消息）
                    logger.info(f"正在更新群组消息 - 工作流ID: {workflow_id}")
                    group_messages = updated_workflow.get("group_messages", {})
                    if group_messages:
                        try:
                            # 不传 message_id，会自动更新所有群组的消息
                            await NotificationHandler.update_group_message(
                                context=context,
                                workflow_data=updated_workflow,
                            )
                        except Exception as e:
                            logger.error(f"更新群组消息失败 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
                    else:
                        logger.warning(f"工作流 {workflow_id} 没有群组消息ID，跳过更新")
                    
                    # 通知提交用户（带超时，不阻塞）
                    logger.info(f"正在通知提交用户 - 工作流ID: {workflow_id}, 用户ID: {workflow['user_id']}")
                    await NotificationHandler.notify_user(
                        context=context,
                        workflow_data=updated_workflow,
                        user_id=workflow["user_id"],
                        timeout=5.0,  # 5秒超时
                    )
                    
                    logger.info(
                        f"✅ 审批流程完成 - 工作流ID: {workflow_id}, 审批人: {approver_username} ({approver_id}), "
                        f"动作: {'通过' if action == ACTION_APPROVE else '拒绝'}"
                    )
                except Exception as e:
                    logger.error(f"后台审批处理失败 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
                    try:
                        await query.edit_message_text("❌ 审批过程中发生错误，请稍后重试")
                    except:
                        pass
            
            # 创建后台任务，立即返回，不等待完成
            asyncio.create_task(_process_approval())
            
        except Exception as e:
            logger.error(f"❌ 处理审批回调时发生错误: {str(e)}", exc_info=True)
            try:
                await query.edit_message_text("❌ 审批过程中发生错误，请稍后重试")
            except:
                pass
    
    @staticmethod
    async def _submit_to_sso(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: dict,
        approver_username: str
    ):
        """
        提交工作流到 SSO 系统（在审批通过后调用）
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 完整的工作流数据（从数据库获取）
            approver_username: 审批人用户名
        """
        import asyncio
        from sso.config import SSOConfig
        from sso.client import SSOClient
        from sso.data_converter import parse_tg_submission_data, convert_to_sso_format
        from sso.monitor import SSOMonitor
        from sso.notifier import SSONotifier
        
        workflow_id = workflow_data.get('workflow_id')
        
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"🚀 开始 SSO 提交流程 - 工作流ID: {workflow_id}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        try:
            # 检查 SSO 是否启用
            logger.info(f"📋 检查 SSO 是否启用...")
            if not SSOConfig.is_enabled():
                logger.warning(f"⚠️ SSO 集成未启用，跳过 SSO 提交 - 工作流ID: {workflow_id}")
                logger.info(f"💡 提示：如需启用 SSO 集成，请修改 scripts/init_db.py 中的 DEFAULT_SSO_ENABLED = True，并配置 SSO_AUTH_TOKEN 和 SSO_AUTHORIZATION，然后运行 python3 scripts/init_db.py 更新数据库配置")
                return
            
            logger.info(f"✅ SSO 集成已启用")
            
            # 验证 SSO 配置
            logger.info(f"📋 验证 SSO 配置...")
            if not SSOConfig.validate():
                logger.error(f"❌ SSO 配置验证失败，无法提交到 SSO - 工作流ID: {workflow_id}")
                logger.error(f"💡 请检查以下配置项：")
                logger.error(f"   - SSO_URL: {SSOConfig.get_url()}")
                logger.error(f"   - SSO_AUTH_TOKEN: {'已配置' if SSOConfig.get_auth_token() else '未配置'}")
                logger.error(f"   - SSO_AUTHORIZATION: {'已配置' if SSOConfig.get_authorization() else '未配置'}")
                
                logger.error(f"💡 提示：请配置 SSO_AUTH_TOKEN 和 SSO_AUTHORIZATION 后重启 Bot")
                # 不发送配置失败通知给用户，只在日志中记录
                return
            
            logger.info(f"✅ SSO 配置验证通过")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📝 开始提交工作流到 SSO 系统 - 工作流ID: {workflow_id}")
            
            # 解析提交数据
            submission_data = workflow_data.get('submission_data', '')
            if not submission_data:
                raise ValueError("工作流数据中缺少 submission_data")
            
            tg_data = parse_tg_submission_data(submission_data)
            project_name = tg_data.get('project')
            environment = tg_data.get('environment')
            services = tg_data.get('services', [])
            
            if not project_name:
                raise ValueError("无法从提交数据中解析项目名称")
            if not environment:
                raise ValueError("无法从提交数据中解析环境")
            if not services:
                raise ValueError("未找到要部署的服务列表")
            
            logger.info(f"✅ 解析 SSO 提交数据成功")
            logger.info(f"   📦 项目: {project_name}")
            logger.info(f"   🌍 环境: {environment}")
            logger.info(f"   🚀 服务数量: {len(services)}, 服务列表: {services}")
            
            # 获取 Job IDs
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📡 步骤 1/5: 正在获取 Job IDs...")
            logger.info(f"   项目: {project_name}, 环境: {environment}, 服务: {services}")
            # 使用项目名称初始化 SSO 客户端（会使用该项目的代理配置）
            sso_client = SSOClient(project_name=project_name)
            job_ids = await asyncio.to_thread(
                sso_client.get_job_ids,
                server_names=services,
                project_name=project_name,
                env=environment
            )
            
            if not job_ids or len(job_ids) != len(services):
                error_msg = f"获取 Job ID 失败或数量不匹配 - 期望: {len(services)}, 实际: {len(job_ids) if job_ids else 0}"
                logger.error(f"❌ {error_msg} - 工作流ID: {workflow_id}")
                raise ValueError(error_msg)
            
            logger.info(f"✅ 获取到 Job IDs 成功: {job_ids}")
            
            # 转换为 SSO 格式
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📝 步骤 2/5: 正在转换数据为 SSO 格式...")
            sso_order_data = convert_to_sso_format(
                workflow_data=workflow_data,
                job_ids=job_ids,
                approver_email=approver_username
            )
            
            logger.info(f"✅ 数据转换为 SSO 格式成功")
            
            # 创建 SSO 提交记录（先创建记录，状态为 pending）
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"💾 步骤 3/5: 正在创建 SSO 提交记录...")
            sso_submission = await asyncio.to_thread(
                WorkflowManager.create_sso_submission,
                workflow_id=workflow_id,
                sso_order_data=sso_order_data
            )
            submission_id = sso_submission['submission_id']
            logger.info(f"✅ SSO 提交记录已创建 - Submission ID: {submission_id}")
            
            # 提交到 SSO 系统
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📤 步骤 4/5: 正在提交 SSO 工单到 SSO 系统...")
            logger.info(f"   Submission ID: {submission_id}")
            submit_response = await asyncio.to_thread(
                sso_client.submit_order,
                sso_order_data
            )
            
            logger.info(f"✅ SSO 工单提交 API 调用成功")
            logger.info(f"   响应: {submit_response}")
            
            # 获取 process_instance_id
            process_instance_id = submit_response.get('object', {}).get('processInstanceId') if submit_response.get('object') else None
            
            if not process_instance_id:
                error_msg = "SSO 提交响应中未找到 processInstanceId"
                logger.error(f"❌ {error_msg} - Submission ID: {submission_id}")
                logger.error(f"   完整响应: {submit_response}")
                raise ValueError(error_msg)
            
            logger.info(f"✅ SSO 工单提交成功 - Process Instance ID: {process_instance_id}")
            
            # 更新 SSO 提交记录状态
            logger.info(f"💾 正在更新 SSO 提交记录状态为 'success'...")
            await asyncio.to_thread(
                WorkflowManager.update_sso_submission_status,
                submission_id=submission_id,
                status='success',
                response=submit_response
            )
            logger.info(f"✅ SSO 提交记录状态已更新")
            
            # 获取发布 IDs
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📋 步骤 5/5: 正在获取发布 ID...")
            logger.info(f"   Process Instance ID: {process_instance_id}")
            release_ids = await asyncio.to_thread(
                sso_client.get_release_ids,
                process_instance_id
            )
            
            if not release_ids:
                logger.warning(f"⚠️ 未获取到发布 ID - Process Instance ID: {process_instance_id}")
                logger.warning(f"   构建监控将不会启动")
            else:
                logger.info(f"✅ 获取到发布 IDs: {release_ids}")
                
                # 启动构建状态监控任务（在后台运行，不阻塞）
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"🔍 启动构建状态监控任务...")
                logger.info(f"   发布 ID 数量: {len(release_ids)}")
                # 使用项目名称初始化 SSO 监控器（会使用该项目的代理配置）
                monitor = SSOMonitor(project_name=project_name)
                asyncio.create_task(
                    monitor.monitor_build_status(
                        release_ids=release_ids,
                        workflow_id=workflow_id,
                        submission_id=submission_id
                    )
                )
                logger.info(f"✅ 已启动 {len(release_ids)} 个构建监控任务（后台运行）")
                logger.info(f"   监控将在后台持续运行，构建完成后会自动发送通知")
            
            # 发送提交成功通知
            logger.info(f"📢 正在发送 SSO 提交成功通知...")
            sso_submission['process_instance_id'] = process_instance_id
            await SSONotifier.notify_submission_success(
                context=context,
                workflow_data=workflow_data,
                sso_submission=sso_submission
            )
            logger.info(f"✅ SSO 提交成功通知已发送")
            
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"✅ SSO 提交流程全部完成！")
            logger.info(f"   工作流ID: {workflow_id}")
            logger.info(f"   SSO 工单ID (Process Instance ID): {process_instance_id}")
            logger.info(f"   发布 ID: {release_ids if release_ids else '无'}")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
        except Exception as e:
            logger.error(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error(f"❌ SSO 提交失败 - 工作流ID: {workflow_id}")
            logger.error(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误信息: {str(e)}")
            logger.error(f"详细错误:", exc_info=True)
            
            # 更新提交记录状态为失败
            try:
                submission_id = workflow_id  # 使用 workflow_id 作为 submission_id
                logger.info(f"💾 正在更新 SSO 提交记录状态为 'failed'...")
                await asyncio.to_thread(
                    WorkflowManager.update_sso_submission_status,
                    submission_id=submission_id,
                    status='failed',
                    error=str(e)
                )
                logger.info(f"✅ SSO 提交记录状态已更新为 'failed'")
            except Exception as update_error:
                logger.error(f"❌ 更新 SSO 提交状态失败: {update_error}", exc_info=True)
            
            # 不发送失败通知给用户，只在日志中记录错误
            # SSO 提交失败不影响审批流程，错误信息已记录在日志中
            logger.warning(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.warning(f"⚠️ SSO 提交失败，但审批流程已完成")
            logger.warning(f"   工作流ID: {workflow_id}")
            logger.warning(f"   审批流程不受影响，工作流状态已更新为 'approved'")
            logger.warning(f"   SSO 错误已记录在日志中，不向用户发送失败通知")
            logger.warning(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    @staticmethod
    async def _trigger_jenkins_build(
        context: ContextTypes.DEFAULT_TYPE,
        workflow_data: dict,
        approver_username: str
    ):
        """
        触发 Jenkins 构建（在审批通过后调用）
        
        Args:
            context: Telegram 上下文对象
            workflow_data: 完整的工作流数据（从数据库获取）
            approver_username: 审批人用户名
        """
        import asyncio
        from jenkins_ops.config import JenkinsConfig
        from jenkins_ops.client import JenkinsClient
        from jenkins_ops.monitor import JenkinsMonitor
        from jenkins_ops.notifier import JenkinsNotifier
        from sso.data_converter import parse_tg_submission_data
        
        workflow_id = workflow_data.get('workflow_id')
        
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"🚀 开始 Jenkins 构建流程 - 工作流ID: {workflow_id}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        try:
            # 解析提交数据（先解析以获取项目名称）
            submission_data = workflow_data.get('submission_data', '')
            if not submission_data:
                raise ValueError("工作流数据中缺少 submission_data")
            
            tg_data = parse_tg_submission_data(submission_data)
            project_name = tg_data.get('project')
            environment = tg_data.get('environment')
            services = tg_data.get('services', [])
            hashes = tg_data.get('hashes', [])
            branch = tg_data.get('branch', 'uat-ebpay')  # 默认分支
            
            if not project_name:
                raise ValueError("无法从提交数据中解析项目名称")
            if not environment:
                raise ValueError("无法从提交数据中解析环境")
            if not services:
                raise ValueError("未找到要部署的服务列表")
            
            logger.info(f"✅ 解析 Jenkins 构建数据成功")
            logger.info(f"   📦 项目: {project_name}")
            logger.info(f"   🌍 环境: {environment}")
            logger.info(f"   🚀 服务数量: {len(services)}, 服务列表: {services}")
            logger.info(f"   🔑 Hash 数量: {len(hashes)}, Hash 列表: {hashes}")
            logger.info(f"   🌿 分支: {branch}")
            
            # 检查该项目的 Jenkins 是否启用
            logger.info(f"📋 检查项目 {project_name} 的 Jenkins 是否启用...")
            if not JenkinsConfig.is_enabled(project_name):
                logger.warning(f"⚠️ 项目 {project_name} 的 Jenkins 集成未启用，跳过 Jenkins 构建 - 工作流ID: {workflow_id}")
                logger.info(f"💡 提示：如需启用 Jenkins 集成，请在 scripts/options.json 中为项目 {project_name} 配置 jenkins.enabled = true，并配置 jenkins.url 和 jenkins.api_token，然后运行 python3 scripts/init_db.py 更新数据库配置")
                return
            
            logger.info(f"✅ 项目 {project_name} 的 Jenkins 集成已启用")
            
            # 验证该项目的 Jenkins 配置
            logger.info(f"📋 验证项目 {project_name} 的 Jenkins 配置...")
            if not JenkinsConfig.validate(project_name):
                logger.error(f"❌ 项目 {project_name} 的 Jenkins 配置验证失败，无法触发构建 - 工作流ID: {workflow_id}")
                logger.error(f"💡 请检查 scripts/options.json 中项目 {project_name} 的以下配置项：")
                logger.error(f"   - jenkins.url: {JenkinsConfig.get_url(project_name)}")
                logger.error(f"   - jenkins.api_token: {'已配置' if JenkinsConfig.get_api_token(project_name) else '未配置'}")
                return
            
            logger.info(f"✅ 项目 {project_name} 的 Jenkins 配置验证通过")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"📝 开始触发 Jenkins 构建 - 工作流ID: {workflow_id}")
            
            # 验证服务与 hash 数量是否一致
            if len(services) != len(hashes):
                error_msg = f"服务数量 ({len(services)}) 与 hash 数量 ({len(hashes)}) 不一致，无法触发 Jenkins 构建"
                logger.error(f"❌ {error_msg} - 工作流ID: {workflow_id}")
                raise ValueError(error_msg)
            
            logger.info(f"✅ 数据验证通过，将为 {len(services)} 个服务触发 Jenkins 构建")
            
            # 获取项目的 services 配置，找到对应环境的 key
            from workflows.models import WorkflowManager
            options = WorkflowManager.get_project_options()
            project_config = options.get('projects', {}).get(project_name, {})
            services_config = project_config.get('services', {})
            
            # 在 services 字典中查找匹配 environment 的 key（不区分大小写）
            env_key = None
            if isinstance(services_config, dict):
                # 先尝试精确匹配
                if environment in services_config:
                    env_key = environment
                else:
                    # 如果不区分大小写匹配
                    env_lower = environment.lower()
                    for key in services_config.keys():
                        if key.lower() == env_lower:
                            env_key = key
                            break
            
            if not env_key:
                raise ValueError(f"无法在项目的 services 配置中找到环境 '{environment}' 对应的 key")
            
            logger.info(f"   使用 services 配置中的环境 key: {env_key}")
            
            # 使用项目名称初始化 Jenkins 客户端和监控器（会使用该项目的配置和代理）
            jenkins_client = JenkinsClient(project_name)
            monitor = JenkinsMonitor(project_name)
            
            # 为每个服务触发构建
            # 注意：Jenkins Job 名称格式为：services字典的key/服务名（如：uat/pre-eb-web-api）
            # hashes 与 services 一一对应，通过索引获取
            for idx, service_name in enumerate(services):
                # 构建 Jenkins Job 名称：使用 services 字典的 key/服务名
                job_name = f"{env_key}/{service_name}"
                
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"📡 [{idx + 1}/{len(services)}] 触发 Jenkins 构建")
                logger.info(f"   服务名称: {service_name}")
                logger.info(f"   环境: {environment}")
                logger.info(f"   Jenkins Job: {job_name}")
                
                # 获取对应的 Git Hash（与 service 一一对应）
                git_hash = hashes[idx] if idx < len(hashes) else None
                if git_hash:
                    logger.info(f"   🔑 Git Hash: {git_hash}")
                else:
                    logger.warning(f"   ⚠️ 未找到对应的 Git Hash（索引: {idx}）")
                
                # 构建参数
                # 注意：参数名需要与 Jenkins Job 配置的参数名一致
                build_parameters = {
                    'action_type': 'gray',  # 固定值：gray
                    'gitBranch': branch,    # 分支（从用户输入获取，默认 uat-ebpay）
                }
                
                # 添加 Git Hash（Jenkins 参数名：check_commitID）
                if git_hash:
                    build_parameters['check_commitID'] = git_hash
                else:
                    logger.warning(f"⚠️ 未找到 Git Hash，Jenkins 构建可能失败 - Job: {job_name}")
                
                logger.info(f"   🌿 分支: {branch}")
                
                # 可选：添加其他信息参数（如果 Jenkins Job 需要）
                # build_parameters['WORKFLOW_ID'] = workflow_id
                # build_parameters['PROJECT'] = project_name
                # build_parameters['ENVIRONMENT'] = environment
                # build_parameters['SERVICE'] = service_name
                # build_parameters['APPROVER'] = approver_username
                
                # 触发构建
                build_result = await asyncio.to_thread(
                    jenkins_client.trigger_build,
                    job_name=job_name,
                    parameters=build_parameters
                )
                
                queue_id = build_result.get('queue_id')
                next_build_number = build_result.get('next_build_number')
                logger.info(f"✅ Jenkins 构建已触发 - Job: {job_name}, Queue ID: {queue_id}, 下一个构建号: {next_build_number}")
                
                # 等待构建开始并获取构建编号
                if queue_id or next_build_number:
                    build_number = await asyncio.to_thread(
                        jenkins_client.wait_for_build_to_start,
                        job_name=job_name,
                        queue_id=queue_id,
                        next_build_number=next_build_number,
                        timeout=60
                    )
                    
                    if build_number:
                        logger.info(f"✅ 构建已开始 - Job: {job_name}, Build: #{build_number}")
                        
                        # 创建构建记录
                        build_record = await asyncio.to_thread(
                            WorkflowManager.create_jenkins_build,
                            workflow_id=workflow_id,
                            job_name=job_name,
                            build_number=build_number,
                            job_url=build_result.get('job_url'),
                            build_status='BUILDING',
                            build_parameters=build_parameters
                        )
                        
                        # 不发送构建开始通知，只等待构建完成后发送结果通知
                        # 启动构建状态监控任务（在后台运行，不阻塞）
                        logger.info(f"🔍 启动构建状态监控任务...")
                        asyncio.create_task(
                            monitor.monitor_build(
                                workflow_id=workflow_id,
                                job_name=job_name,
                                build_number=build_number,
                                context=context
                            )
                        )
                        logger.info(f"✅ 已启动构建监控任务（后台运行）")
                    else:
                        logger.warning(f"⚠️ 等待构建开始超时 - Job: {job_name}, Queue ID: {queue_id}")
                else:
                    logger.warning(f"⚠️ 未获取到 Queue ID - Job: {job_name}")
            
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"✅ Jenkins 构建流程全部完成！")
            logger.info(f"   工作流ID: {workflow_id}")
            logger.info(f"   成功触发构建数: {len(services)} 个")
            logger.info(f"   构建任务已在后台运行，完成后将自动通知")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
        except Exception as e:
            logger.error(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error(f"❌ Jenkins 构建触发失败 - 工作流ID: {workflow_id}")
            logger.error(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误信息: {str(e)}")
            logger.error(f"详细错误:", exc_info=True)
            
            logger.warning(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.warning(f"⚠️ Jenkins 构建触发失败，但审批流程已完成")
            logger.warning(f"   工作流ID: {workflow_id}")
            logger.warning(f"   审批流程不受影响，工作流状态已更新为 'approved'")
            logger.warning(f"   Jenkins 错误已记录在日志中，不向用户发送失败通知")
            logger.warning(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

