"""SSO 数据格式化模块"""
import json
from datetime import datetime
from typing import Dict, List
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SSODataFormatter:
    """SSO 数据格式化器类"""
    
    @staticmethod
    def format_order_data(
        project_name: str,
        user_mail: str,
        order_list: List[List[Dict]],
        account_data: List[Dict]
    ) -> Dict:
        """
        构建 SSO 工单数据格式
        
        Args:
            project_name: 项目名称
            user_mail: 审批人邮箱
            order_list: 订单列表，格式为 [[订单项1], [订单项2], ...]
            account_data: 账户数据列表
            
        Returns:
            SSO 工单数据字典
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建工单标题（项目名 + 预发发版）
        title = f"{project_name}预发发版"
        
        data = {
            "detail": [
                [
                    {"status": "申请详情"},
                    {"id": "projectName", "name": "项目名称", "value": project_name},
                    {"id": "releaseType", "name": "发布类型", "value": "常规发布"},
                    {"id": "category", "name": "依赖业务", "value": ""},
                    {"id": "environment", "name": "上线环境", "value": "预发环境"},
                    {"id": "releaseTime", "name": "上线时间", "value": current_time},
                    {"id": "repository", "name": "仓库地址", "value": ""},
                    {"id": "codeBranch", "name": "代码分支", "value": ""},
                    {"id": "onlineVersion", "name": "上线版本", "value": "上线版本"},
                    {"id": "onlineMD5", "name": "MD5", "value": "MD5"},
                    {"id": "updateContent", "name": "更新内容", "value": "更新内容"},
                    {"id": "sqlUpdate", "name": "SQL更新", "value": False},
                    {"id": "configUpdate", "name": "配置文件更新", "value": False},
                    {"id": "affectScope", "name": "影响范围", "value": "影响范围"},
                    {"id": "rollbackInstructions", "name": "回滚说明", "value": ""},
                    {"id": "releaseProcess", "name": "发布流程", "value": "发布流程"},
                    {"id": "mainBusiness", "name": "是否主线业务", "value": False},
                    {"id": "needTest", "name": "是否需要测试", "value": False},
                    {"id": "upload", "name": "SQL脚本", "value": ""},
                    {"id": "ifUploadJT", "name": "截图审批", "value": False},
                    {"id": "sourceRemark", "name": "备注", "value": "备注"},
                    {
                        "id": "application",
                        "name": "发布应用",
                        "children": order_list,
                        "account_data": account_data,
                        "job_status": True
                    },
                    {"id": "approver", "name": "审批人", "value": user_mail}
                ]
            ],
            "draftId": "",
            "endType": "0",
            "processStatus": "0",
            "publishVersion": "0",
            "title": title,
            "type": "dcAutoReleaseProcess",
            "userId": "10572"
        }
        
        logger.debug(f"构建 SSO 工单数据完成 - 项目: {project_name}, 订单数: {len(order_list)}")
        return data


# 为了向后兼容，保留函数式接口
def run_format_data(
    project_name: str,
    user_mail: str,
    order_list: List[List[Dict]],
    account_data: List[Dict]
) -> Dict:
    """构建 SSO 工单数据格式（函数式接口）"""
    return SSODataFormatter.format_order_data(project_name, user_mail, order_list, account_data)
