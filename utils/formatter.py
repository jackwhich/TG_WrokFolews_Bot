"""消息格式化工具"""
from config.constants import (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    WORKFLOW_MESSAGE_TEMPLATE,
    WORKFLOW_APPROVED_TEMPLATE,
    WORKFLOW_REJECTED_TEMPLATE,
    WORKFLOW_MESSAGE_TEMPLATE_ADDRESS,
    WORKFLOW_APPROVED_TEMPLATE_ADDRESS,
    WORKFLOW_REJECTED_TEMPLATE_ADDRESS,
)


def _resolve_template(template_key: str, default_template: str, project: str = None) -> str:
    """从数据库读取模板，失败时回退默认模板"""
    try:
        from workflows.models import WorkflowManager
        return WorkflowManager.get_message_template(template_key, project=project, default=default_template) or default_template
    except Exception:
        return default_template


def _detect_template_type(workflow_data: dict, fallback: str = "default") -> str:
    """判定模板类型（address_only / default）"""
    tpl_type = workflow_data.get("template_type")
    if tpl_type:
        return tpl_type
    project = workflow_data.get("project")
    if project:
        try:
            from workflows.models import WorkflowManager
            options = WorkflowManager.get_project_options()
            if options.get("projects", {}).get(project, {}).get("address_only"):
                return "address_only"
        except Exception:
            pass
    return fallback


def format_workflow_message(workflow_data: dict, approver_username: str, template_type: str = None) -> str:
    """格式化工作流消息"""
    status_text = {
        STATUS_PENDING: "待审批",
        STATUS_APPROVED: "已通过",
        STATUS_REJECTED: "已拒绝",
    }.get(workflow_data.get("status", STATUS_PENDING), "未知")

    project = workflow_data.get("project")
    tpl_type = template_type or _detect_template_type(workflow_data)
    if tpl_type == "address_only":
        template = _resolve_template("address_only", WORKFLOW_MESSAGE_TEMPLATE_ADDRESS, project=project)
    else:
        template = _resolve_template("default", WORKFLOW_MESSAGE_TEMPLATE, project=project)
    
    return template.format(
        workflow_id=workflow_data.get("workflow_id", "N/A"),
        username=workflow_data.get("username", "N/A"),
        created_at=workflow_data.get("created_at", "N/A"),
        submission_data=format_submission_data(workflow_data.get("submission_data", "")),
        status=status_text,
        approver_username=approver_username,
    )


def format_approval_result(workflow_data: dict, approver_username: str, template_type: str = None) -> str:
    """格式化审批结果消息"""
    status = workflow_data.get("status", STATUS_PENDING)
    project = workflow_data.get("project")
    tpl_type = template_type or _detect_template_type(workflow_data)
    
    if status == STATUS_APPROVED:
        base_template = (
            WORKFLOW_APPROVED_TEMPLATE_ADDRESS if tpl_type == "address_only"
            else WORKFLOW_APPROVED_TEMPLATE
        )
        template_resolved = _resolve_template(
            "approved_address_only" if tpl_type == "address_only" else "approved_default",
            base_template,
            project=project,
        )
        # 移除 "正在提交到 SSO 系统" 这一行（无论 SSO 是否启用都不显示）
        template = template_resolved.replace(
            "\n━━━━━━━━━━━━━━━━━━━━\n🚀 正在提交到 SSO 系统\n━━━━━━━━━━━━━━━━━━━━",
            ""
        )
        
        return template.format(
            workflow_id=workflow_data.get("workflow_id", "N/A"),
            username=workflow_data.get("username", "N/A"),
            approver_username=approver_username,
            approval_time=workflow_data.get("approval_time", "N/A"),
            submission_data=format_submission_data(workflow_data.get("submission_data", "")),
        )
    elif status == STATUS_REJECTED:
        base_template = (
            WORKFLOW_REJECTED_TEMPLATE_ADDRESS if tpl_type == "address_only"
            else WORKFLOW_REJECTED_TEMPLATE
        )
        template = _resolve_template(
            "rejected_address_only" if tpl_type == "address_only" else "rejected_default",
            base_template,
            project=project,
        )
        return template.format(
            workflow_id=workflow_data.get("workflow_id", "N/A"),
            username=workflow_data.get("username", "N/A"),
            approver_username=approver_username,
            approval_time=workflow_data.get("approval_time", "N/A"),
            submission_data=format_submission_data(workflow_data.get("submission_data", "")),
            approval_comment=workflow_data.get("approval_comment", "无"),
        )
    else:
        return format_workflow_message(workflow_data, approver_username)


def format_submission_data(data: str) -> str:
    """格式化提交数据（美化显示）"""
    if not data:
        return "无"
    
    # 如果是JSON字符串，尝试格式化
    try:
        import json
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            formatted = []
            for key, value in parsed.items():
                formatted.append(f"{key}: {value}")
            return "\n".join(formatted)
        return str(parsed)
    except:
        pass
    
    # 尝试解析为结构化数据（使用 SSO 数据解析器）
    try:
        from sso.data_converter import SSODataConverter
        parsed_data = SSODataConverter.parse_tg_submission_data(data)

        # 检查 address_only 配置
        project = parsed_data.get('project')
        is_address_only = False
        if project:
            try:
                from workflows.models import WorkflowManager
                options = WorkflowManager.get_project_options()
                is_address_only = bool(options.get("projects", {}).get(project, {}).get("address_only"))
            except Exception:
                is_address_only = False

        formatted_lines = []

        if parsed_data.get('apply_time'):
            formatted_lines.append(f"🕐 申请时间: {parsed_data['apply_time']}")
        if project:
            formatted_lines.append(f"📦 申请项目: {project}")
        if parsed_data.get('environment'):
            formatted_lines.append(f"🌍 申请环境: {parsed_data['environment']}")

        services = parsed_data.get('services', [])
        hashes = parsed_data.get('hashes', [])

        if is_address_only:
            # 地址列表：优先 hashes，其次 services，若都无则从原始文本抓取“申请新增地址”
            addr_list = hashes or services
            if not addr_list:
                import re
                # 捕获“申请新增地址:”后的多行文本
                m = re.search(r"申请新增地址[：:]\s*(.+)", data, re.S)
                if m:
                    raw_addrs = m.group(1).strip()
                    addr_list = [ln.strip() for ln in raw_addrs.splitlines() if ln.strip()]
            if addr_list:
                formatted_lines.append("🏷 申请新增地址:")
                for addr in addr_list:
                    formatted_lines.append(f"   • {addr}")
            return "\n".join(formatted_lines) if formatted_lines else data

        branch = parsed_data.get('branch')
        if branch:
            formatted_lines.append(f"🌿 申请发版分支: {branch}")

        if hashes:
            if len(hashes) == 1:
                if services and len(services) == 1:
                    formatted_lines.append(f"🚀 申请部署服务: {services[0]}\n🔑 申请发版hash: <b>{hashes[0]}</b>")
                else:
                    formatted_lines.append(f"🔑 申请发版hash: <b>{hashes[0]}</b>")
            else:
                if len(hashes) == len(services) and services:
                    hash_text = "\n   ".join([
                        f"• {services[i]}: <b>{hashes[i]}</b>"
                        for i in range(len(services))
                    ])
                    formatted_lines.append(f"🚀 申请部署服务及hash:\n   {hash_text}")
                else:
                    hash_text = "\n   ".join([f"• <b>{h}</b>" for h in hashes])
                    formatted_lines.append(f"🔑 申请发版hash:\n   {hash_text}")

        if parsed_data.get('content'):
            formatted_lines.append(f"📝 申请发版服务内容: {parsed_data['content']}")

        return "\n".join(formatted_lines) if formatted_lines else data
    except Exception:
        return data

