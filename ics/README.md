# 课表 ICS（ics）

登录教务系统，按日期范围拉取日程 JSON，生成 `courses.ics`，可选 SMTP 发送。

## 运行

```bash
cd some_university_tools/ics
pip install -r requirements.txt
cp config_dir/config.jsonc.example config_dir/config.jsonc
python cmd/main.py
```

---

## 一、用户配置 `config_dir/config.jsonc`

配置文件支持 JSONC 注释，各字段含义见 `config.jsonc.example` 内联说明。

| 字段 | 类型 | 默认值 | 含义 |
|------|------|--------|------|
| `username` | string | — | 学号；空或占位符时在终端交互输入 |
| `password` | string | — | 统一认证密码；空时在终端 `getpass` 输入 |
| `mfaMethod` | string | `"sms"` | 二次验证方式：`sms` / `app` / `email` / `otp` |
| `trustDevice` | bool | `true` | MFA 是否勾选「信任此设备」 |
| `useSessionCache` | bool | `true` | 是否读取 `config_dir/cache/session.json` |
| `saveSession` | bool | `true` | 登录成功后是否写入 `config_dir/cache/session.json` |
| `startDate` | string | — | 拉取起始日期 `YYYY-MM-DD`；缺省用 `config.py` 的 `START_DATE` |
| `endDate` | string | — | 拉取结束日期 `YYYY-MM-DD`；缺省用 `config.py` 的 `END_DATE` |
| `sendMail` | string/bool | `"prompt"` | 邮件：`prompt` 终端询问 / `true` 发送 / `false` 跳过 |
| `logLevel` | string | `"INFO"` | 日志级别 |
| `logFile` | string | — | 可选，日志文件路径 |

---

## 二、代码常量 `config.py`

| 常量 | 示例值 | 含义 |
|------|--------|------|
| `START_DATE` | `2025-06-22` | 默认拉取起始日（学期初，需按学期修改） |
| `END_DATE` | `2026-02-01` | 默认拉取结束日 |
| `ENTRY_URL` | `http://jw.hitsz.edu.cn/casLogin` | CAS 入口，传给 `auth.login` |
| `SCHEDULE_QUERY_URL` | `http://jw.hitsz.edu.cn/component/queryrcxxlist` | 单日日程查询接口 |
| `LOCATION_PREFIX` | `哈尔滨工业大学深圳校区` | ICS 地点前缀，与 `NR` 拼接 |
| `TIMEZONE` | `Asia/Shanghai` | ICS 事件时区 |
| `REMIND_MINUTES` | `15` | 预留：当前未写入 ICS 提醒字段 |

---

## 三、教务 HTTP 接口

### 1. 单日日程查询 — `POST /component/queryrcxxlist`

**用途**：按某一天拉取该日所有日程条目；`cmd/main.py` 对日期范围内每一天各请求一次。

**请求体**：

| 字段 | 类型 | 含义 |
|------|------|------|
| `rcrq` | string | 查询日期，`YYYY-MM-DD` |

**响应**：JSON **数组**，每个元素为一条日程记录。

**记录字段（脚本使用）**：

| 字段 | 含义 | 示例 |
|------|------|------|
| `BT` | 标题，内含时间段 | `"高等数学 8:00-9:40"` |
| `SJ` | 日期 | `"2025-09-01"` |
| `NR` | 地点/教室（可选） | `"T3201"` |

**时间解析规则**（`save_as_ics.py`）：

- 从 `BT` 中用正则提取 `H:MM-H:MM`（如 `8:00-9:40`）
- 结合 `SJ` 的日期生成 ICS 事件起止
- 无法解析时间的记录会跳过并打日志

---

## 四、ICS 生成

| 项目 | 说明 |
|------|------|
| 输出文件 | `config_dir/courses.ics` |
| 事件名称 | 原始 `BT` 全文 |
| 事件地点 | `LOCATION_PREFIX` + `NR`（`NR` 为空则不含地点） |
| 时区 | `TIMEZONE`（默认 `Asia/Shanghai`） |

---

## 五、邮件发送（可选）

运行结束时根据 `sendMail` 决定是否发信。SMTP 配置**不在配置文件内**，运行时终端输入：

| 输入项 | 含义 |
|--------|------|
| 发送邮箱 | SMTP 登录账号 |
| SMTP 授权码 | 非登录密码，邮箱服务商生成 |
| 接收邮箱 | 附件接收地址 |

固定使用 QQ 邮箱 SMTP：`smtp.qq.com:465`（SSL）。

---

## 六、认证相关（共用 `auth`）

与 enroll 相同，参见 [auth/README.md](../auth/README.md)。ICS 使用的参数：

| 参数 | 来源 |
|------|------|
| `entry_url` | `config.py` → `ENTRY_URL` |
| `mfa_method` | `config_dir/config.jsonc` → `mfaMethod` |
| `trust_device` | `config_dir/config.jsonc` → `trustDevice` |
| `use_session_cache` / `save_session` | `config_dir/config.jsonc` 对应字段 |
| `cache_dir` | `config_dir/cache/`（`session.json`、`browser_fingerprint`） |

Session 缓存目录：`config_dir/cache/`

---

## 七、环境变量

| 变量 | 作用 |
|------|------|
| `ICS_LOG_LEVEL` / `LOG_LEVEL` | 日志级别 |
| `ICS_LOG_FILE` | 日志输出文件 |
| `AUTH_DEBUG` | 登录 HTTP 跳转追踪 |

---

## 八、目录结构

```
ics/
├── cmd/main.py
├── config.py
├── config_dir/
│   ├── config.jsonc.example
│   ├── config.jsonc       # 个人配置（git 忽略）
│   ├── courses.ics       # 输出（git 忽略）
│   └── cache/            # session.json、browser_fingerprint（git 忽略）
├── logic/
│   ├── config_loader.py
│   ├── runner.py
│   ├── load_data.py
│   ├── save_as_ics.py
│   └── send_email.py
└── utils/
    ├── log.py
    └── paths.py
```
