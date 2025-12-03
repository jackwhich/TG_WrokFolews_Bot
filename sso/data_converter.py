"""数据转换器模块 - 将 TG 工作流数据转换为 SSO 工单数据"""
import re
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSODataConverter:
    """SSO 数据转换器类"""
    
    @staticmethod
    def parse_tg_submission_data(submission_data: str) -> Dict:
        """
        解析 TG 提交数据字符串
        
        Args:
            submission_data: TG 工作流的 submission_data 字符串
            
        Returns:
            解析后的结构化数据字典
            
        Example:
            输入:
            申请时间: 2024-01-01 10:00:00
            申请项目: EBPAY
            申请环境: UAT
            申请部署服务: pre-admin-export, pre-adminmanager
            申请发版hash: abc123, def456
            申请发版服务内容: 修复bug
            
            返回:
            {
                'apply_time': '2024-01-01 10:00:00',
                'project': 'EBPAY',
                'environment': 'UAT',
                'services': ['pre-admin-export', 'pre-adminmanager'],
                'hashes': ['abc123', 'def456'],
                'content': '修复bug'
            }
        """
        result = {
            'apply_time': None,
            'project': None,
            'environment': None,
            'services': [],
            'hashes': [],
            'branch': 'uat-ebpay',  # 默认分支
            'content': None
        }
        
        # 使用正则表达式提取各字段
        patterns = {
            'apply_time': r'申请时间[：:]\s*([^\n]+)',
            'project': r'申请项目[：:]\s*([^\n]+)',
            'environment': r'申请环境[：:]\s*([^\n]+)',
            'services': r'申请部署服务[：:]\s*([^\n]+)',
            'hash': r'申请发版hash[：:]\s*([^\n]+)',
            'branch': r'申请发版分支[：:]\s*([^\n]+)',
            'content': r'申请发版服务内容[：:]\s*(.+?)(?=\n|$)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, submission_data, re.MULTILINE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                
                if key == 'services':
                    # 服务可能是逗号分隔的列表（支持中文和英文逗号）
                    # 先统一替换中文逗号和顿号为英文逗号
                    value_normalized = value.replace('，', ',').replace('、', ',')
                    result['services'] = [s.strip() for s in value_normalized.split(',') if s.strip()]
                elif key == 'hash':
                    # Hash 可能是逗号分隔或换行分隔（支持中文和英文逗号）
                    # 先统一替换中文逗号和顿号为英文逗号
                    value_normalized = value.replace('，', ',').replace('、', ',')
                    result['hashes'] = [h.strip() for h in re.split(r'[,\n]', value_normalized) if h.strip()]
                elif key == 'branch':
                    # 分支是单个值
                    result['branch'] = value.strip() if value.strip() else 'uat-ebpay'
                else:
                    result[key] = value
        
        logger.debug(f"解析 TG 提交数据结果: {result}")
        return result
    
    @staticmethod
    def convert_to_sso_format(
        workflow_data: Dict,
        job_ids: List[str],
        approver_email: Optional[str] = None
    ) -> Dict:
        """
        将 TG 工作流数据转换为 SSO 工单数据格式
        
        Args:
            workflow_data: 工作流完整数据（从数据库读取，包含 submission_data）
            job_ids: 从SSO获取的Job IDs（与服务一一对应）
            approver_email: 审批人邮箱（可选，如果未提供则从 workflow_data 中获取）
            
        Returns:
            SSO 工单数据字典
            
        Raises:
            ValueError: 如果服务与 job_ids 数量不匹配
            
        Example:
            workflow_data = {
                'workflow_id': 'xxx',
                'submission_data': '申请项目: EBPAY\n申请环境: UAT\n...',
                'approver_username': 'user@example.com'
            }
            job_ids = ['job_123', 'job_456']
            
            返回: SSO 工单数据格式
        """
        # 从 workflow_data 中获取 submission_data 并解析
        submission_data = workflow_data.get('submission_data', '')
        if not submission_data:
            raise ValueError("工作流数据中缺少 submission_data")
        
        tg_data = SSODataConverter.parse_tg_submission_data(submission_data)
        
        # 从解析后的数据读取项目和环境
        project_name = tg_data.get('project')
        environment = tg_data.get('environment')  # 直接来自 options.json 的 environments（如 "UAT" 或 "GRAY-UAT"）
        
        if not project_name:
            raise ValueError("无法从提交数据中解析项目名称")
        if not environment:
            raise ValueError("无法从提交数据中解析环境")
        
        # 从 tg_data 获取服务和 hash 信息（服务名在 options.json 中已经是完整的名称）
        services = tg_data.get('services', [])
        hashes = tg_data.get('hashes', [])
        
        # 验证服务与 hash 数量是否一致
        if len(services) != len(hashes):
            error_msg = f"服务数量 ({len(services)}) 与 hash 数量 ({len(hashes)}) 不一致"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 验证服务与 job_ids 数量是否一致
        if len(services) != len(job_ids):
            error_msg = f"服务数量 ({len(services)}) 与 Job ID 数量 ({len(job_ids)}) 不一致"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 获取审批人邮箱
        if not approver_email:
            approver_email = workflow_data.get('approver_username', '')
        
        # 构建订单列表
        order_list = []
        account_data = []
        
        # 支持多个服务：每个服务创建一个订单项
        for idx, service in enumerate(services):
            job_id = job_ids[idx]
            service_hash = hashes[idx]
            
            # 每个订单项的 name 字段只包含一个服务名（服务名在 options.json 中已经是完整的名称）
            order_item = {
                "project_name": project_name,
                "env": environment,  # 直接使用用户在表单中选择的环境
                "job_id": job_id,
                "name": service,  # 服务名在 options.json 中已经是完整的名称（如 pre-admin-export）
                "parameters": {
                    "check_commitID": service_hash or "",
                    "action_type": "gray",
                    "gitBranch": "",
                    "canRollback": "不支持",
                    "rollback_ver": ""
                }
            }
            
            # SSO 要求的格式：每个服务是一个列表，包含一个订单项
            order_list.append([order_item])
            account_data.append(order_item)
        
        logger.info(f"构建 SSO 订单列表完成 - 项目: {project_name}, 环境: {environment}, 服务数: {len(services)}")
        
        # 使用 data_format 模块构建完整的 SSO 工单数据
        from sso.data_format import SSODataFormatter
        sso_data = SSODataFormatter.format_order_data(
            project_name=project_name,
            user_mail=approver_email,
            order_list=order_list,
            account_data=account_data
        )
        
        return sso_data


# 为了向后兼容，保留函数式接口
def parse_tg_submission_data(submission_data: str) -> Dict:
    """解析 TG 提交数据字符串（函数式接口）"""
    return SSODataConverter.parse_tg_submission_data(submission_data)


def convert_to_sso_format(
    workflow_data: Dict,
    job_ids: List[str],
    approver_email: Optional[str] = None
) -> Dict:
    """将 TG 工作流数据转换为 SSO 工单数据格式（函数式接口）"""
    return SSODataConverter.convert_to_sso_format(workflow_data, job_ids, approver_email)
