#!/usr/bin/env python3
"""简单的数据库查询工具"""
import sqlite3
import json
from pathlib import Path

DB_FILE = Path("data/workflows.db")

def query_project_options():
    """查询项目配置"""
    if not DB_FILE.exists():
        print(f"❌ 数据库文件不存在: {DB_FILE}")
        return
    
    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()
    
    # 检查配置是否存在
    cursor.execute("SELECT COUNT(*) FROM project_options WHERE config_key = 'projects'")
    count = cursor.fetchone()[0]
    
    if count > 0:
        print("✅ 配置已存在于数据库中")
        
        # 获取配置
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
            
            # 显示配置内容
            try:
                config_data = json.loads(config_value)
                print("\n配置内容:")
                print(json.dumps(config_data, ensure_ascii=False, indent=2))
            except:
                print(f"\n原始内容: {config_value[:200]}...")
    else:
        print("❌ 配置不存在于数据库中")
    
    conn.close()

if __name__ == "__main__":
    query_project_options()

