"""数据验证器"""
from typing import Tuple, Optional


def validate_submission_data(data: str) -> Tuple[bool, Optional[str]]:
    """
    验证提交数据
    
    Args:
        data: 用户提交的数据字符串
        
    Returns:
        (是否有效, 错误信息)
    """
    if not data:
        return False, "提交内容不能为空"
    
    if len(data.strip()) == 0:
        return False, "提交内容不能为空"
    
    # 可以添加更多验证规则
    # 例如：长度限制、格式验证等
    
    if len(data) > 5000:
        return False, "提交内容过长，请控制在5000字符以内"
    
    return True, None

