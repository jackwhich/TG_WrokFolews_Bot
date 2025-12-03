"""数据同步器"""
from typing import Tuple, Optional
from .client import APIClient
from workflows.state_machine import WorkflowStateMachine
from utils.logger import setup_logger

logger = setup_logger(__name__)


def sync_workflow_to_api(workflow_data: dict) -> Tuple[bool, Optional[str]]:
    """
    同步工作流到外部API
    
    Args:
        workflow_data: 工作流数据
        
    Returns:
        (是否成功, 错误信息)
    """
    client = APIClient()
    success, error = client.sync_workflow(workflow_data)
    
    if success:
        # 标记为已同步
        workflow_id = workflow_data.get("workflow_id")
        WorkflowStateMachine.mark_as_synced(workflow_id)
        logger.info(f"工作流 {workflow_id} 已标记为已同步")
    
    return success, error

