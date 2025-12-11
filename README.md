# Telegram Workflows 工作流机器人

基于Telegram Bot的审批工作流系统，实现用户提交信息、群组展示、审批流程、数据同步、SSO 系统集成以及 Jenkins 构建集成等功能。

## 功能特性

- ✅ 用户通过表单提交工作流信息（支持多项目、多环境、多服务选择）
- ✅ 信息自动发布到指定群组
- ✅ @提醒审批人进行审批
- ✅ 审批人进行审批操作（通过/拒绝）
- ✅ 审批结果同步到外部API接口
- ✅ **SSO 系统集成**：审批通过后自动提交到 SSO 系统进行构建部署
- ✅ **构建状态监控**：自动监控 SSO 构建状态并发送 Telegram 通知
- ✅ **Jenkins 集成**：审批通过后自动触发 Jenkins 构建任务
- ✅ **Jenkins 构建监控**：自动监控 Jenkins 构建状态并发送 Telegram 通知
- ✅ **SQLite 数据库存储**：持久化存储工作流数据、SSO 提交记录、Jenkins 构建记录和构建状态
- ✅ **配置管理**：支持从数据库读取配置，首次启动自动初始化
- ✅ **统一代理配置**：所有模块（Telegram Bot、SSO、API、Jenkins）使用相同的代理配置

## 安装部署

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置文件设置

#### 2.1 基础配置（`config/settings.py`）

在 `config/settings.py` 中配置以下参数：

**Telegram Bot 配置**：
```python
DEFAULT_BOT_TOKEN = "你的 BOT_TOKEN"
DEFAULT_APPROVER_USERNAME = "审批人用户名"  # 例如: "xxxxx"
```

**SSO 配置**（可选，如果需要 SSO 集成）：
```python
DEFAULT_SSO_ENABLED: bool = True
DEFAULT_SSO_URL: str = "https://xxxxx"
DEFAULT_SSO_AUTH_TOKEN: str = "你的 SSO Auth Token"
DEFAULT_SSO_AUTHORIZATION: str = "Bearer 你的 Authorization"
```

**外部 API 配置**（可选，如果需要同步到外部系统）：
```python
API_BASE_URL: str = "外部API地址"
API_ENDPOINT: str = "/workflows/sync"
API_TOKEN: str = "API认证Token"
```

**全局代理配置**（可选，用于 Telegram Bot，支持有/无用户名密码）：
```python
DEFAULT_PROXY_ENABLED: bool = True
DEFAULT_PROXY_HOST: str = "代理地址"
DEFAULT_PROXY_PORT: int = 8080
DEFAULT_PROXY_USERNAME: str = "代理用户名"  # 可选，无认证代理可不配置
DEFAULT_PROXY_PASSWORD: str = "代理密码"  # 可选，无认证代理可不配置
```

**注意**：全局代理配置用于 Telegram Bot。SSO、API、Jenkins 的代理配置在 `options.json` 中按项目配置。

#### 2.2 项目配置（`scripts/options.json`）

配置项目、环境、服务、群组、Jenkins 和代理信息：

```json
{
  "projects": {
    "EBPAY": {
      "group_ids": [-5036335599],
      "approvers": {
        "usernames": ["bob68888"]
      },
      "ops_usernames": ["ops_user1", "ops_user2"],
      "environments": {
        "UAT": {
          "default_branch": "uat"
        },
        "GRAY-UAT": {
          "default_branch": "uat-gray"
        }
      },
      "services": {
        "UAT": ["pre-admin-export", "pre-adminmanager", "pre-eb-web-api"],
        "GRAY-UAT": ["gray-pre-admin-export", "gray-pre-adminmanager"]
      },
      "jenkins": {
        "enabled": true,
        "url": "https://jenkins.example.com",
        "username": "",
        "api_token": "your_jenkins_api_token_here",
        "max_concurrent_builds": 5
      },
      "proxy": {
        "enabled": true,
        "type": "socks5",
        "host": "proxy.example.com",
        "port": 8080,
        "username": "",
        "password": ""
      }
    },
    "项目B": {
      "group_ids": [-1001234567890],
      "approvers": {
        "usernames": []
      },
      "ops_usernames": [],
      "environments": {
        "dev": {
          "default_branch": "main"
        },
        "test": {
          "default_branch": "main"
        }
      },
      "services": {
        "dev": ["服务B1", "服务B2"],
        "test": ["服务B1", "服务B2"]
      },
      "jenkins": {
        "enabled": false,
        "url": "",
        "username": "",
        "api_token": ""
      },
      "proxy": {
        "enabled": false,
        "type": "socks5",
        "host": "",
        "port": 0,
        "username": "",
        "password": ""
      }
    }
  }
}
```

**配置说明**：
- `group_ids`: 该项目的 Telegram 群组ID列表（支持多个群组）
- `approvers`: 审批人配置
  - `usernames`: 审批人用户名列表（支持多个）
- `ops_usernames`: OPS 用户列表（支持多个），构建失败时会 @ 这些用户，同时这些用户也可以审批工作流
- `environments`: 环境配置（支持两种格式）
  - **对象格式（推荐）**：`{"UAT": {"default_branch": "uat"}, ...}` - 每个环境可配置独立的默认分支
  - **数组格式（向后兼容）**：`["UAT", "GRAY-UAT"]` - 所有环境使用相同的默认分支（从全局 `default_branch` 获取）
- `services`: 一个对象，key 是环境名称，value 是该环境对应的服务列表
- `jenkins`: Jenkins 配置（按项目区分）
  - `enabled`: 是否启用该项目的 Jenkins 集成
  - `url`: Jenkins 服务器地址
  - `username`: Jenkins 用户名（可选，如果使用 Token 认证可以留空）
  - `api_token`: Jenkins API Token（在 Jenkins 用户设置中生成）
  - `max_concurrent_builds`: 最大并发构建数（可选，默认不限制）
- `proxy`: 代理配置（按项目区分，用于该项目的 SSO、API、Jenkins 请求）
  - `enabled`: 是否启用该项目的代理
  - `type`: 代理类型（socks5/socks5h/http/https，默认 socks5）
  - `host`: 代理服务器地址
  - `port`: 代理服务器端口
  - `username`: 代理用户名（可选，无认证代理可不配置）
  - `password`: 代理密码（可选，无认证代理可不配置）

**重要**：
- 每个项目可以配置独立的 Jenkins 服务器和代理
- 不同项目可以使用不同的 Jenkins 实例和代理设置
- 如果项目未配置 `jenkins` 或 `proxy`，则使用默认值（enabled: false）

### 3. 初始化数据库

运行初始化脚本：

```bash
python3 scripts/init_db.py
```

初始化脚本会：
- 创建 SQLite 数据库（`data/workflows.db`）
- 从 `scripts/init_db.py` 中的默认值初始化配置到数据库
- 从 `scripts/options.json` 导入项目配置到数据库

**重要**：首次运行前必须执行初始化脚本，否则 Bot 无法启动。

### 4. 运行Bot

```bash
python3 bot/bot.py
```

或

```bash
python -m bot.bot
```

## 使用说明

### 用户提交工作流

1. 在私聊中发送 `/start` 开始
2. 发送 `/deploy_build` 启动表单提交流程
3. 按步骤选择：
   - 选择项目
   - 选择环境（选择后会自动设置该环境对应的默认分支）
   - 选择分支（可使用默认分支或自定义输入）
   - 选择服务（支持多选）
   - 输入发版 hash（多个服务时，hash 与服务一一对应）
   - 输入发版内容
4. 确认提交后，信息会自动发布到对应项目的群组并@审批人

### 审批流程

1. 审批人或 OPS 用户在群组中看到工作流消息
2. 点击"✅ 通过"或"❌ 拒绝"按钮进行审批
   - **审批人**：`approvers.usernames` 中配置的用户可以审批
   - **OPS 用户**：`ops_usernames` 中配置的用户也可以审批（用于运维场景）
3. 审批完成后：
   - ✅ 提交用户会在Telegram中收到审批结果通知
   - ✅ 群组消息会更新显示审批结果
   - ✅ 如果配置了外部API，Bot会自动调用外部接口同步审批结果
   - ✅ **如果启用了 SSO 集成，审批通过后会自动提交到 SSO 系统进行构建部署**
   - ✅ **如果启用了 Jenkins 集成，审批通过后会自动触发 Jenkins 构建任务**

### SSO 集成流程

当审批通过且 SSO 集成已启用时：

1. **自动提交到 SSO**：
   - 解析工作流数据（项目、环境、服务、hash等）
   - 获取 SSO Job IDs
   - 转换为 SSO 工单格式
   - 提交到 SSO 系统

2. **构建状态监控**：
   - 自动获取发布 ID
   - 后台监控构建状态（轮询）
   - 构建完成后自动发送 Telegram 通知

3. **通知发送**：
   - 提交成功通知
   - 构建完成通知（成功/失败/终止）
   - 所有通知都会发送到原始工作流的群组

### Jenkins 集成流程

当审批通过且 Jenkins 集成已启用时：

1. **自动触发 Jenkins 构建**：
   - 解析工作流数据（项目、环境、服务、hash等）
   - 直接使用 `services` 中的值作为 Jenkins Job 名称
   - 为每个服务触发对应的 Jenkins Job 构建
   - 传递构建参数（WORKFLOW_ID、PROJECT、ENVIRONMENT、SERVICE、GIT_HASH、APPROVER）

2. **构建状态监控**：
   - 后台监控每个构建的状态（轮询）
   - 构建完成后自动发送 Telegram 通知

3. **通知发送**：
   - 构建完成后发送简洁的结果通知（成功/失败/终止/不稳定）
   - 构建失败时会自动 @ 项目配置的 `ops_usernames` 中的用户
   - 通知格式：
     - 成功：`✅ 构建成功\n- {job_name} 服务构建完成。`
     - 失败：`❌ 构建失败\n- {job_name} 服务构建失败。\n@{ops_user1} @{ops_user2}\n请让运维ops 协助查看错误日志`
   - 所有通知都会发送到原始工作流的群组

**注意**：
- Service 名称直接作为 Jenkins Job 名称，无需映射配置
- Services 和 Hashes 一一对应，通过索引获取对应的 hash
- 支持多个服务同时构建，每个服务独立监控和通知

## 数据库存储

系统使用 SQLite 数据库（`data/workflows.db`）持久化存储：

- **workflows**: 工作流记录
- **sso_submissions**: SSO 提交记录
- **sso_build_status**: SSO 构建状态记录
- **jenkins_builds**: Jenkins 构建记录
- **app_config**: 应用配置（从 init_db.py 初始化）
- **project_options**: 项目配置（从 options.json 导入）

数据保留 60 天，过期数据会自动清理。

## 配置管理

### 配置方式

配置存储在数据库中，首次启动时从代码中的默认值自动初始化：

1. **首次启动**：从 `config/settings.py` 的默认值写入数据库
2. **后续修改**：可以通过数据库直接修改，或修改 `settings.py` 后重启（会自动同步）

### 配置项说明

**基础配置**：
- `BOT_TOKEN`: Telegram Bot Token
- `APPROVER_USERNAME`: 审批人用户名（全局默认，可在项目配置中覆盖）
- `GROUP_IDS`: 群组ID（从 `options.json` 自动读取）

**项目配置**（在 `scripts/options.json` 中）：
- `approvers.usernames`: 项目审批人用户名列表（支持多个）
- `ops_usernames`: OPS 用户列表（支持多个）
  - 构建失败时会 @ 这些用户
  - 这些用户也可以审批工作流
- `environments`: 环境配置
  - **对象格式**：`{"UAT": {"default_branch": "uat"}, ...}` - 每个环境可配置独立的默认分支
  - **数组格式**：`["UAT", "GRAY-UAT"]` - 向后兼容，使用全局 `default_branch`

**SSO 配置**：
- `SSO_ENABLED`: 是否启用 SSO 集成
- `SSO_URL`: SSO 系统 URL
- `SSO_AUTH_TOKEN`: SSO Auth Token
- `SSO_AUTHORIZATION`: SSO Authorization

**Jenkins 配置**（按项目配置，在 `scripts/options.json` 中）：
- 每个项目在 `projects.{项目名}.jenkins` 中配置
- `enabled`: 是否启用该项目的 Jenkins 集成
- `url`: Jenkins 服务器地址
- `username`: Jenkins 用户名（可选）
- `api_token`: Jenkins API Token

**代理配置**（按项目配置，在 `scripts/options.json` 中）：
- 每个项目在 `projects.{项目名}.proxy` 中配置（用于该项目的 SSO、API、Jenkins 请求）
- `enabled`: 是否启用该项目的代理
- `host`: 代理服务器地址
- `port`: 代理服务器端口
- `username`: 代理用户名（可选）
- `password`: 代理密码（可选）

**全局代理配置**（用于 Telegram Bot，在 `scripts/init_db.py` 中）：
- `PROXY_ENABLED`: 是否启用全局代理（用于 Telegram Bot）
- `PROXY_HOST`: 代理主机
- `PROXY_PORT`: 代理端口
- `PROXY_USERNAME`: 代理用户名（可选）
- `PROXY_PASSWORD`: 代理密码（可选）

**外部 API 配置**：
- `API_BASE_URL`: 外部API基础地址
- `API_ENDPOINT`: API同步端点
- `API_TOKEN`: API认证Token

**代理配置**（支持有/无用户名密码）：
- `PROXY_ENABLED`: 是否启用代理
- `PROXY_HOST`: 代理主机
- `PROXY_PORT`: 代理端口
- `PROXY_USERNAME`: 代理用户名（可选，无认证代理可不配置）
- `PROXY_PASSWORD`: 代理密码（可选，无认证代理可不配置）

**注意**：代理配置会被所有模块使用（Telegram Bot、SSO、API、Jenkins），统一管理。

## 项目结构

```
tg_workfolws_bot/
├── config/          # 配置模块
│   ├── settings.py  # 应用配置（默认值）
│   ├── constants.py # 常量定义
│   └── options.json # 项目配置（项目、环境、服务）
├── bot/            # Bot核心模块
│   ├── bot.py      # Bot入口
│   └── handlers.py # 命令处理器
├── workflows/       # 工作流模块
│   └── models.py   # 数据模型和数据库操作
├── handlers/       # 业务处理器模块
│   ├── form_handler.py       # 表单处理
│   ├── submission_handler.py # 提交处理
│   ├── approval_handler.py   # 审批处理（包含 SSO 集成）
│   └── notification_handler.py # 通知处理
├── sso/            # SSO 集成模块
│   ├── config.py         # SSO 配置
│   ├── client.py         # SSO API 客户端
│   ├── data_converter.py # 数据转换器
│   ├── data_format.py    # 数据格式化
│   ├── monitor.py        # 构建状态监控
│   └── notifier.py       # SSO 通知器
├── jenkins_ops/    # Jenkins 集成模块
│   ├── config.py   # Jenkins 配置
│   ├── client.py   # Jenkins API 客户端
│   ├── monitor.py  # 构建状态监控
│   └── notifier.py # Jenkins 通知器
├── api/            # 外部API模块
│   ├── client.py   # API客户端
│   └── sync.py     # 数据同步
├── utils/          # 工具模块
│   ├── logger.py   # 日志工具
│   ├── formatter.py # 消息格式化
│   ├── helpers.py  # 辅助函数
│   └── proxy.py    # 代理配置工具（统一管理所有模块的代理配置）
├── scripts/        # 工具脚本
│   ├── init_db.py  # 数据库初始化脚本（必须运行）
│   └── options.json # 项目配置文件
├── data/           # 数据目录（SQLite数据库）
└── logs/           # 日志目录
```

## 注意事项

- ✅ 使用 SQLite 数据库存储，Bot重启后数据不会丢失
- ✅ **首次启动前必须运行 `python3 scripts/init_db.py` 初始化数据库**
- ✅ 如果配置了外部API，审批结果会自动同步到外部系统
- ✅ 如果启用了 SSO 集成，审批通过后会自动提交到 SSO 系统
- ✅ 如果启用了 Jenkins 集成，审批通过后会自动触发 Jenkins 构建
- ✅ 确保Bot已添加到目标群组并具有发送消息权限
- ✅ 首次启动前请确保 `scripts/options.json` 文件存在且配置正确
- ✅ SSO 集成需要配置 `SSO_AUTH_TOKEN` 和 `SSO_AUTHORIZATION` 才能正常工作
- ✅ **Jenkins 集成按项目配置**：在 `scripts/options.json` 中为每个项目配置 `jenkins` 对象
- ✅ **代理配置按项目区分**：在 `scripts/options.json` 中为每个项目配置 `proxy` 对象（用于该项目的 SSO、API、Jenkins 请求）
- ✅ Service 名称直接作为 Jenkins Job 名称，无需额外映射配置
- ✅ 代理配置支持有/无用户名密码两种方式
- ✅ 不同项目可以使用不同的 Jenkins 服务器和代理设置
- ✅ **OPS 用户支持**：`ops_usernames` 中的用户既可以审批工作流，也会在构建失败时被 @
- ✅ **按环境配置默认分支**：`environments` 支持对象格式，每个环境可配置独立的默认分支
- ✅ **审批权限**：`approvers.usernames` 和 `ops_usernames` 中的用户都可以审批工作流

## 日志

日志文件保存在 `logs/bot.log`，包含：
- 工作流提交和审批记录
- SSO 提交和构建监控记录
- Jenkins 构建触发和监控记录
- 错误和异常信息

## 许可证

MIT
