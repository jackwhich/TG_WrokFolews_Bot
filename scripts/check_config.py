#!/usr/bin/env python3
"""检查数据库中的项目配置"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from workflows.models import WorkflowManager
import json

def main():
    """检查项目配置"""
    print("=" * 50)
    print("检查数据库中的项目配置")
    print("=" * 50)
    
    # 初始化数据库连接
    try:
        conn = WorkflowManager._get_connection()
        cursor = conn.cursor()
        
        # 先检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_options'
        """)
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("❌ 数据库表不存在")
            print("提示: 请先运行 python3 scripts/init_db.py 初始化数据库")
            print("\n" + "=" * 50)
            return
        
        # 检查配置是否存在
        cursor.execute("SELECT COUNT(*) FROM project_options WHERE config_key = 'projects'")
        count = cursor.fetchone()[0]
    except Exception as e:
        print(f"❌ 检查配置时发生错误: {str(e)}")
        print("提示: 请先运行 python3 scripts/init_db.py 初始化数据库")
        print("\n" + "=" * 50)
        return
    
    if count > 0:
        print(f"✅ 配置已存在于数据库中（共 {count} 条记录）")
        
        # 获取配置内容
        cursor.execute("""
            SELECT config_key, config_value, updated_at 
            FROM project_options 
            WHERE config_key = 'projects'
        """)
        row = cursor.fetchone()
        
        if row:
            config_key, config_value, updated_at = row
            print(f"\n配置键: {config_key}")
            print(f"更新时间戳: {updated_at}")
            
            # 解析并显示配置内容
            try:
                config_data = json.loads(config_value)
                print("\n配置内容:")
                print(json.dumps(config_data, ensure_ascii=False, indent=2))
                
                # 统计信息
                projects = config_data.get("projects", {})
                print(f"\n📊 统计信息:")
                print(f"  - 项目数量: {len(projects)}")
                for project_name, project_data in projects.items():
                    envs = project_data.get("environments", [])
                    services = project_data.get("services", {})
                    total_services = sum(len(svcs) for svcs in services.values())
                    print(f"  - {project_name}: {len(envs)} 个环境, {total_services} 个服务")
            except json.JSONDecodeError as e:
                print(f"❌ 解析配置JSON失败: {e}")
                print(f"原始内容: {config_value[:200]}...")
    else:
        print("❌ 配置不存在于数据库中")
        print("提示: 请运行 python3 scripts/init_db.py 初始化数据库配置")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()

