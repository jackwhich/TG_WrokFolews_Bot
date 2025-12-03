"""消息格式化工具"""
from config.constants import (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    WORKFLOW_MESSAGE_TEMPLATE,
    WORKFLOW_APPROVED_TEMPLATE,
    WORKFLOW_REJECTED_TEMPLATE,
)


def format_workflow_message(workflow_data: dict, approver_username: str) -> str:
    """格式化工作流消息"""
    status_text = {
        STATUS_PENDING: "待审批",
        STATUS_APPROVED: "已通过",
        STATUS_REJECTED: "已拒绝",
    }.get(workflow_data.get("status", STATUS_PENDING), "未知")
    
    return WORKFLOW_MESSAGE_TEMPLATE.format(
        workflow_id=workflow_data.get("workflow_id", "N/A"),
        username=workflow_data.get("username", "N/A"),
        created_at=workflow_data.get("created_at", "N/A"),
        submission_data=format_submission_data(workflow_data.get("submission_data", "")),
        status=status_text,
        approver_username=approver_username,
    )


def format_approval_result(workflow_data: dict, approver_username: str) -> str:
    """格式化审批结果消息"""
    status = workflow_data.get("status", STATUS_PENDING)
    
    if status == STATUS_APPROVED:
        # 移除 "正在提交到 SSO 系统" 这一行（无论 SSO 是否启用都不显示）
        template = WORKFLOW_APPROVED_TEMPLATE.replace(
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
        return WORKFLOW_REJECTED_TEMPLATE.format(
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
        
        formatted_lines = []
        
        # 申请时间
        if parsed_data.get('apply_time'):
            formatted_lines.append(f"🕐 申请时间: {parsed_data['apply_time']}")
        
        # 申请项目
        if parsed_data.get('project'):
            formatted_lines.append(f"📦 申请项目: {parsed_data['project']}")
        
        # 申请环境
        if parsed_data.get('environment'):
            formatted_lines.append(f"🌍 申请环境: {parsed_data['environment']}")
        
        # 申请发版分支
        branch = parsed_data.get('branch', 'uat-ebpay')
        if branch:
            formatted_lines.append(f"🌿 申请发版分支: {branch}")
        
        # 申请发版hash（支持多个hash，与服务对应）
        # 注意：不再单独显示"申请部署服务"，因为hash部分已经显示了服务名称
        services = parsed_data.get('services', [])
        hashes = parsed_data.get('hashes', [])
        if hashes:
            if len(hashes) == 1:
                # 单个hash，如果有服务信息则显示服务名
                if services and len(services) == 1:
                    formatted_lines.append(f"🚀 申请部署服务: {services[0]}\n🔑 申请发版hash: <b>{hashes[0]}</b>")
                else:
                    formatted_lines.append(f"🔑 申请发版hash: <b>{hashes[0]}</b>")
            else:
                # 多个hash，如果与服务数量相同，按对应关系显示（包含服务名）
                if len(hashes) == len(services) and services:
                    hash_text = "\n   ".join([
                        f"• {services[i]}: <b>{hashes[i]}</b>"
                        for i in range(len(services))
                    ])
                    formatted_lines.append(f"🚀 申请部署服务及hash:\n   {hash_text}")
                else:
                    # hash数量与服务数量不一致，只显示hash
                    hash_text = "\n   ".join([f"• <b>{h}</b>" for h in hashes])
                    formatted_lines.append(f"🔑 申请发版hash:\n   {hash_text}")
        
        # 申请发版服务内容
        if parsed_data.get('content'):
            formatted_lines.append(f"📝 申请发版服务内容: {parsed_data['content']}")
        
        if formatted_lines:
            return "\n".join(formatted_lines)
        
        # 如果解析失败，返回原始数据
        return data
    except Exception:
        # 如果解析失败，返回原始数据
        return data

