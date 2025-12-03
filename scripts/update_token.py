#!/usr/bin/env python3
"""更新 BOT_TOKEN 配置"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from workflows.models import WorkflowManager
from config.settings import Settings

def main():
    """更新 BOT_TOKEN"""
    if len(sys.argv) < 2:
        print("用法: python scripts/update_token.py <BOT_TOKEN>")
        print("示例: python scripts/update_token.py 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        sys.exit(1)
    
    token = sys.argv[1]
    
    if not token:
        print("❌ 错误: BOT_TOKEN 不能为空")
        sys.exit(1)
    
    # 更新数据库中的配置
    result = WorkflowManager.update_app_config("BOT_TOKEN", token)
    
    if result:
        print(f"✅ BOT_TOKEN 已更新到数据库")
        
        # 刷新 Settings 缓存
        Settings._refresh_cache()
        Settings.load_from_db()
        
        # 验证
        if Settings.BOT_TOKEN == token:
            print(f"✅ 验证成功: BOT_TOKEN 已正确加载")
            print(f"   Token 前10位: {token[:10]}...")
        else:
            print(f"⚠️  警告: 配置已更新，但验证失败")
    else:
        print("❌ 更新失败，请检查日志")
        sys.exit(1)

if __name__ == "__main__":
    main()
