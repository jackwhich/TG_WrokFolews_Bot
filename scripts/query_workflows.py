#!/usr/bin/env python3
"""查询工作流数据"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from workflows.models import WorkflowManager

def main():
    """查询工作流数据"""
    print("=" * 60)
    print("工作流数据查询")
    print("=" * 60)
    
    try:
        # 初始化数据库连接
        conn = WorkflowManager._get_connection()
        cursor = conn.cursor()
        
        # 先检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='workflows'
        """)
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("❌ 数据库表不存在")
            print("提示: 请先运行 python3 scripts/init_db.py 初始化数据库")
            print("\n" + "=" * 60)
            return
        
        # 统计信息
        cursor.execute("SELECT COUNT(*) FROM workflows")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'approved'")
        approved = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'rejected'")
        rejected = cursor.fetchone()[0]
    except Exception as e:
        print(f"❌ 查询工作流数据时发生错误: {str(e)}")
        print("提示: 请先运行 python3 scripts/init_db.py 初始化数据库")
        print("\n" + "=" * 60)
        return
    
    print(f"\n📊 统计信息:")
    print(f"  - 总工作流数: {total}")
    print(f"  - 待审批: {pending}")
    print(f"  - 已通过: {approved}")
    print(f"  - 已拒绝: {rejected}")
    
    # 查询最近的工作流
    print(f"\n📋 最近的工作流（最多10条）:")
    print("-" * 60)
    
    cursor.execute("""
        SELECT 
            workflow_id,
            username,
            status,
            approver_username,
            created_at,
            approval_time,
            timestamp
        FROM workflows 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    if rows:
        for i, row in enumerate(rows, 1):
            workflow_id, username, status, approver_username, created_at, approval_time, timestamp = row
            print(f"\n{i}. 工作流ID: {workflow_id}")
            print(f"   提交人: @{username}")
            print(f"   状态: {status}")
            if approver_username:
                print(f"   审批人: @{approver_username}")
            print(f"   创建时间: {created_at}")
            if approval_time:
                print(f"   审批时间: {approval_time}")
            print(f"   时间戳: {timestamp}")
    else:
        print("   (暂无工作流数据)")
    
    # 查询特定工作流（如果提供了ID）
    import sys
    if len(sys.argv) > 1:
        workflow_id = sys.argv[1]
        print(f"\n🔍 查询工作流详情: {workflow_id}")
        print("-" * 60)
        
        workflow = WorkflowManager.get_workflow(workflow_id)
        if workflow:
            import json
            print(json.dumps(workflow, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 工作流 {workflow_id} 不存在")
    
    print("\n" + "=" * 60)
    print("💡 提示: 使用 'python3 scripts/query_workflows.py <workflow_id>' 查询特定工作流")
    print("=" * 60)

if __name__ == "__main__":
    main()

