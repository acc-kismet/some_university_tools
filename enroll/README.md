# 自动选课（enroll）

依赖 `auth` 登录教务系统，调用选课接口拉取课程列表或提交抢课。

## 运行

```bash
cd some_university_tools/enroll
pip install -r requirements.txt
cp config_dir/myData.jsonc.example config_dir/myData.jsonc
python cmd/main.py
```

---

## 一、用户配置 `config_dir/myData.jsonc`

配置文件支持 JSONC 注释，各字段含义见 `myData.jsonc.example` 内联说明。

| 字段 | 类型 | 默认值 | 含义 |
|------|------|--------|------|
| `username` | string | — | 学号。与 `password` 一起用于 IDS 登录 |
| `password` | string | — | 统一认证密码 |
| `cookies` | object | `{}` | 非空时跳过 IDS 登录，直接用 Cookie 访问教务（键值对同浏览器 Cookie） |
| `courseType` | string | — | 选课类型中文名，见下表「选课类型映射」 |
| `selectedCourseIds` | string[] | `[]` | 要抢的课程任务 ID（来自 `config_dir/keyCourseInfo.json` 或 `allCourseInfo.json` 的 `id`） |
| `runMode` | string | `"auto"` | 运行模式：`auto` / `enroll` / `export` |
| `mfaMethod` | string | `"sms"` | 二次验证方式，传给 `auth.login`：`sms` / `app` / `email` / `otp` |
| `trustDevice` | bool | `true` | MFA 是否勾选「信任此设备」 |
| `useSessionCache` | bool | `true` | 是否读取 `config_dir/cache/session.json` 跳过重复登录 |
| `saveSession` | bool | `true` | 登录成功后是否写入 `config_dir/cache/session.json` |
| `logLevel` | string | `"INFO"` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `logFile` | string | — | 可选，日志文件路径 |

### `runMode` 行为

| 值 | 行为 |
|----|------|
| `auto` | 有有效 `selectedCourseIds` → 抢课；否则 → 导出课程列表 |
| `enroll` | 强制抢课（无有效 ID 时报错） |
| `export` | 强制导出 `config_dir/allCourseInfo.json` + `config_dir/keyCourseInfo.json` |

---

## 二、代码常量 `config.py`

| 常量 | 值 | 含义 |
|------|-----|------|
| `ENTRY_URL` | `http://jw.hitsz.edu.cn/casLogin` | CAS 入口，传给 `auth.login` |
| `JW_BASE` | `http://jw.hitsz.edu.cn` | 教务 API 基址（内网 http） |
| `MAX_ENROLL_ATTEMPTS` | `10` | 单门课最大重试次数 |
| `ENROLL_INTERVAL_SEC` | `3` | 抢课失败后的重试间隔（秒） |
| `REQUEST_TIMEOUT_SEC` | `20` | HTTP 请求超时（秒） |
| `DEFAULT_PAGE_SIZE` | `15` | 首次探测课程总数时的分页大小 |

### 选课类型映射 `COURSE_TYPE_MAP`

| 界面名称 | 接口代码 `p_xkfsdm` |
|----------|---------------------|
| 限选 | `xx-b-b` |
| 必修 | `bx-b-b` |
| 跨专业课程体系 | `sx-b-b` |
| 文理通识 | `tsk-b-b` |
| MOOC | `mooc-b-b` |

---

## 三、教务 HTTP 接口

所有接口均需已登录 Session（Cookie）。请求体为 `application/x-www-form-urlencoded`，基础字段来自 `BASE_FORM`。

### 1. 查询学期 — `POST /Xsxk/queryXkdqXnxq`

**用途**：初始化当前学期与选课学期，结果写入后续请求的表单。

**额外字段**（相对 `BASE_FORM`）：

| 字段 | 抢课脚本取值 | 含义 |
|------|--------------|------|
| `p_sfhlctkc` | `0` | 是否忽略冲突课程（查询学期时固定 0） |
| `p_sfhllrlkc` | `0` | 是否忽略零容量课程（查询学期时固定 0） |

**响应 JSON（脚本使用的字段）**：

| 字段 | 含义 | 写入表单 |
|------|------|----------|
| `p_xn` | 选课学年 | `p_xn` |
| `p_xq` | 选课学期序号 | `p_xq` |
| `p_xnxq` | 选课学年学期编码 | `p_xnxq` |
| `p_dqxn` | 当前学年 | `p_dqxn` |
| `p_dqxq` | 当前学期序号 | `p_dqxq` |
| `p_dqxnxq` | 当前学年学期编码 | `p_dqxnxq` |

---

### 2. 查询可选课程 — `POST /Xsxk/queryKxrw`

**用途**：导出模式拉取可选课程列表。

**额外字段**：

| 字段 | 导出模式取值 | 含义 |
|------|--------------|------|
| `p_xkfsdm` | 来自 `courseType` | 选课类型代码 |
| `p_sfhlctkc` | `1` | `1` = 列表中隐藏冲突课程 |
| `p_sfhllrlkc` | `1` | `1` = 列表中隐藏零容量课程 |
| `pageSize` | 先 `15` 再改为 `total` | 分页大小 |
| `pageNum` | `1` | 页码 |

**响应 JSON（脚本使用的字段）**：

| 路径 | 含义 |
|------|------|
| `kxrwList.total` | 可选课程总数 |
| `kxrwList.list[].id` | **课程任务 ID**（填入 `selectedCourseIds`） |
| `kxrwList.list[].kcmc` | 课程名称 |
| `kxrwList.list[].dgjsmc` | 授课教师 |

导出文件（位于 `config_dir/`）：

- `allCourseInfo.json` — 完整接口响应
- `keyCourseInfo.json` — 精简列表（含 `课程id`、`课程名称`、`授课教师`）

---

### 3. 提交选课 — `POST /Xsxk/addGouwuche`

**用途**：对指定课程 ID 发起选课（抢课）。

**额外字段**：

| 字段 | 取值 | 含义 |
|------|------|------|
| `p_id` | 课程任务 ID | 要抢的那门课 |
| `p_xktjz` | `rwtjzyx` | 选课提交动作（任务直接预选） |
| `p_xkfsdm` | 类型代码 | 与 `courseType` 对应 |
| `p_xn` … `p_dqxnxq` | 来自学期接口 | 学期上下文 |

**响应 JSON（脚本判定用）**：

| 字段 | 含义 |
|------|------|
| `jg` | `"1"` 表示业务成功 |
| `message` | 人类可读结果文案 |

**结果判定逻辑**（`enroll_result.py`）：

1. `jg == "1"` → 成功，停止重试
2. `message == "该任务已选择"` → 已在课表中，停止
3. `message` 匹配冲突模式（如「与…冲突」）→ 排课冲突，停止
4. 其余 → 失败，间隔 `ENROLL_INTERVAL_SEC` 秒后重试，最多 `MAX_ENROLL_ATTEMPTS` 次

---

## 四、`BASE_FORM` 公共字段说明

初始化时大部分为空，由学期接口或业务逻辑填充。下表为脚本中**有明确含义**的字段；其余保持默认 `0` / 空串，与浏览器选课页一致。

| 字段 | 默认 | 含义 |
|------|------|------|
| `p_pylx` | `1` | 培养类型 |
| `mxpylx` | `1` | 明细培养类型 |
| `p_sfxsgwckb` | `1` | 是否显示购物车课表 |
| `p_xkfsdm` | `""` → 填充 | 选课方式/类型代码 |
| `p_xn` / `p_xq` / `p_xnxq` | 学期接口填充 | 选课目标学期 |
| `p_dqxn` / `p_dqxq` / `p_dqxnxq` | 学期接口填充 | 当前学期 |
| `p_id` | 抢课时填充 | 课程任务 ID |
| `p_xktjz` | 抢课时 `rwtjzyx` | 选课提交类型 |
| `p_sfhlctkc` | 列表时 0/1 | 是否过滤冲突课 |
| `p_sfhllrlkc` | 列表时 0/1 | 是否过滤零容量课 |
| `pageNum` / `pageSize` | 分页 | 课程列表分页 |

---

## 五、环境变量

| 变量 | 作用 |
|------|------|
| `ENROLL_LOG_LEVEL` / `LOG_LEVEL` | 日志级别 |
| `ENROLL_LOG_FILE` | 日志输出文件 |
| `AUTH_DEBUG` | 登录 HTTP 跳转追踪（auth 模块） |

---

## 六、目录结构

```
enroll/
├── cmd/main.py           # 入口
├── config.py             # 项目常量（API 地址等）
├── config_dir/
│   ├── myData.jsonc.example
│   ├── myData.jsonc       # 个人配置（git 忽略）
│   ├── allCourseInfo.json
│   ├── keyCourseInfo.json
│   └── cache/            # session.json、browser_fingerprint（git 忽略）
├── logic/
│   ├── client.py
│   ├── config_loader.py
│   ├── enroll_result.py
│   ├── runner.py
│   └── session_builder.py
└── utils/
    ├── log.py
    └── paths.py
```
