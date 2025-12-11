"""表单处理器 - 用于多步骤表单输入"""
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config.constants import (
    SELECTING_PROJECT,
    SELECTING_ENVIRONMENT,
    SELECTING_SERVICE,
    INPUTTING_HASH,
    INPUTTING_ADDRESS,
    INPUTTING_BRANCH,
    INPUTTING_CONTENT,
    CONFIRMING_FORM,
    ACTION_SELECT_PROJECT,
    ACTION_SELECT_ENV,
    ACTION_SELECT_SERVICE,
    ACTION_SERVICE_PAGE,
    ACTION_CONFIRM_SERVICE_SELECTION,
    ACTION_CONFIRM_FORM,
    ACTION_CANCEL_FORM,
)
from config.settings import Settings
from handlers.submission_handler import SubmissionHandler
from utils.logger import setup_logger
from utils.helpers import reply_or_edit

logger = setup_logger(__name__)


class FormHandler:
    """表单处理器"""

    @staticmethod
    def _is_address_only(project: str) -> bool:
        """从配置判断项目是否为仅地址输入流程"""
        if not project:
            return False
        options = Settings.load_options()
        return bool(options.get("projects", {}).get(project, {}).get("address_only"))
    
    @staticmethod
    async def _get_default_branch(project: str = None, environment: str = None) -> str:
        """获取默认分支（从配置中读取，支持按环境区分）"""
        if project:
            return await asyncio.to_thread(Settings.get_default_branch, project, environment, "main")
        return "main"  # 如果没有项目，返回通用默认值
    
    @staticmethod
    async def _init_form_data(context: ContextTypes.DEFAULT_TYPE):
        """初始化表单数据"""
        if 'form_data' not in context.user_data:
            # 获取项目名称，用于获取默认分支
            project = context.user_data.get('project_name') or context.user_data.get('form_data', {}).get('project')
            default_branch = await FormHandler._get_default_branch(project) if project else "main"
            
            context.user_data['form_data'] = {
                'apply_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'project': None,
                'environment': None,
                'services': [],
                'address': [],
                'hash': None,
                'branch': default_branch,  # 从配置中获取默认分支
                'content': None,
                'template_type': context.user_data.get('template_type') or "default",
            }
        return context.user_data['form_data']
    
    @staticmethod
    async def _format_submission_data(form_data: dict) -> str:
        """格式化提交数据"""
        services_text = ", ".join(form_data.get('services', []))
        address_list = form_data.get('address') or []
        address_text = "\n".join(address_list) if address_list else "无"
        # 对于链接节点地址项目，如果未提供 hash/content，填充占位
        hash_val = form_data.get('hash') or "-"
        content_val = form_data.get('content') or "-"
        # 如果分支为空，从配置中获取默认分支
        branch_text = form_data.get('branch')
        if not branch_text:
            project = form_data.get('project')
            environment = form_data.get('environment')
            branch_text = await FormHandler._get_default_branch(project, environment) if project else "main"

        # 特例：链接节点地址项目仅展示地址相关信息（不展示分支/服务/hash/content）
        if FormHandler._is_address_only(form_data.get('project')):
            return (
                f"申请时间: {form_data['apply_time']}\n"
                f"申请项目: {form_data['project']}\n"
                f"申请环境: {form_data['environment']}\n"
                f"申请新增地址:\n{address_text}"
            )

        return (
            f"申请时间: {form_data['apply_time']}\n"
            f"申请项目: {form_data['project']}\n"
            f"申请环境: {form_data['environment']}\n"
            f"申请发版分支: {branch_text}\n"
            f"申请部署服务: {services_text}\n"
            f"申请链路地址: {address_text}\n"
            f"申请发版hash: {hash_val}\n"
            f"申请发版服务内容: {content_val}"
        )

    @staticmethod
    def _auto_select_service(project: str, environment: str) -> list:
        """
        针对“链接节点地址”项目：如果 services 中只有 uat key，按环境返回对应服务
        TRC -> 数组索引0，ETH -> 数组索引1
        """
        if not project or not environment:
            return []
        options = Settings.load_options()
        project_cfg = options.get("projects", {}).get(project, {})
        services_cfg = project_cfg.get("services", {})
        if not isinstance(services_cfg, dict):
            return []
        # 优先精确/不区分大小写匹配
        env_key = None
        if environment in services_cfg:
            env_key = environment
        else:
            env_lower = environment.lower()
            for k in services_cfg.keys():
                if k.lower() == env_lower:
                    env_key = k
                    break
        if env_key:
            val = services_cfg.get(env_key, [])
            return val if isinstance(val, list) else []
        # fallback: 使用 uat key
        uat_val = services_cfg.get("uat") or services_cfg.get("UAT")
        if isinstance(uat_val, list):
            idx = 0 if environment.lower() == "trc" else 1 if environment.lower() == "eth" else 0
            if idx < len(uat_val):
                return [uat_val[idx]]
        return []
    
    @staticmethod
    async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE, project_name: str = None):
        """开始表单流程"""
        try:
            # 如果从命令中指定了项目，使用指定的项目；否则从 context 中获取
            if project_name is None:
                project_name = context.user_data.get('project_name')
            
            logger.info(f"收到部署命令，用户ID: {update.effective_user.id}, 项目: {project_name or '未指定'}")
            
            # 初始化表单数据
            form_data = await FormHandler._init_form_data(context)
            apply_time = form_data['apply_time']
            
            # 如果命令中指定了项目，直接设置项目并跳过项目选择
            if project_name:
                # 验证项目是否存在
                projects = await asyncio.to_thread(Settings.get_projects)
                if project_name not in projects:
                    error_msg = f"❌ 项目 {project_name} 不存在，请联系管理员"
                    await update.message.reply_text(error_msg)
                    logger.error(f"项目 {project_name} 不存在")
                    return ConversationHandler.END
                
                # 设置项目
                form_data['project'] = project_name
                template_type = "address_only" if FormHandler._is_address_only(project_name) else "default"
                context.user_data['template_type'] = template_type
                form_data['template_type'] = template_type
                logger.info(f"用户 {update.effective_user.id} 通过命令指定项目: {project_name}，申请时间: {apply_time}")
                
                # 直接显示环境选择界面（跳过项目选择）
                result = await FormHandler.show_environment_selection(update, context)
                logger.debug(f"命令处理完成，返回状态: {result}")
                return result
            else:
                # 未指定项目，显示项目选择界面
                logger.info(f"用户 {update.effective_user.id} 开始填写表单，申请时间: {apply_time}")
                result = await FormHandler.show_project_selection(update, context, None)
                logger.debug(f"命令处理完成，返回状态: {result}")
                return result
        except Exception as e:
            logger.error(f"启动表单流程时发生错误: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 启动表单失败: {str(e)}")
            return ConversationHandler.END
    
    @staticmethod
    async def show_project_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, loading_msg_id: int = None):
        """显示项目选择"""
        try:
            form_data = context.user_data.get('form_data', {})
            apply_time = form_data.get('apply_time', 'N/A')
            
            # 获取项目列表
            projects = await asyncio.to_thread(Settings.get_projects)
            logger.debug(f"获取项目列表: {projects}")
            
            if not projects:
                error_msg = "❌ 未配置项目列表，请联系管理员"
                await reply_or_edit(update, error_msg)
                logger.error("项目列表未配置")
                return ConversationHandler.END
            
            keyboard = []
            # 每行显示2个按钮
            for i in range(0, len(projects), 2):
                row = []
                row.append(InlineKeyboardButton(
                    projects[i],
                    callback_data=f"{ACTION_SELECT_PROJECT}:{projects[i]}"
                ))
                if i + 1 < len(projects):
                    row.append(InlineKeyboardButton(
                        projects[i + 1],
                        callback_data=f"{ACTION_SELECT_PROJECT}:{projects[i + 1]}"
                    ))
                keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = "📋 申请测试环境服务发版\n\n" \
                     f"✅ 申请时间: {apply_time}\n" \
                     f"⏳ 申请项目: 请选择"
            
            # 显示项目选择界面
            await reply_or_edit(update, message, reply_markup=reply_markup)
            logger.debug(f"项目选择界面已显示，返回状态: SELECTING_PROJECT")
            return SELECTING_PROJECT
            
        except Exception as e:
            logger.error(f"显示项目选择时发生错误: {str(e)}", exc_info=True)
            await reply_or_edit(update, f"❌ 显示项目选择失败: {str(e)}")
            return ConversationHandler.END
    
    @staticmethod
    async def handle_project_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理项目选择"""
        query = update.callback_query
        await query.answer()
        
        project = query.data.split(":", 1)[1]
        context.user_data['form_data']['project'] = project
        template_type = "address_only" if FormHandler._is_address_only(project) else "default"
        context.user_data['template_type'] = template_type
        context.user_data['form_data']['template_type'] = template_type
        
        logger.info(f"用户 {query.from_user.id} 选择项目: {project}")
        
        # 显示环境选择
        return await FormHandler.show_environment_selection(update, context)
    
    @staticmethod
    async def show_environment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示环境选择"""
        form_data = context.user_data.get('form_data', {})
        project = form_data.get('project')
        
        if not project:
            error_msg = "❌ 未选择项目"
            await reply_or_edit(update, error_msg)
            logger.error("未选择项目")
            return ConversationHandler.END
        
        # 根据项目获取环境列表（在线程池中执行，避免阻塞）
        environments = await asyncio.to_thread(Settings.get_environments, project)
        if not environments:
            error_msg = f"❌ 项目 {project} 未配置环境列表，请联系管理员"
            await reply_or_edit(update, error_msg)
            logger.error(f"项目 {project} 环境列表未配置")
            return ConversationHandler.END
        
        keyboard = []
        for i in range(0, len(environments), 2):
            row = []
            row.append(InlineKeyboardButton(
                environments[i],
                callback_data=f"{ACTION_SELECT_ENV}:{environments[i]}"
            ))
            if i + 1 < len(environments):
                row.append(InlineKeyboardButton(
                    environments[i + 1],
                    callback_data=f"{ACTION_SELECT_ENV}:{environments[i + 1]}"
                ))
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        form_data = context.user_data['form_data']
        message = "📋 申请测试环境服务发版\n\n" \
                 f"✅ 申请时间: {form_data['apply_time']}\n" \
                 f"✅ 申请项目: {form_data['project']}\n" \
                 f"⏳ 申请环境: 请选择"
        
        # 使用 reply_or_edit 以支持 callback_query 和 message 两种情况
        await reply_or_edit(update, message, reply_markup=reply_markup)
        
        return SELECTING_ENVIRONMENT
    
    @staticmethod
    async def handle_environment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理环境选择"""
        query = update.callback_query
        await query.answer()
        
        environment = query.data.split(":", 1)[1]
        context.user_data['form_data']['environment'] = environment
        
        logger.info(f"用户 {query.from_user.id} 选择环境: {environment}")
        
        # 清空之前选择的服务（切换环境时重置）
        if 'form_data' in context.user_data:
            context.user_data['form_data']['services'] = []
        
        project = context.user_data['form_data'].get('project')
        # 设置默认分支；address_only 项目分支填占位
        if FormHandler._is_address_only(project):
            context.user_data['form_data']['branch'] = "-"
        else:
            default_branch = await FormHandler._get_default_branch(project, environment)
            context.user_data['form_data']['branch'] = default_branch
        # 针对 address_only 项目：自动选择服务并进入地址输入
        if FormHandler._is_address_only(project):
            auto_services = FormHandler._auto_select_service(project, environment)
            if auto_services:
                context.user_data['form_data']['services'] = auto_services
            return await FormHandler.show_address_input(update, context)
        
        # 其他项目仍按原流程：分支->服务选择
        return await FormHandler.show_branch_input(update, context)

    @staticmethod
    async def show_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示地址输入界面（TRC/ETH 都需要输入，每行一个地址）"""
        form_data = context.user_data.get('form_data', {})
        services_text = ", ".join(form_data.get('services', [])) if form_data.get('services') else "默认服务"
        branch_text = form_data.get('branch') or "main"
        if FormHandler._is_address_only(form_data.get('project')):
            message = (
                "📋 申请测试环境服务发版\n\n"
                f"✅ 申请时间: {form_data.get('apply_time')}\n"
                f"✅ 申请项目: {form_data.get('project')}\n"
                f"✅ 申请环境: {form_data.get('environment')}\n"
                "⏳ 请输入地址（每行一个，多行代表多个地址，勿用逗号）："
            )
        else:
            message = (
                "📋 申请测试环境服务发版\n\n"
                f"✅ 申请时间: {form_data.get('apply_time')}\n"
                f"✅ 申请项目: {form_data.get('project')}\n"
                f"✅ 申请环境: {form_data.get('environment')}\n"
                f"✅ 申请发版分支: {branch_text}\n"
                f"✅ 申请部署服务: {services_text}\n"
                "⏳ 请输入地址（每行一个，多行代表多个地址，勿用逗号）："
            )
        await reply_or_edit(update, message)
        return INPUTTING_ADDRESS

    @staticmethod
    async def handle_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理地址输入（按换行分割）"""
        if not update.message or not update.message.text:
            await update.message.reply_text("❌ 请输入地址，每行一个，勿用逗号")
            return INPUTTING_ADDRESS
        raw = update.message.text.strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not lines:
            await update.message.reply_text("❌ 地址不能为空，请每行一个重新输入")
            return INPUTTING_ADDRESS
        await FormHandler._init_form_data(context)
        context.user_data['form_data']['address'] = lines
        # 链接节点地址项目：地址后直接进入确认（不需要 hash / 内容）
        project = context.user_data['form_data'].get('project')
        if FormHandler._is_address_only(project):
            context.user_data['form_data'].setdefault('hash', "-")
            context.user_data['form_data'].setdefault('content', "-")
            return await FormHandler.show_confirmation(update, context)
        # 其他项目保持原流程
        return await FormHandler._proceed_to_hash_input(update, context)

    @staticmethod
    async def _proceed_to_hash_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """跳转到 Hash 输入步骤（跳过服务选择/分支输入界面）"""
        form_data = context.user_data.get('form_data', {})
        services_text = ", ".join(form_data.get('services', [])) if form_data.get('services') else "默认服务"
        branch_text = form_data.get('branch') or "main"
        message = (
            "📋 申请测试环境服务发版\n\n"
            f"✅ 申请时间: {form_data.get('apply_time')}\n"
            f"✅ 申请项目: {form_data.get('project')}\n"
            f"✅ 申请环境: {form_data.get('environment')}\n"
            f"✅ 申请发版分支: {branch_text}\n"
            f"✅ 申请部署服务: {services_text}\n"
            f"⏳ 申请发版hash: 请输入（仅单个hash，不支持逗号分隔）"
        )
        await reply_or_edit(update, message)
        return INPUTTING_HASH
    
    @staticmethod
    async def show_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示服务选择（每行1个按钮，确保完整显示服务名称）"""
        form_data = context.user_data.get('form_data', {})
        project = form_data.get('project')
        environment = form_data.get('environment')
        
        if not project:
            error_msg = "❌ 未选择项目"
            await reply_or_edit(update, error_msg)
            logger.error("未选择项目")
            return ConversationHandler.END
        
        if not environment:
            error_msg = "❌ 未选择环境"
            await reply_or_edit(update, error_msg)
            logger.error("未选择环境")
            return ConversationHandler.END
        
        # 根据项目和环境获取服务列表（在线程池中执行，避免阻塞）
        services = await asyncio.to_thread(lambda: Settings.get_services(project, environment))
        if not services:
            error_msg = f"❌ 项目 {project} 在 {environment} 环境下未配置服务列表，请联系管理员"
            await reply_or_edit(update, error_msg)
            logger.error(f"项目 {project} 在 {environment} 环境下服务列表未配置")
            return ConversationHandler.END
        
        # 获取已选择的服务（确保是列表类型，并清空无效数据）
        selected_services = context.user_data['form_data'].get('services', [])
        if not isinstance(selected_services, list):
            selected_services = []
            context.user_data['form_data']['services'] = []
        
        # 确保已选择的服务都在当前服务列表中（过滤掉无效的服务）
        selected_services = [s for s in selected_services if s in services]
        context.user_data['form_data']['services'] = selected_services
        
        # 构建按钮键盘（每行显示1个按钮，确保完整显示服务名称）
        keyboard = []
        for service in services:
            # 如果已选择，显示 ✓ 标记
            is_selected = service in selected_services
            
            # 按钮文本：✓ 服务名 或 服务名（完整显示）
            if is_selected:
                btn_text = f"✓ {service}"
            else:
                btn_text = service
            
            # 每个服务独占一行，确保按钮足够宽，可以完整显示服务名称
            keyboard.append([
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"{ACTION_SELECT_SERVICE}:{service}"
                )
            ])
        
        # 添加"完成选择"按钮
        keyboard.append([
            InlineKeyboardButton("✅ 完成选择", callback_data=ACTION_CONFIRM_SERVICE_SELECTION)
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 构建消息文本
        selected_text = ", ".join(selected_services) if selected_services else "未选择"
        # 从配置中获取默认分支
        branch_text = form_data.get('branch')
        if not branch_text:
            environment = form_data.get('environment')
            branch_text = await FormHandler._get_default_branch(project, environment)
        
        message = "📋 申请测试环境服务发版\n\n" \
                 f"✅ 申请时间: {form_data['apply_time']}\n" \
                 f"✅ 申请项目: {form_data['project']}\n" \
                 f"✅ 申请环境: {form_data['environment']}\n" \
                 f"✅ 申请发版分支: {branch_text}\n" \
                 f"⏳ 申请部署服务: {selected_text}\n\n" \
                 f"💡 可多选，再次点击可取消选择"
        
        # 使用 reply_or_edit 以支持 callback_query 和 message 两种情况
        await reply_or_edit(update, message, reply_markup=reply_markup)
        
        return SELECTING_SERVICE
    
    @staticmethod
    async def handle_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理服务选择（支持多选）"""
        query = update.callback_query
        await query.answer()
        
        # 检查是否是完成选择按钮
        if query.data == ACTION_CONFIRM_SERVICE_SELECTION:
            selected_services = context.user_data['form_data'].get('services', [])
            if not selected_services:
                await query.answer("请至少选择一个服务", show_alert=True)
                return SELECTING_SERVICE
            
            form_data = context.user_data['form_data']
            services_text = ", ".join(selected_services)
            # 从配置中获取默认分支
            branch_text = form_data.get('branch')
            if not branch_text:
                project = form_data.get('project')
                environment = form_data.get('environment')
                branch_text = await FormHandler._get_default_branch(project, environment) if project else "main"
            # 链接节点地址项目：无需 hash，直接确认
            if FormHandler._is_address_only(form_data.get('project')):
                form_data.setdefault('hash', "-")
                form_data.setdefault('content', "-")
                return await FormHandler.show_confirmation(update, context)
            message = "📋 申请测试环境服务发版\n\n" \
                     f"✅ 申请时间: {form_data['apply_time']}\n" \
                     f"✅ 申请项目: {form_data['project']}\n" \
                     f"✅ 申请环境: {form_data['environment']}\n" \
                     f"✅ 申请发版分支: {branch_text}\n" \
                     f"✅ 申请部署服务: {services_text}\n" \
                     f"⏳ 申请发版hash: 请输入（仅单个hash，不支持逗号分隔）"
            
            await query.edit_message_text(message)
            logger.info(f"用户 {query.from_user.id} 完成服务选择: {selected_services}")
            return INPUTTING_HASH
        
        # 处理单个服务的选择/取消
        service = query.data.split(":", 1)[1]
        services = context.user_data['form_data'].get('services', [])
        
        if service in services:
            # 取消选择
            services.remove(service)
            logger.info(f"用户 {query.from_user.id} 取消选择服务: {service}")
        else:
            # 添加选择
            services.append(service)
            logger.info(f"用户 {query.from_user.id} 选择服务: {service}")
        
        context.user_data['form_data']['services'] = services
        
        # 刷新服务选择界面
        return await FormHandler.show_service_selection(update, context)
    
    @staticmethod
    async def handle_hash_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理hash输入"""
        try:
            logger.info(f"=== handle_hash_input 被调用 ===")
            logger.info(f"收到hash输入，用户ID: {update.effective_user.id}")
            logger.info(f"update类型: {type(update)}")
            logger.info(f"update.message: {update.message}")
            logger.info(f"context.user_data: {context.user_data}")
            
            # 检查是否有消息
            if not update.message:
                logger.error("update.message 为空")
                return INPUTTING_HASH
            
            # 检查是否有文本内容
            if not update.message.text:
                logger.error(f"消息格式错误，没有文本内容。消息类型: {update.message.content_type}")
                await update.message.reply_text("❌ 请输入有效的hash值（文本格式）")
                return INPUTTING_HASH
            
            hash_value = update.message.text.strip()
            logger.info(f"用户 {update.effective_user.id} 输入hash: {hash_value}")
            
            if not hash_value:
                await update.message.reply_text("❌ hash不能为空，请重新输入")
                return INPUTTING_HASH
            
            # 不支持多个hash，若包含逗号提示重输
            if ',' in hash_value or '，' in hash_value or '、' in hash_value:
                await update.message.reply_text("❌ 仅支持单个hash，请不要使用逗号分隔多个hash")
                return INPUTTING_HASH
            
            # 确保表单数据已初始化
            await FormHandler._init_form_data(context)
            context.user_data['form_data']['hash'] = hash_value
            logger.info(f"hash已保存: {hash_value}, 完整表单数据: {context.user_data['form_data']}")
            
            # 显示输入发版内容界面（hash 输入后直接到内容输入）
            logger.info("准备显示输入发版内容界面")
            result = await FormHandler.show_content_input(update, context)
            logger.info(f"输入发版内容界面已显示，返回状态: {result}")
            return result
        except Exception as e:
            logger.error(f"处理hash输入时发生错误: {str(e)}", exc_info=True)
            if update.message:
                await update.message.reply_text(f"❌ 处理输入失败: {str(e)}")
            return INPUTTING_HASH
    
    @staticmethod
    async def show_branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示输入分支界面"""
        try:
            form_data = context.user_data.get('form_data', {})
            project = form_data.get('project')
            environment = form_data.get('environment')
            # 从配置中获取默认分支（根据环境）
            default_branch = await FormHandler._get_default_branch(project, environment) if project else "main"
            branch_text = form_data.get('branch', default_branch)
            
            # 创建键盘，提供默认选项和自定义输入
            keyboard = [
                [
                    InlineKeyboardButton(f"✅ 使用默认: {default_branch}", callback_data="branch:default")
                ],
                [
                    InlineKeyboardButton("✏️ 自定义输入", callback_data="branch:custom")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = "📋 申请测试环境服务发版\n\n" \
                     f"✅ 申请时间: {form_data.get('apply_time', 'N/A')}\n" \
                     f"✅ 申请项目: {form_data.get('project', 'N/A')}\n" \
                     f"✅ 申请环境: {form_data.get('environment', 'N/A')}\n" \
                     f"⏳ 申请发版分支: {branch_text}\n\n" \
                     f"💡 选择默认分支或点击自定义输入"
            
            await reply_or_edit(update, message, reply_markup=reply_markup)
            
            logger.info("输入分支界面已显示")
            return INPUTTING_BRANCH
        except Exception as e:
            logger.error(f"显示输入分支界面时发生错误: {str(e)}", exc_info=True)
            await reply_or_edit(update, f"❌ 显示输入界面失败: {str(e)}")
            return ConversationHandler.END
    
    @staticmethod
    async def handle_branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理分支输入"""
        try:
            # 检查是否是回调查询（选择默认分支）
            if update.callback_query:
                query = update.callback_query
                await query.answer()
                
                if query.data == "branch:default":
                    # 使用默认分支
                    await FormHandler._init_form_data(context)
                    form_data = context.user_data['form_data']
                    project = form_data.get('project')
                    environment = form_data.get('environment')
                    default_branch = await FormHandler._get_default_branch(project, environment) if project else "main"
                    context.user_data['form_data']['branch'] = default_branch
                    logger.info(f"用户 {query.from_user.id} 选择默认分支: {default_branch}")
                    
                    # 显示服务选择界面
                    return await FormHandler.show_service_selection(update, context)
                elif query.data == "branch:custom":
                    # 提示用户输入自定义分支
                    form_data = context.user_data.get('form_data', {})
                    message = "📋 申请测试环境服务发版\n\n" \
                             f"✅ 申请时间: {form_data.get('apply_time', 'N/A')}\n" \
                             f"✅ 申请项目: {form_data.get('project', 'N/A')}\n" \
                             f"✅ 申请环境: {form_data.get('environment', 'N/A')}\n" \
                             f"⏳ 申请发版分支: 请输入\n\n" \
                             f"💡 请在下方输入框中直接输入分支名称，然后发送"
                    
                    await query.edit_message_text(message)
                    return INPUTTING_BRANCH
                else:
                    return INPUTTING_BRANCH
            
            # 处理文本输入（自定义分支）
            if not update.message or not update.message.text:
                logger.error("消息格式错误，没有文本内容")
                await update.message.reply_text("❌ 请输入有效的分支名称（文本格式）")
                return INPUTTING_BRANCH
            
            branch_value = update.message.text.strip()
            logger.info(f"用户 {update.message.from_user.id} 输入分支: {branch_value}")
            
            if not branch_value:
                await update.message.reply_text("❌ 分支名称不能为空，请重新输入")
                return INPUTTING_BRANCH
            
            # 确保表单数据已初始化
            await FormHandler._init_form_data(context)
            context.user_data['form_data']['branch'] = branch_value
            logger.info(f"分支已保存: {branch_value}, 完整表单数据: {context.user_data['form_data']}")
            
            # 显示服务选择界面
            logger.info("准备显示服务选择界面")
            result = await FormHandler.show_service_selection(update, context)
            logger.info(f"服务选择界面已显示，返回状态: {result}")
            return result
        except Exception as e:
            logger.error(f"处理分支输入时发生错误: {str(e)}", exc_info=True)
            if update.message:
                await update.message.reply_text(f"❌ 处理输入失败: {str(e)}")
            return INPUTTING_BRANCH
    
    @staticmethod
    async def show_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示输入发版内容界面"""
        try:
            form_data = context.user_data.get('form_data', {})
            services_text = ", ".join(form_data.get('services', [])) if form_data.get('services') else "未选择"
            hash_text = form_data.get('hash', 'N/A')
            # 从配置中获取默认分支
            branch_text = form_data.get('branch')
            if not branch_text:
                project = form_data.get('project')
                environment = form_data.get('environment')
                branch_text = await FormHandler._get_default_branch(project, environment) if project else "main"
            message = "📋 申请测试环境服务发版\n\n" \
                     f"✅ 申请时间: {form_data.get('apply_time', 'N/A')}\n" \
                     f"✅ 申请项目: {form_data.get('project', 'N/A')}\n" \
                     f"✅ 申请环境: {form_data.get('environment', 'N/A')}\n" \
                     f"✅ 申请发版分支: {branch_text}\n" \
                     f"✅ 申请部署服务: {services_text}\n" \
                     f"✅ 申请发版hash: {hash_text}\n" \
                     f"⏳ 申请发版服务内容: 请输入\n\n" \
                     f"💡 请在下方输入框中直接输入发版内容，然后发送"
            
            await reply_or_edit(update, message)
            
            logger.info("输入发版内容界面已显示")
            return INPUTTING_CONTENT
        except Exception as e:
            logger.error(f"显示输入发版内容界面时发生错误: {str(e)}", exc_info=True)
            await reply_or_edit(update, f"❌ 显示输入界面失败: {str(e)}")
            return ConversationHandler.END
    
    @staticmethod
    async def handle_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理发版内容输入"""
        try:
            logger.info(f"收到发版内容输入，用户ID: {update.effective_user.id}")
            
            if not update.message or not update.message.text:
                logger.error("消息格式错误，没有文本内容")
                await update.message.reply_text("❌ 请输入有效的发版内容（文本格式）")
                return INPUTTING_CONTENT
            
            content_value = update.message.text.strip()
            logger.info(f"用户 {update.effective_user.id} 输入发版内容: {content_value}")
            
            if not content_value:
                await update.message.reply_text("❌ 发版内容不能为空，请重新输入")
                return INPUTTING_CONTENT
            
            # 确保表单数据已初始化
            await FormHandler._init_form_data(context)
            context.user_data['form_data']['content'] = content_value
            logger.info(f"发版内容已保存: {content_value}, 完整表单数据: {context.user_data['form_data']}")
            
            # 显示确认界面
            logger.info("准备显示确认界面")
            result = await FormHandler.show_confirmation(update, context)
            logger.info(f"确认界面已显示，返回状态: {result}")
            return result
        except Exception as e:
            logger.error(f"处理发版内容输入时发生错误: {str(e)}", exc_info=True)
            if update.message:
                await update.message.reply_text(f"❌ 处理输入失败: {str(e)}")
            return INPUTTING_CONTENT
    
    @staticmethod
    async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示确认界面"""
        try:
            logger.info("=== show_confirmation 开始 ===")
            logger.info(f"update: {update}")
            logger.info(f"context.user_data: {context.user_data}")
            
            if 'form_data' not in context.user_data:
                logger.error("form_data 不存在")
                await update.message.reply_text("❌ 表单数据丢失，请重新开始")
                return ConversationHandler.END
            
            form_data = context.user_data['form_data']
            logger.info(f"form_data: {form_data}")
            
            # 验证所有必需字段
            services = form_data.get('services', [])
            if not services:
                logger.error("未选择服务")
                await update.message.reply_text("❌ 请至少选择一个服务")
                return ConversationHandler.END
            
            # 针对“链接节点地址”项目，hash/content 可为空（已填充占位）
            if FormHandler._is_address_only(form_data.get('project')):
                required_fields = ['apply_time', 'project', 'environment', 'branch']
            else:
                required_fields = ['apply_time', 'project', 'environment', 'hash', 'branch', 'content']
            missing_fields = [field for field in required_fields if not form_data.get(field)]
            if missing_fields:
                logger.error(f"缺少必需字段: {missing_fields}")
                await update.message.reply_text(f"❌ 表单数据不完整，缺少: {', '.join(missing_fields)}")
                return ConversationHandler.END
            
            # 格式化提交数据
            submission_data = await FormHandler._format_submission_data(form_data)
            message = "📋 请确认您的申请信息：\n\n" + submission_data
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ 确认提交", callback_data=ACTION_CONFIRM_FORM),
                    InlineKeyboardButton("❌ 取消", callback_data=ACTION_CANCEL_FORM),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.info("准备发送确认消息")
            await update.message.reply_text(message, reply_markup=reply_markup)
            logger.info("确认消息已发送，返回状态 CONFIRMING_FORM")
            
            return CONFIRMING_FORM
        except Exception as e:
            logger.error(f"显示确认界面时发生错误: {str(e)}", exc_info=True)
            if update.message:
                await update.message.reply_text(f"❌ 显示确认界面失败: {str(e)}")
            return ConversationHandler.END
    
    @staticmethod
    async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理确认"""
        query = update.callback_query
        await query.answer()
        
        if query.data == ACTION_CANCEL_FORM:
            await query.edit_message_text("❌ 已取消提交")
            logger.info(f"用户 {query.from_user.id} 取消了表单提交")
            return ConversationHandler.END
        
        if query.data == ACTION_CONFIRM_FORM:
            form_data = context.user_data.get('form_data')
            if not form_data:
                await query.edit_message_text("❌ 表单数据丢失，请重新提交")
                logger.error(f"用户 {query.from_user.id} 确认提交时表单数据丢失")
                return ConversationHandler.END
            
            # 格式化提交数据
            submission_data = await FormHandler._format_submission_data(form_data)
            
            # 更新消息显示"正在提交..."
            await query.edit_message_text("⏳ 正在提交工作流...")
            
            # 处理提交（传递项目信息，用于选择对应的群组）
            success = await SubmissionHandler.handle_submission(
                update=update,
                context=context,
                submission_data=submission_data,
                project=form_data.get('project'),  # 传递项目信息
                template_type=form_data.get('template_type') or context.user_data.get('template_type') or "default",
            )
            
            if success:
                # submission_handler 已经发送了详细的成功消息，这里不需要再编辑
                return ConversationHandler.END
            else:
                await query.edit_message_text("❌ 提交失败，请重试")
                return ConversationHandler.END
        
        return ConversationHandler.END

