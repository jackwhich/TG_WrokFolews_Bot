"""工作流数据模型"""
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from utils.helpers import generate_workflow_id, get_current_timestamp
from config.constants import STATUS_PENDING
from utils.logger import setup_logger

logger = setup_logger(__name__)


class WorkflowManager:
    """工作流管理器（SQLite 时序数据库存储）"""
    
    # 数据存储目录
    DATA_DIR = Path("data")
    
    # SQLite 数据库文件路径
    DB_FILE = DATA_DIR / "workflows.db"
    
    # 数据库连接（线程安全，使用连接池）
    _connection: Optional[sqlite3.Connection] = None
    _schema_initialized: bool = False
    
    # 数据保留天数（60天）
    RETENTION_DAYS = 60
    
    @classmethod
    def _get_connection(cls) -> sqlite3.Connection:
        """获取数据库连接（单例模式，优化性能）"""
        if cls._connection is None:
            # 确保数据目录存在
            cls.DATA_DIR.mkdir(exist_ok=True)
            
            # 创建连接，启用外键约束
            # 注意：Python 3.12+ 默认使用自动提交模式，需要显式设置事务模式以支持手动事务管理
            cls._connection = sqlite3.connect(
                str(cls.DB_FILE),
                check_same_thread=False,  # 允许多线程访问
                timeout=30.0,  # 30秒超时
                isolation_level='DEFERRED'  # 使用显式事务模式，支持手动 commit()/rollback()
            )
            cls._connection.row_factory = sqlite3.Row  # 返回字典式行对象
            
            # 性能优化：启用WAL模式（Write-Ahead Logging）提升并发性能
            cls._connection.execute("PRAGMA journal_mode = WAL")
            # 设置忙等待超时（毫秒），减少锁冲突
            cls._connection.execute("PRAGMA busy_timeout = 5000")
            # 优化同步模式：NORMAL模式在WAL下更安全且性能更好
            cls._connection.execute("PRAGMA synchronous = NORMAL")
            # 启用外键约束
            cls._connection.execute("PRAGMA foreign_keys = ON")
            # 优化缓存大小（2MB，可根据需要调整）
            cls._connection.execute("PRAGMA cache_size = -2048")
            # 优化临时存储
            cls._connection.execute("PRAGMA temp_store = MEMORY")
            
            logger.debug(f"SQLite 数据库连接已建立（WAL模式）: {cls.DB_FILE}")
        
        # 确保表结构
        if not cls._schema_initialized:
            cls._ensure_schema()
        
        return cls._connection

    # ------------------------------------------------------------------ schema helpers
    @classmethod
    def _ensure_column(cls, cursor: sqlite3.Cursor, table: str, column: str, definition: str):
        """如果列不存在则新增"""
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @classmethod
    def _ensure_schema(cls):
        """初始化/迁移表结构（幂等）"""
        conn = cls._connection
        if conn is None:
            return
        cursor = conn.cursor()

        # 原有表结构
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                submission_data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                approver_id INTEGER,
                approver_username TEXT,
                approval_time TEXT,
                approval_comment TEXT,
                created_at TEXT NOT NULL,
                synced_to_api INTEGER NOT NULL DEFAULT 0,
                group_messages TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_messages (
                message_id INTEGER PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                group_id INTEGER NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_options (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT,
                updated_at INTEGER NOT NULL
            )
        """)

        # SSO 相关表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sso_submissions (
                submission_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                process_instance_id TEXT,
                sso_order_data TEXT NOT NULL,
                submit_status TEXT NOT NULL DEFAULT 'pending',
                submit_time INTEGER NOT NULL,
                submit_response TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sso_build_status (
                build_id TEXT PRIMARY KEY,
                submission_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                release_id INTEGER NOT NULL,
                job_name TEXT NOT NULL,
                service_name TEXT,
                job_id TEXT,
                build_status TEXT NOT NULL DEFAULT 'BUILDING',
                build_start_time INTEGER,
                build_end_time INTEGER,
                build_detail TEXT,
                notified INTEGER NOT NULL DEFAULT 0,
                notification_time INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (submission_id) REFERENCES sso_submissions(submission_id) ON DELETE CASCADE,
                FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
            )
        """)

        # Jenkins 构建表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jenkins_builds (
                build_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                job_name TEXT NOT NULL,
                job_url TEXT,
                build_number INTEGER,
                build_status TEXT NOT NULL DEFAULT 'BUILDING',
                build_start_time INTEGER,
                build_end_time INTEGER,
                build_duration INTEGER,
                build_console_output TEXT,
                build_parameters TEXT,
                notified INTEGER NOT NULL DEFAULT 0,
                notification_time INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
            )
        """)

        # 新增：消息模板表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_templates (
                template_type TEXT NOT NULL,
                project TEXT,
                content TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (template_type, project)
            )
        """)

        # 迁移新增列
        cls._ensure_column(cursor, "workflows", "project", "TEXT")
        cls._ensure_column(cursor, "workflows", "template_type", "TEXT")

        # 索引（保留原有，存在则跳过）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_timestamp 
            ON workflows(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_status 
            ON workflows(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_user_id 
            ON workflows(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_approver_id 
            ON workflows(approver_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_synced_to_api 
            ON workflows(synced_to_api)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_messages_workflow_id 
            ON workflow_messages(workflow_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_messages_group_id 
            ON workflow_messages(group_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_messages_message_id 
            ON workflow_messages(message_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_status_timestamp 
            ON workflows(status, timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_user_timestamp 
            ON workflows(user_id, timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_approver_timestamp 
            ON workflows(approver_id, timestamp DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_submissions_workflow_id 
            ON sso_submissions(workflow_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_submissions_process_instance_id 
            ON sso_submissions(process_instance_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_workflow_id 
            ON sso_build_status(workflow_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_submission_id 
            ON sso_build_status(submission_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_job_id 
            ON sso_build_status(job_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_status 
            ON sso_build_status(build_status)
        """)
        
        # 性能优化：添加缺失的关键索引
        # SSO submissions 查询优化索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_submissions_workflow_time 
            ON sso_submissions(workflow_id, submit_time DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_submissions_submit_status 
            ON sso_submissions(submit_status)
        """)
        
        # SSO build status 通知查询优化索引（复合索引覆盖常用查询）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_notify 
            ON sso_build_status(build_status, notified, build_end_time)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_notified 
            ON sso_build_status(notified)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sso_build_status_end_time 
            ON sso_build_status(build_end_time)
        """)
        
        # workflows 项目/模板类型查询优化索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_project_template 
            ON workflows(project, template_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflows_project 
            ON workflows(project)
        """)
        
        # Jenkins builds 通知查询优化索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jenkins_builds_notify 
            ON jenkins_builds(build_status, notified, build_end_time)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jenkins_builds_notified 
            ON jenkins_builds(notified)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jenkins_builds_end_time 
            ON jenkins_builds(build_end_time)
        """)

        conn.commit()
        cls._schema_initialized = True
    
    @classmethod
    def _init_database(cls):
        """初始化数据库表结构（委托 _ensure_schema，避免重复定义）"""
        cls._get_connection()
        cls._ensure_schema()
        logger.info("✅ 数据库表结构和索引初始化完成（幂等）")
    
    @classmethod
    def _init_project_options(cls, options_file: Path = None, force_update: bool = False):
        """
        初始化项目配置选项（从 JSON 文件导入到数据库）
        
        Args:
            options_file: 配置文件路径
            force_update: 是否强制更新（即使数据库中已有配置也更新）
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 检查数据库中是否已有配置
        cursor.execute("SELECT COUNT(*) FROM project_options WHERE config_key = 'projects'")
        count = cursor.fetchone()[0]
        
        if count > 0 and not force_update:
            logger.info("项目配置已存在于数据库中，跳过初始化")
            return
        
        # 从 JSON 文件加载
        if options_file is None:
            options_file = Path("config/options.json")
        
        if not options_file.exists():
            logger.error(f"项目配置文件不存在: {options_file}，请创建该文件")
            raise FileNotFoundError(f"项目配置文件不存在: {options_file}")
        
        try:
            with open(options_file, 'r', encoding='utf-8') as f:
                options_data = json.load(f)
            logger.info(f"从文件加载项目配置: {options_file}")
        except Exception as e:
            logger.error(f"读取项目配置文件失败: {str(e)}", exc_info=True)
            raise
        
        # 将配置存储到数据库（使用事务优化批量操作）
        timestamp = int(time.time())
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO project_options (config_key, config_value, updated_at)
                VALUES (?, ?, ?)
            """, ("projects", json.dumps(options_data, ensure_ascii=False), timestamp))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        if force_update:
            logger.info("✅ 项目配置已更新到数据库")
        else:
            logger.info("✅ 项目配置已初始化到数据库")
    
    @classmethod
    def get_project_options(cls) -> Dict:
        """从数据库获取项目配置"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT config_value FROM project_options 
            WHERE config_key = 'projects'
        """)
        
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"解析项目配置JSON失败: {str(e)}", exc_info=True)
                return {"projects": {}}
        
        return {"projects": {}}
    
    @classmethod
    def update_project_options(cls, options_data: Dict) -> bool:
        """更新项目配置"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        try:
            timestamp = int(time.time())
            cursor.execute("""
                INSERT OR REPLACE INTO project_options (config_key, config_value, updated_at)
                VALUES (?, ?, ?)
            """, ("projects", json.dumps(options_data, ensure_ascii=False), timestamp))
            conn.commit()
            logger.info("✅ 项目配置已更新")
            return True
        except Exception as e:
            logger.error(f"更新项目配置失败: {str(e)}", exc_info=True)
            return False

    # ======================== 模板读写 ========================
    @classmethod
    def _ensure_default_templates(cls):
        """如果模板表缺省，则写入默认模板（幂等）"""
        from config.constants import (
            WORKFLOW_MESSAGE_TEMPLATE,
            WORKFLOW_APPROVED_TEMPLATE,
            WORKFLOW_REJECTED_TEMPLATE,
            WORKFLOW_MESSAGE_TEMPLATE_ADDRESS,
            WORKFLOW_APPROVED_TEMPLATE_ADDRESS,
            WORKFLOW_REJECTED_TEMPLATE_ADDRESS,
        )
        conn = cls._get_connection()
        cursor = conn.cursor()

        defaults = {
            ("default", None): WORKFLOW_MESSAGE_TEMPLATE,
            ("approved_default", None): WORKFLOW_APPROVED_TEMPLATE,
            ("rejected_default", None): WORKFLOW_REJECTED_TEMPLATE,
            ("address_only", None): WORKFLOW_MESSAGE_TEMPLATE_ADDRESS,
            ("approved_address_only", None): WORKFLOW_APPROVED_TEMPLATE_ADDRESS,
            ("rejected_address_only", None): WORKFLOW_REJECTED_TEMPLATE_ADDRESS,
        }

        timestamp = int(time.time())
        changed = False
        try:
            for (tpl_type, project), content in defaults.items():
                cursor.execute(
                    "SELECT 1 FROM message_templates WHERE template_type = ? AND project IS ?",
                    (tpl_type, project),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        """
                        INSERT INTO message_templates (template_type, project, content, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (tpl_type, project, content, timestamp),
                    )
                    changed = True
            if changed:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"初始化默认模板失败: {str(e)}", exc_info=True)
            raise

    @classmethod
    def set_message_template(cls, template_type: str, content: str, project: Optional[str] = None) -> bool:
        """写入/更新消息模板"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        try:
            timestamp = int(time.time())
            cursor.execute(
                """
                INSERT INTO message_templates (template_type, project, content, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(template_type, project) DO UPDATE SET
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (template_type, project, content, timestamp),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新消息模板失败: {str(e)}", exc_info=True)
            return False

    @classmethod
    def get_message_template(
        cls,
        template_type: str,
        project: Optional[str] = None,
        default: Optional[str] = None
    ) -> str:
        """获取消息模板，优先项目级，其次通用，最后回退默认值"""
        conn = cls._get_connection()
        cursor = conn.cursor()

        # 确保有缺省模板
        cls._ensure_default_templates()

        # 项目级
        if project:
            cursor.execute(
                """
                SELECT content FROM message_templates
                WHERE template_type = ? AND project = ?
                """,
                (template_type, project),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]

        # 全局
        cursor.execute(
            """
            SELECT content FROM message_templates
            WHERE template_type = ? AND project IS NULL
            """,
            (template_type,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]

        return default or ""
    
    @classmethod
    def _row_to_dict(cls, row: sqlite3.Row) -> dict:
        """将数据库行转换为字典"""
        if row is None:
            return None
        
        data = dict(row)
        
        # 解析 group_messages JSON
        if data.get('group_messages'):
            try:
                data['group_messages'] = json.loads(data['group_messages'])
            except (json.JSONDecodeError, TypeError):
                data['group_messages'] = {}
        else:
            data['group_messages'] = {}
        
        # 转换 synced_to_api
        data['synced_to_api'] = bool(data.get('synced_to_api', 0))

        # 补充模板类型/项目字段默认值
        data['project'] = data.get('project')
        data['template_type'] = data.get('template_type') or "default"
        
        return data
    
    @classmethod
    def _cleanup_old_data(cls):
        """清理 60 天前的旧数据（分批删除优化性能，避免长时间锁表）"""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()
            
            # 计算 60 天前的时间戳
            cutoff_time = datetime.now() - timedelta(days=cls.RETENTION_DAYS)
            cutoff_timestamp = int(cutoff_time.timestamp())
            
            # 分批删除，每次删除1000条，避免长时间锁表
            batch_size = 1000
            total_deleted = 0
            
            while True:
                # 使用 LIMIT 分批删除
                cursor.execute("""
                    DELETE FROM workflows 
                    WHERE workflow_id IN (
                        SELECT workflow_id FROM workflows 
                        WHERE timestamp < ? 
                        LIMIT ?
                    )
                """, (cutoff_timestamp, batch_size))
                
                deleted_in_batch = cursor.rowcount
                total_deleted += deleted_in_batch
                conn.commit()
                
                if deleted_in_batch == 0:
                    break
                
                logger.debug(f"清理进度: 已删除 {total_deleted} 条旧数据")
                
                # 短暂休眠，让其他操作有机会执行
                time.sleep(0.1)
            
            if total_deleted > 0:
                logger.info(f"已清理 {total_deleted} 条 {cls.RETENTION_DAYS} 天前的旧数据")
                # 可选：执行 VACUUM 回收空间（在低峰期执行）
                # cursor.execute("PRAGMA incremental_vacuum")
            
            return total_deleted
        except Exception as e:
            logger.error(f"清理旧数据时发生错误: {str(e)}", exc_info=True)
            return 0
    
    @classmethod
    def _init_app_config(cls):
        """初始化应用配置表（仅创建表结构，配置值从 settings.py 的默认值初始化）"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 检查数据库中是否已有配置
        cursor.execute("SELECT COUNT(*) FROM app_config")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info("应用配置已存在于数据库中，跳过初始化")
            return
        
        # 表结构已在 _init_database() 中创建，这里只是标记表已初始化
        logger.info("✅ 应用配置表已初始化（配置值需要通过 scripts/init_db.py 脚本初始化）")
    
    @classmethod
    def initialize(cls, options_file: Path = None):
        """
        初始化工作流管理器（公共方法）
        
        这个方法会：
        1. 初始化数据库表结构
        2. 从 options.json 文件导入项目配置到数据库
        3. 初始化应用配置表（配置值需要通过 scripts/init_db.py 脚本初始化）
        
        注意：此方法已废弃，请使用 scripts/init_db.py 脚本进行初始化
        
        Args:
            options_file: 项目配置文件路径（默认为 config/options.json）
        """
        try:
            # 1. 初始化数据库表结构
            cls._init_database()
            
            # 2. 初始化项目配置（从 options.json）
            cls._init_project_options(options_file)
            
            # 3. 初始化应用配置表
            cls._init_app_config()
            
            logger.info("✅ 工作流管理器初始化完成")
        except Exception as e:
            logger.error(f"❌ 工作流管理器初始化失败: {str(e)}", exc_info=True)
            raise
    
    @classmethod
    def get_app_config(cls, key: str, default: str = None) -> Optional[str]:
        """从数据库获取应用配置"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT config_value FROM app_config 
            WHERE config_key = ?
        """, (key,))
        
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
        
        return default
    
    @classmethod
    def get_all_app_config(cls) -> Dict[str, str]:
        """从数据库获取所有应用配置"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT config_key, config_value FROM app_config")
        rows = cursor.fetchall()
        
        config_dict = {}
        for row in rows:
            config_dict[row[0]] = row[1] if row[1] is not None else ""
        
        return config_dict
    
    @classmethod
    def update_app_config(cls, key: str, value: str) -> bool:
        """更新应用配置"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        try:
            timestamp = int(time.time())
            cursor.execute("""
                INSERT OR REPLACE INTO app_config (config_key, config_value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, timestamp))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"更新应用配置失败: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def create_workflow(
        cls,
        user_id: int,
        username: str,
        submission_data: str,
        project: Optional[str] = None,
        template_type: str = "default",
    ) -> dict:
        """
        创建工作流
        
        Args:
            user_id: 用户ID
            username: 用户名
            submission_data: 提交的数据（字符串格式）
            
        Returns:
            创建的工作流数据字典
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 生成工作流ID
        workflow_id = generate_workflow_id()
        timestamp = int(time.time())
        created_at = get_current_timestamp()
        
        # 插入工作流（使用事务确保原子性）
        try:
            cursor.execute("""
                INSERT INTO workflows (
                    workflow_id, timestamp, user_id, username, submission_data,
                    status, created_at, project, template_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (workflow_id, timestamp, user_id, username, submission_data, STATUS_PENDING, created_at, project, template_type))
            
            conn.commit()
            logger.info(f"✅ 工作流已创建 - ID: {workflow_id}, 用户: {username} ({user_id})")
        except Exception as e:
            conn.rollback()
            logger.error(f"创建工作流失败: {str(e)}", exc_info=True)
            raise
        
        # 返回创建的工作流数据
        return {
            "workflow_id": workflow_id,
            "timestamp": timestamp,
            "user_id": user_id,
            "username": username,
            "submission_data": submission_data,
            "status": STATUS_PENDING,
            "created_at": created_at,
            "synced_to_api": False,
            "group_messages": {},
            "project": project,
            "template_type": template_type,
        }
    
    @classmethod
    def get_workflow(cls, workflow_id: str) -> Optional[dict]:
        """获取工作流"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM workflows 
            WHERE workflow_id = ?
        """, (workflow_id,))
        
        row = cursor.fetchone()
        if row:
            return cls._row_to_dict(row)
        
        return None
    
    @classmethod
    def get_workflow_by_message_id(cls, message_id: int) -> Optional[dict]:
        """根据消息ID获取工作流"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT w.* FROM workflows w
            INNER JOIN workflow_messages wm ON w.workflow_id = wm.workflow_id
            WHERE wm.message_id = ?
        """, (message_id,))
        
        row = cursor.fetchone()
        if row:
            return cls._row_to_dict(row)
        
        return None
    
    @classmethod
    def update_workflow(cls, workflow_id: str, **kwargs) -> bool:
        """
        更新工作流
        
        Args:
            workflow_id: 工作流ID
            **kwargs: 要更新的字段
        
        Returns:
            是否成功
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 构建更新字段
        update_fields = []
        values = []
        
        # 处理特殊字段
        group_messages_dict = None
        if 'group_messages' in kwargs:
            group_messages_dict = kwargs['group_messages']
            kwargs['group_messages'] = json.dumps(group_messages_dict, ensure_ascii=False) if group_messages_dict else None
        
        if 'synced_to_api' in kwargs:
            kwargs['synced_to_api'] = 1 if kwargs['synced_to_api'] else 0
        
        # 构建 SQL 更新语句
        allowed_fields = [
            'user_id', 'username', 'submission_data', 'status',
            'approver_id', 'approver_username', 'approval_time',
            'approval_comment', 'synced_to_api', 'group_messages',
            'project', 'template_type'
        ]
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if not update_fields:
            logger.warning(f"没有有效的更新字段 - 工作流ID: {workflow_id}")
            return False
        
        # 执行更新
        values.append(workflow_id)
        sql = f"""
            UPDATE workflows 
            SET {', '.join(update_fields)}
            WHERE workflow_id = ?
        """
        
        try:
            cursor.execute(sql, values)
            conn.commit()
            logger.debug(f"工作流已更新 - ID: {workflow_id}, 更新字段: {list(kwargs.keys())}")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"更新工作流失败 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def delete_workflow(cls, workflow_id: str) -> bool:
        """删除工作流（级联删除关联的消息和 SSO 记录）"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM workflows WHERE workflow_id = ?", (workflow_id,))
            conn.commit()
            logger.info(f"✅ 工作流已删除 - ID: {workflow_id}")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"删除工作流失败 - 工作流ID: {workflow_id}, 错误: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def get_all_workflows(
        cls, 
        limit: Optional[int] = None, 
        offset: int = 0,
        status: Optional[str] = None,
        project: Optional[str] = None
    ) -> Dict[str, dict]:
        """
        获取工作流（支持分页和过滤，优化性能）
        
        Args:
            limit: 限制返回数量（默认不限制，建议设置合理值如1000）
            offset: 偏移量（用于分页）
            status: 按状态过滤（可选）
            project: 按项目过滤（可选）
        
        Returns:
            工作流字典
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if project:
            conditions.append("project = ?")
            params.append(project)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # 构建SQL（使用索引优化的ORDER BY）
        sql = f"""
            SELECT * FROM workflows 
            {where_clause}
            ORDER BY timestamp DESC
        """
        
        if limit:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        workflows = {}
        for row in rows:
            data = cls._row_to_dict(row)
            workflows[data['workflow_id']] = data
        
        return workflows
    
    @classmethod
    def cleanup_old_data(cls) -> int:
        """手动触发清理旧数据（公开方法）"""
        return cls._cleanup_old_data()
    
    # ========== SSO 相关数据库操作方法 ==========
    
    @classmethod
    def create_sso_submission(
        cls,
        workflow_id: str,
        sso_order_data: Dict,
        process_instance_id: Optional[str] = None
    ) -> Dict:
        """
        创建 SSO 提交记录
        
        Args:
            workflow_id: 工作流ID
            sso_order_data: SSO 工单数据（字典）
            process_instance_id: SSO 工单ID (可选，提交后获取)
            
        Returns:
            SSO 提交记录字典
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 生成提交ID（使用 workflow_id 作为 submission_id）
        submission_id = workflow_id
        submit_time = int(time.time())
        created_at = get_current_timestamp()
        updated_at = created_at
        
        try:
            cursor.execute("""
                INSERT INTO sso_submissions (
                    submission_id, workflow_id, process_instance_id,
                    sso_order_data, submit_status, submit_time,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                submission_id,
                workflow_id,
                process_instance_id,
                json.dumps(sso_order_data, ensure_ascii=False),
                'pending',
                submit_time,
                created_at,
                updated_at
            ))
            
            conn.commit()
            logger.info(f"✅ SSO 提交记录已创建 - Submission ID: {submission_id}, 工作流ID: {workflow_id}")
            
            return {
                'submission_id': submission_id,
                'workflow_id': workflow_id,
                'process_instance_id': process_instance_id,
                'sso_order_data': sso_order_data,
                'submit_status': 'pending',
                'submit_time': submit_time,
                'created_at': created_at,
                'updated_at': updated_at
            }
        except Exception as e:
            logger.error(f"创建 SSO 提交记录失败: {e}", exc_info=True)
            raise
    
    @classmethod
    def get_sso_submission_by_workflow(cls, workflow_id: str) -> Optional[Dict]:
        """
        根据工作流ID获取 SSO 提交记录
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            SSO 提交记录字典，如果不存在返回 None
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM sso_submissions 
            WHERE workflow_id = ?
            ORDER BY submit_time DESC
            LIMIT 1
        """, (workflow_id,))
        
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('sso_order_data'):
                try:
                    data['sso_order_data'] = json.loads(data['sso_order_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
            if data.get('submit_response'):
                try:
                    data['submit_response'] = json.loads(data['submit_response'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data
        
        return None
    
    @classmethod
    def update_sso_submission_status(
        cls,
        submission_id: str,
        status: str,
        response: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        更新 SSO 提交状态
        
        Args:
            submission_id: SSO 提交ID
            status: 提交状态 (pending/success/failed)
            response: SSO 提交响应（可选）
            error: 错误信息（可选）
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        updated_at = get_current_timestamp()
        update_fields = ["submit_status = ?", "updated_at = ?"]
        values = [status, updated_at]
        
        if response:
            update_fields.append("submit_response = ?")
            values.append(json.dumps(response, ensure_ascii=False))
        
        if error:
            update_fields.append("error_message = ?")
            values.append(error)
        
        values.append(submission_id)
        
        try:
            cursor.execute(f"""
                UPDATE sso_submissions 
                SET {', '.join(update_fields)}
                WHERE submission_id = ?
            """, values)
            
            conn.commit()
            logger.info(f"✅ SSO 提交状态已更新 - Submission ID: {submission_id}, 状态: {status}")
        except Exception as e:
            logger.error(f"更新 SSO 提交状态失败: {e}", exc_info=True)
            raise
    
    @classmethod
    def create_sso_build_status(
        cls,
        submission_id: str,
        workflow_id: str,
        release_id: int,
        job_name: str,
        service_name: Optional[str] = None,
        job_id: Optional[str] = None,
        build_status: str = 'BUILDING'
    ) -> Dict:
        """
        创建构建状态记录
        
        Args:
            submission_id: SSO 提交ID
            workflow_id: 工作流ID
            release_id: SSO 发布ID
            job_name: Jenkins Job 名称
            service_name: 服务名称（可选）
            job_id: Jenkins Job ID（可选）
            build_status: 构建状态（默认 BUILDING）
            
        Returns:
            构建状态记录字典
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 生成构建ID
        build_id = f"BUILD-{int(time.time())}-{str(uuid.uuid4())[:8].upper()}"
        build_start_time = int(time.time())
        created_at = get_current_timestamp()
        updated_at = created_at
        
        try:
            cursor.execute("""
                INSERT INTO sso_build_status (
                    build_id, submission_id, workflow_id, release_id,
                    job_name, service_name, job_id, build_status,
                    build_start_time, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                build_id,
                submission_id,
                workflow_id,
                release_id,
                job_name,
                service_name,
                job_id,
                build_status,
                build_start_time,
                created_at,
                updated_at
            ))
            
            conn.commit()
            logger.info(f"✅ 构建状态记录已创建 - Build ID: {build_id}, Release ID: {release_id}, Job: {job_name}")
            
            return {
                'build_id': build_id,
                'submission_id': submission_id,
                'workflow_id': workflow_id,
                'release_id': release_id,
                'job_name': job_name,
                'service_name': service_name,
                'job_id': job_id,
                'build_status': build_status,
                'build_start_time': build_start_time,
                'created_at': created_at,
                'updated_at': updated_at
            }
        except Exception as e:
            logger.error(f"创建构建状态记录失败: {e}", exc_info=True)
            raise
    
    @classmethod
    def update_sso_build_status(
        cls,
        build_id: str,
        status: str,
        build_detail: Optional[Dict] = None
    ):
        """
        更新构建状态
        
        Args:
            build_id: 构建ID
            status: 构建状态 (BUILDING/SUCCESS/FAILURE/ABORTED)
            build_detail: 构建详情（可选）
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        updated_at = get_current_timestamp()
        update_fields = ["build_status = ?", "updated_at = ?"]
        values = [status, updated_at]
        
        # 如果构建完成，记录结束时间
        if status in ['SUCCESS', 'FAILURE', 'ABORTED']:
            update_fields.append("build_end_time = ?")
            values.append(int(time.time()))
        
        if build_detail:
            update_fields.append("build_detail = ?")
            values.append(json.dumps(build_detail, ensure_ascii=False))
            
            # 从构建详情中提取 job_name
            if 'jobName' in build_detail:
                update_fields.append("job_name = ?")
                values.append(build_detail['jobName'])
        
        values.append(build_id)
        
        try:
            cursor.execute(f"""
                UPDATE sso_build_status 
                SET {', '.join(update_fields)}
                WHERE build_id = ?
            """, values)
            
            conn.commit()
            logger.debug(f"构建状态已更新 - Build ID: {build_id}, 状态: {status}")
        except Exception as e:
            logger.error(f"更新构建状态失败: {e}", exc_info=True)
            raise
    
    @classmethod
    def get_pending_notifications(cls, limit: Optional[int] = 100) -> List[Dict]:
        """
        获取待通知的构建状态（构建完成但未通知，优化查询性能）
        
        Args:
            limit: 限制返回数量（默认100，避免一次返回过多数据）
        
        Returns:
            构建状态记录列表
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 使用索引优化的查询（build_status, notified, build_end_time 复合索引）
        sql = """
            SELECT * FROM sso_build_status 
            WHERE build_status IN ('SUCCESS', 'FAILURE', 'ABORTED')
            AND notified = 0
            ORDER BY build_end_time ASC
        """
        
        if limit:
            sql += " LIMIT ?"
            cursor.execute(sql, (limit,))
        else:
            cursor.execute(sql)
        
        rows = cursor.fetchall()
        results = []
        
        for row in rows:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('build_detail'):
                try:
                    data['build_detail'] = json.loads(data['build_detail'])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(data)
        
        return results
    
    @classmethod
    def mark_build_notified(cls, build_id: str):
        """
        标记构建已通知
        
        Args:
            build_id: 构建ID
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        notification_time = int(time.time())
        updated_at = get_current_timestamp()
        
        try:
            cursor.execute("""
                UPDATE sso_build_status 
                SET notified = 1, notification_time = ?, updated_at = ?
                WHERE build_id = ?
            """, (notification_time, updated_at, build_id))
            
            conn.commit()
            logger.debug(f"构建已标记为已通知 - Build ID: {build_id}")
        except Exception as e:
            logger.error(f"标记构建已通知失败: {e}", exc_info=True)
            raise
    
    # ========== Jenkins 相关数据库操作方法 ==========
    
    @classmethod
    def create_jenkins_build(
        cls,
        workflow_id: str,
        job_name: str,
        build_number: Optional[int] = None,
        job_url: Optional[str] = None,
        build_status: str = 'BUILDING',
        build_parameters: Optional[Dict] = None
    ) -> Dict:
        """
        创建 Jenkins 构建记录
        
        Args:
            workflow_id: 工作流ID
            job_name: Jenkins Job 名称
            build_number: Jenkins 构建编号（可选）
            job_url: Jenkins Job URL（可选）
            build_status: 构建状态（默认 BUILDING）
            build_parameters: 构建参数（可选，JSON 格式）
            
        Returns:
            Jenkins 构建记录字典
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 生成构建ID
        build_id = f"JENKINS-{int(time.time())}-{str(uuid.uuid4())[:8].upper()}"
        build_start_time = int(time.time())
        created_at = get_current_timestamp()
        updated_at = created_at
        
        try:
            cursor.execute("""
                INSERT INTO jenkins_builds (
                    build_id, workflow_id, job_name, job_url, build_number,
                    build_status, build_start_time, build_parameters,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                build_id,
                workflow_id,
                job_name,
                job_url,
                build_number,
                build_status,
                build_start_time,
                json.dumps(build_parameters, ensure_ascii=False) if build_parameters else None,
                created_at,
                updated_at
            ))
            
            conn.commit()
            logger.info(f"✅ Jenkins 构建记录已创建 - Build ID: {build_id}, Job: {job_name}, Build: {build_number}")
            
            return {
                'build_id': build_id,
                'workflow_id': workflow_id,
                'job_name': job_name,
                'job_url': job_url,
                'build_number': build_number,
                'build_status': build_status,
                'build_start_time': build_start_time,
                'build_parameters': build_parameters,
                'created_at': created_at,
                'updated_at': updated_at
            }
        except Exception as e:
            logger.error(f"创建 Jenkins 构建记录失败: {e}", exc_info=True)
            raise
    
    @classmethod
    def update_jenkins_build(cls, build_id: str, **kwargs) -> bool:
        """
        更新 Jenkins 构建记录
        
        Args:
            build_id: 构建ID
            **kwargs: 要更新的字段
        
        Returns:
            是否成功
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        updated_at = get_current_timestamp()
        update_fields = ["updated_at = ?"]
        values = [updated_at]
        
        # 处理特殊字段
        if 'build_parameters' in kwargs and kwargs['build_parameters']:
            kwargs['build_parameters'] = json.dumps(kwargs['build_parameters'], ensure_ascii=False)
        
        # 构建 SQL 更新语句
        allowed_fields = [
            'job_name', 'job_url', 'build_number', 'build_status',
            'build_start_time', 'build_end_time', 'build_duration',
            'build_console_output', 'build_parameters'
        ]
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if len(update_fields) == 1:  # 只有 updated_at
            logger.warning(f"没有有效的更新字段 - Build ID: {build_id}")
            return False
        
        values.append(build_id)
        
        try:
            cursor.execute(f"""
                UPDATE jenkins_builds 
                SET {', '.join(update_fields)}
                WHERE build_id = ?
            """, values)
            
            conn.commit()
            logger.debug(f"Jenkins 构建记录已更新 - Build ID: {build_id}, 更新字段: {list(kwargs.keys())}")
            return True
        except Exception as e:
            logger.error(f"更新 Jenkins 构建记录失败 - Build ID: {build_id}, 错误: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def get_jenkins_build_by_workflow(cls, workflow_id: str) -> Optional[Dict]:
        """
        根据工作流ID获取 Jenkins 构建记录
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            Jenkins 构建记录字典，如果不存在返回 None
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM jenkins_builds 
            WHERE workflow_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (workflow_id,))
        
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('build_parameters'):
                try:
                    data['build_parameters'] = json.loads(data['build_parameters'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data
        
        return None
    
    @classmethod
    def get_jenkins_build_by_id(cls, build_id: str) -> Optional[Dict]:
        """
        根据构建ID获取 Jenkins 构建记录
        
        Args:
            build_id: 构建ID
            
        Returns:
            Jenkins 构建记录字典，如果不存在返回 None
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM jenkins_builds 
            WHERE build_id = ?
        """, (build_id,))
        
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('build_parameters'):
                try:
                    data['build_parameters'] = json.loads(data['build_parameters'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data
        
        return None
    
    @classmethod
    def get_jenkins_build_by_job_and_number(cls, workflow_id: str, job_name: str, build_number: int) -> Optional[Dict]:
        """
        根据工作流ID、Job名称和构建编号获取 Jenkins 构建记录
        
        Args:
            workflow_id: 工作流ID
            job_name: Jenkins Job 名称
            build_number: 构建编号
            
        Returns:
            Jenkins 构建记录字典，如果不存在返回 None
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM jenkins_builds 
            WHERE workflow_id = ? AND job_name = ? AND build_number = ?
            LIMIT 1
        """, (workflow_id, job_name, build_number))
        
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('build_parameters'):
                try:
                    data['build_parameters'] = json.loads(data['build_parameters'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data
        
        return None
    
    @classmethod
    def get_pending_jenkins_notifications(cls, limit: Optional[int] = 100) -> List[Dict]:
        """
        获取待通知的 Jenkins 构建（构建完成但未通知，优化查询性能）
        
        Args:
            limit: 限制返回数量（默认100，避免一次返回过多数据）
        
        Returns:
            Jenkins 构建记录列表
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        # 使用索引优化的查询（build_status, notified, build_end_time 复合索引）
        sql = """
            SELECT * FROM jenkins_builds 
            WHERE build_status IN ('SUCCESS', 'FAILURE', 'ABORTED', 'UNSTABLE')
            AND notified = 0
            ORDER BY build_end_time ASC
        """
        
        if limit:
            sql += " LIMIT ?"
            cursor.execute(sql, (limit,))
        else:
            cursor.execute(sql)
        
        rows = cursor.fetchall()
        results = []
        
        for row in rows:
            data = dict(row)
            # 解析 JSON 字段
            if data.get('build_parameters'):
                try:
                    data['build_parameters'] = json.loads(data['build_parameters'])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(data)
        
        return results
    
    @classmethod
    def mark_jenkins_build_notified(cls, build_id: str) -> bool:
        """
        标记 Jenkins 构建已通知
        
        Args:
            build_id: 构建ID
        
        Returns:
            是否成功
        """
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        notification_time = int(time.time())
        updated_at = get_current_timestamp()
        
        try:
            cursor.execute("""
                UPDATE jenkins_builds 
                SET notified = 1, notification_time = ?, updated_at = ?
                WHERE build_id = ?
            """, (notification_time, updated_at, build_id))
            
            conn.commit()
            logger.debug(f"Jenkins 构建已标记为已通知 - Build ID: {build_id}")
            return True
        except Exception as e:
            logger.error(f"标记 Jenkins 构建已通知失败: {e}", exc_info=True)
            return False
