# Telegram Workflows 工作流机器人

基于Telegram Bot的审批工作流系统，实现用户提交信息、群组展示、审批流程、数据同步以及 SSO 系统集成等功能。

## 功能特性

- ✅ 用户通过表单提交工作流信息（支持多项目、多环境、多服务选择）
- ✅ 信息自动发布到指定群组
- ✅ @提醒审批人进行审批
- ✅ 审批人进行审批操作（通过/拒绝）
- ✅ 审批结果同步到外部API接口
- ✅ **SSO 系统集成**：审批通过后自动提交到 SSO 系统进行构建部署
- ✅ **构建状态监控**：自动监控 SSO 构建状态并发送 Telegram 通知
- ✅ **SQLite 数据库存储**：持久化存储工作流数据、SSO 提交记录和构建状态
- ✅ **配置管理**：支持从数据库读取配置，首次启动自动初始化

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

**代理配置**（可选）：
```python
PROXY_ENABLED: bool = True
PROXY_HOST: str = "代理地址"
PROXY_PORT: int = 端口号
PROXY_USERNAME: str = "代理用户名"
PROXY_PASSWORD: str = "代理密码"
```

#### 2.2 项目配置（`config/options.json`）

配置项目、环境、服务和群组信息：

```json
{
  "projects": {
    "xxxx": {
      "group_ids": [xxxxx],
      "environments": ["UAT", "GRAY-UAT"],
      "services": {
        "UAT": ["xxxxx", "xxxx", "xxxx"],
        "GRAY-UAT": ["xxxxx", "xxxxx"]
      }
    }
  }
}
```

**配置说明**：
- `group_ids`: 该项目的 Telegram 群组ID列表（支持多个群组）
- `environments`: 该项目支持的环境列表
- `services`: 一个对象，key 是环境名称，value 是该环境对应的服务列表

### 3. 初始化数据库

首次运行时会自动：
- 创建 SQLite 数据库（`data/workflows.db`）
- 从 `config/settings.py` 初始化配置到数据库
- 从 `config/options.json` 导入项目配置到数据库

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
   - 选择环境
   - 选择服务（支持多选）
   - 输入发版 hash（多个服务时，hash 与服务一一对应）
   - 输入发版内容
4. 确认提交后，信息会自动发布到对应项目的群组并@审批人

### 审批流程

1. 审批人在群组中看到工作流消息
2. 点击"✅ 通过"或"❌ 拒绝"按钮进行审批
3. 审批完成后：
   - ✅ 提交用户会在Telegram中收到审批结果通知
   - ✅ 群组消息会更新显示审批结果
   - ✅ 如果配置了外部API，Bot会自动调用外部接口同步审批结果
   - ✅ **如果启用了 SSO 集成，审批通过后会自动提交到 SSO 系统进行构建部署**

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

## 数据库存储

系统使用 SQLite 数据库（`data/workflows.db`）持久化存储：

- **workflows**: 工作流记录
- **sso_submissions**: SSO 提交记录
- **sso_build_status**: SSO 构建状态记录
- **app_config**: 应用配置（从 settings.py 初始化）
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
- `APPROVER_USERNAME`: 审批人用户名
- `GROUP_IDS`: 群组ID（从 `options.json` 自动读取）

**SSO 配置**：
- `SSO_ENABLED`: 是否启用 SSO 集成
- `SSO_URL`: SSO 系统 URL
- `SSO_AUTH_TOKEN`: SSO Auth Token
- `SSO_AUTHORIZATION`: SSO Authorization

**外部 API 配置**：
- `API_BASE_URL`: 外部API基础地址
- `API_ENDPOINT`: API同步端点
- `API_TOKEN`: API认证Token

**代理配置**：
- `PROXY_ENABLED`: 是否启用代理
- `PROXY_HOST`: 代理主机
- `PROXY_PORT`: 代理端口
- `PROXY_USERNAME`: 代理用户名
- `PROXY_PASSWORD`: 代理密码

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
├── api/            # 外部API模块
│   ├── client.py   # API客户端
│   └── sync.py     # 数据同步
├── utils/          # 工具模块
│   ├── logger.py   # 日志工具
│   ├── formatter.py # 消息格式化
│   └── helpers.py  # 辅助函数
├── scripts/        # 工具脚本
├── data/           # 数据目录（SQLite数据库）
└── logs/           # 日志目录
```

## 注意事项

- ✅ 使用 SQLite 数据库存储，Bot重启后数据不会丢失
- ✅ 如果配置了外部API，审批结果会自动同步到外部系统
- ✅ 如果启用了 SSO 集成，审批通过后会自动提交到 SSO 系统
- ✅ 确保Bot已添加到目标群组并具有发送消息权限
- ✅ 首次启动前请确保 `config/options.json` 文件存在且配置正确
- ✅ SSO 集成需要配置 `SSO_AUTH_TOKEN` 和 `SSO_AUTHORIZATION` 才能正常工作

## 日志

日志文件保存在 `logs/bot.log`，包含：
- 工作流提交和审批记录
- SSO 提交和构建监控记录
- 错误和异常信息

## 许可证

MIT
