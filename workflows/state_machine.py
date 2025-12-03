"""工作流状态机"""
from typing import Optional
from utils.helpers import get_current_timestamp
from config.constants import STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED
from .models import WorkflowManager


class WorkflowStateMachine:
    """工作流状态机"""
    
    @staticmethod
    def approve_workflow(
        workflow_id: str,
        approver_id: int,
        approver_username: str,
        approval_comment: Optional[str] = None,
    ) -> bool:
        """审批通过工作流"""
        workflow = WorkflowManager.get_workflow(workflow_id)
        if not workflow:
            return False
        
        if workflow["status"] != STATUS_PENDING:
            return False  # 只能审批待审批状态的工作流
        
        WorkflowManager.update_workflow(
            workflow_id,
            status=STATUS_APPROVED,
            approver_id=approver_id,
            approver_username=approver_username,
            approval_time=get_current_timestamp(),
            approval_comment=approval_comment or "已通过",
        )
        
        return True
    
    @staticmethod
    def reject_workflow(
        workflow_id: str,
        approver_id: int,
        approver_username: str,
        approval_comment: Optional[str] = None,
    ) -> bool:
        """拒绝工作流"""
        workflow = WorkflowManager.get_workflow(workflow_id)
        if not workflow:
            return False
        
        if workflow["status"] != STATUS_PENDING:
            return False  # 只能审批待审批状态的工作流
        
        WorkflowManager.update_workflow(
            workflow_id,
            status=STATUS_REJECTED,
            approver_id=approver_id,
            approver_username=approver_username,
            approval_time=get_current_timestamp(),
            approval_comment=approval_comment or "已拒绝",
        )
        
        return True
    
    @staticmethod
    def mark_as_synced(workflow_id: str) -> bool:
        """标记工作流已同步到API"""
        return WorkflowManager.update_workflow(workflow_id, synced_to_api=True)

