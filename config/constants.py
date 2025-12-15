"""常量定义"""

# 工作流状态
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

# 审批操作
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"

# 对话状态（用于ConversationHandler）
(
    WAITING_FOR_SUBMISSION,
    WAITING_FOR_CONFIRMATION,
    # 表单状态
    SELECTING_PROJECT,
    SELECTING_ENVIRONMENT,
    SELECTING_SERVICE,
    INPUTTING_ADDRESS,
    INPUTTING_HASH,
    INPUTTING_BRANCH,
    INPUTTING_CONTENT,
    CONFIRMING_FORM,
) = range(10)

# 提交确认操作
ACTION_CONFIRM_SUBMIT = "confirm_submit"
ACTION_CANCEL_SUBMIT = "cancel_submit"

# 表单选择操作
ACTION_SELECT_PROJECT = "select_project"
ACTION_SELECT_ENV = "select_env"
ACTION_SELECT_SERVICE = "select_service"
ACTION_SERVICE_PAGE = "service_page"  # 服务分页导航
ACTION_CONFIRM_SERVICE_SELECTION = "confirm_service_selection"
ACTION_CONFIRM_FORM = "confirm_form"
ACTION_CANCEL_FORM = "cancel_form"

# 消息模板
WORKFLOW_MESSAGE_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━
📋 工作流审批请求
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: `{workflow_id}`
👤 提交人: @{username}
📅 提交时间: {created_at}

━━━━━━━━━━━━━━━━━━━━
📝 申请详情
━━━━━━━━━━━━━━━━━━━━

{submission_data}

━━━━━━━━━━━━━━━━━━━━
⏳ 状态: {status}
━━━━━━━━━━━━━━━━━━━━

{approver_username} 请审批"""

WORKFLOW_APPROVED_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━
✅ 工作流已通过
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: `{workflow_id}`
👤 提交人: @{username}
✅ 审批人: @{approver_username}
📅 审批时间: {approval_time}

━━━━━━━━━━━━━━━━━━━━
📝 申请详情
━━━━━━━━━━━━━━━━━━━━

{submission_data}

━━━━━━━━━━━━━━━━━━━━
🚀 正在提交到 SSO 系统
━━━━━━━━━━━━━━━━━━━━"""

WORKFLOW_REJECTED_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━
❌ 工作流已拒绝
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: {workflow_id}
👤 提交人: @{username}
❌ 审批人: @{approver_username}
📅 审批时间: {approval_time}

申请发版服务
{submission_data}

💬 审批意见: {approval_comment}"""

# 地址类项目默认模板（仅作为数据库缺省回退使用）
WORKFLOW_MESSAGE_TEMPLATE_ADDRESS = """━━━━━━━━━━━━━━━━━━━━
📋 链接节点地址审批请求
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: `{workflow_id}`
👤 提交人: @{username}
📅 提交时间: {created_at}

━━━━━━━━━━━━━━━━━━━━
📝 申请新增地址
━━━━━━━━━━━━━━━━━━━━

{submission_data}

━━━━━━━━━━━━━━━━━━━━
⏳ 状态: {status}
━━━━━━━━━━━━━━━━━━━━

{approver_username} 请审批"""

WORKFLOW_APPROVED_TEMPLATE_ADDRESS = """━━━━━━━━━━━━━━━━━━━━
✅ 链接节点地址已通过
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: `{workflow_id}`
👤 提交人: @{username}
✅ 审批人: @{approver_username}
📅 审批时间: {approval_time}

━━━━━━━━━━━━━━━━━━━━
📝 申请新增地址
━━━━━━━━━━━━━━━━━━━━

{submission_data}
"""

WORKFLOW_REJECTED_TEMPLATE_ADDRESS = """━━━━━━━━━━━━━━━━━━━━
❌ 链接节点地址已拒绝
━━━━━━━━━━━━━━━━━━━━

🆔 工作流ID: {workflow_id}
👤 提交人: @{username}
❌ 审批人: @{approver_username}
📅 审批时间: {approval_time}

申请新增地址
{submission_data}

💬 审批意见: {approval_comment}"""

