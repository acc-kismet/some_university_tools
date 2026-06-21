# some_university_tools

自用脚本集合，按独立项目拆分，各项目自带 `utils` / `logic`，不共用顶层工具目录。

## 一些感想
学校官网的抢课逻辑:
1. 获取课程列表（在非拥挤时间，响应时间在10s左右
2. 发起请求
正常进入官网抢课的话，都是因为拉取课程列表导致的时间过长，然后不断的刷新，导致后端一直很难响应这个接口（这个点在客户端不一样，客户端也许使用了本地的缓存机制？这个不得而知），因此主要拼的根本不是请求的时间，而是看怎么更快的获取需要抢的课，直接提前拉下数据即可，课程id是不变的

## 项目列表

| 目录 | 语言 | 功能 |
|------|------|------|
| [auth](./auth/) | Python | IDS 统一认证登录（MFA 终端交互） |
| [enroll](./enroll/) | Python | 教务自动选课/抢课 |
| [ics](./ics/) | Python | 课表拉取并生成 ICS |
| [course-replay](./course-replay/) | 油猴 JS | 教学平台回放下载 |

## 目录结构

```
some_university_tools/
├── auth/              # 认证：api / logic / utils
├── enroll/            # 抢课脚本
│   ├── cmd/main.py    # 入口
│   ├── config.py      # 项目常量（API 地址等）
│   └── config_dir/    # 个人配置与运行产物（git 忽略）
├── ics/               # 导出课表脚本
│   ├── cmd/main.py
│   ├── config.py
│   └── config_dir/
└── course-replay/     # 回放权限脚本
```

## 使用方式

各 Python 项目运行时需将 `some_university_tools/` 加入 `sys.path`（各 `cmd/main.py` 已处理），认证统一：

```python
from auth.api import login, login_or_exit, LoginError, session_from_cookies
```

登录缓存由调用方指定目录，通常放在 `config_dir/cache/`：

- `session.json` — Cookie 缓存
- `browser_fingerprint` — 浏览器指纹

## 敏感文件与 `.gitignore`

根目录 [`.gitignore`](./.gitignore) 已忽略整个 `config_dir/`（仅保留 `*.example` 模板）：

- `config_dir/myData.jsonc`、`config_dir/config.jsonc`（用户配置，含账号密码）
- `config_dir/cache/`（登录 Cookie / 指纹）
- `config_dir/allCourseInfo.json`、`config_dir/keyCourseInfo.json`、`config_dir/courses.ics`（运行产物）

**只提交 `config_dir/*.example` 模板，不要提交上述文件。**

## 参数与接口文档

| 项目 | 文档 |
|------|------|
| 抢课 | [enroll/README.md](./enroll/README.md) — `myData.jsonc` 各字段、三个教务 API、`BASE_FORM` |
| 课表 | [ics/README.md](./ics/README.md) — `config.jsonc` 各字段、日程 API、ICS 字段映射 |
shou| 认证 | [auth/README.md](./auth/README.md) — 登录流程与 `auth.login` 参数 |

## 日志与调试

| 模块 | 日志前缀 | 级别环境变量 | 文件环境变量 |
|------|----------|--------------|--------------|
| auth | `[认证]` `[MFA]` | `AUTH_LOG_LEVEL` | `AUTH_LOG_FILE` |
| enroll | `[抢课]` | `ENROLL_LOG_LEVEL` | `ENROLL_LOG_FILE` |
| ics | `[课表]` | `ICS_LOG_LEVEL` | `ICS_LOG_FILE` |

通用：`LOG_LEVEL` 对上述模块均生效。

HTTP 跳转追踪（仅 auth）：`AUTH_DEBUG=1`

## 快速入口

```bash
# 抢课
cd enroll && pip install -r requirements.txt
cp config_dir/myData.jsonc.example config_dir/myData.jsonc
手机python cmd/main.py

# 课表
cd ics && pip install -r requirements.txt
cp config_dir/config.jsonc.example config_dir/config.jsonc
python cmd/main.py

# 回放：将 course-replay/course-helper.js 粘贴到 Tampermonkey
```

## 免责声明

仅供学习研究，使用者需自行承担后果并遵守学校规定。
