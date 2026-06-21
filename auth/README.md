# IDS 统一认证 (`auth`)

封装 IDS 统一认证完整登录流程，供 `enroll`、`ics` 等项目调用。

## 结构

```
auth/
├── api/              # 对外 API：login, login_or_exit, LoginError, ...
├── logic/
│   ├── flow.py       # 主流程
│   ├── mfa.py        # 二次认证（终端交互）
│   ├── target.py     # entry_url / CAS service 解析
│   ├── verify.py     # Session 有效性探测
│   └── constants.py
└── utils/
    ├── http_trace.py # AUTH_DEBUG=1 跳转追踪
    ├── log.py        # 默认步骤日志
    ├── session.py    # Session 与 Cookie 缓存
    ├── crypto.py     # 密码加密、表单解析
    └── fingerprint.py
```

## 快速开始

```python
from pathlib import Path
from auth.api import login, LoginError

session = login(
    username="学号",
    password="密码",
    entry_url="http://jw.hitsz.edu.cn/casLogin",
    cache_dir=Path("config_dir/cache"),
    mfa_method="sms",
    trust_device=True,
    use_session_cache=True,
    save_session=True,
)
```

## `login()` 参数

| 参数 | 类型 | 默认值 | 含义 |
|------|------|--------|------|
| `username` | str | — | 学号 |
| `password` | str | — | 统一认证密码 |
| `entry_url` | str | — | 目标站点 CAS 入口（见下） |
| `verify` | callable / str / None | `None` | Session 有效性探测；默认 jw 域用课表 JSON 接口 |
| `mfa_method` | str | `"sms"` | 二次验证方式，见下表 |
| `trust_device` | bool | `True` | MFA 是否勾选「信任此设备」 |
| `use_session_cache` | bool | `True` | 是否读取 `cache_dir/session.json` |
| `save_session` | bool | `True` | 成功后是否写入 `cache_dir/session.json` |
| `cache_dir` | Path | — | 登录缓存目录（必填；含 `session.json` 与 `browser_fingerprint`） |
| `log_fn` | callable | 内置 logger | 步骤日志回调 |

### `mfa_method` 可选值

| 值 | 含义 |
|----|------|
| `sms` | 短信验证码 |
| `app` | 哈工大 APP 验证码 |
| `email` | 邮箱验证码 |
| `otp` | 安全令牌 |

## entry_url

传入**目标站点入口**，未登录时访问会 302 到 IDS：

```
http://jw.hitsz.edu.cn/casLogin
```

## 登录流程

```
entry_url → IDS 密码 → MFA 终端验证码 → ticket 回调 → Session
```

## 日志

默认输出带 `[认证]` / `[MFA]` 前缀的步骤日志。

- 级别：`AUTH_LOG_LEVEL` 或 `LOG_LEVEL`
- 文件：`AUTH_LOG_FILE`

## 调试

```bash
AUTH_DEBUG=1 python cmd/main.py   # 在 ics/ 目录
```

会额外打印 HTTP 跳转细节。

## 缓存文件

由调用方传入 `cache_dir`，各项目默认使用 `config_dir/cache/`：

| 文件 | 说明 |
|------|------|
| `session.json` | 登录 Cookie 缓存 |
| `browser_fingerprint` | 浏览器指纹 MD5 |

## 依赖

```
requests beautifulsoup4 pycryptodome
```

滑块验证需：`playwright`
