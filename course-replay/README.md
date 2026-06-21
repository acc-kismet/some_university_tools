# 课程回放下载油猴脚本

HITsz 教学平台 `jxypt.hitsz.edu.cn` 课程回放批量下载、回放权限绕过、播放器快捷键。

> **状态**：该脚本功能目前可用，是本仓库中维护优先级最高的子项目。

## 安装

1. 安装 [Tampermonkey](https://www.tampermonkey.net/)
2. 新建脚本，粘贴 `course-helper.js` 全部内容
3. 保存并访问 `https://jxypt.hitsz.edu.cn/*`
4. 首次跨域请求时允许 Tampermonkey 权限（`GM.xmlHttpRequest`）

## 功能

| 功能 | 说明 |
|------|------|
| 批量下载 | 从课程列表勾选教师流/学生流/课件流，串行下载、分片 10 并发 |
| 回放绕过 | 覆盖 `getStuControlType` + 点击拦截，无权限也可打开回放 |
| 动态刷新 | MutationObserver 监听 DOM，分页/筛选后自动同步列表 |
| 快捷键 | 左右方向键快进/快退 10 秒 |

## 交互接口一览

### 1. 回放详情页（获取 HLS 地址）

| 项目 | 值 |
|------|-----|
| URL 模板 | `GET https://jxypt.hitsz.edu.cn:443/ve/back/rp/common/rpIndex.shtml` |
| 方法 | GET（通过 `GM.xmlHttpRequest`） |
| Query 参数 | `method=studyCourseDeatil`, `courseId={id2}`, `courseNum={courseCode}`, `rpId={id1}`, `dataSource=1` |
| 响应 | HTML 页面，内嵌 JS 变量 |

**从 HTML 提取的 HLS 变量**：

| JS 变量 | 流类型 | 对应 key |
|---------|--------|----------|
| `teaStreamHlsUrl` | 教师流 | `teaUrl` |
| `stuStreamHlsUrl` | 学生流 | `stuUrl` |
| `vgaStreamHlsUrl` | 课件流 | `vgaUrl` |

### 2. HLS 播放列表

| 项目 | 值 |
|------|-----|
| URL | 上一步提取的 `*StreamHlsUrl` 绝对地址 |
| 方法 | GET |
| 响应 | m3u8 文本，非 `#` 开头且以 `.ts`/`.mp4` 结尾的行为分片 URL |

### 3. 视频分片下载

| 项目 | 值 |
|------|-----|
| URL | m3u8 中各分片 URL（相对路径会补全为绝对路径） |
| 方法 | GET |
| 响应类型 | `arraybuffer` |
| 并发 | 每路流内 10 个分片并发，多路流之间串行 |

### 4. 回放权限绕过（页面内 JS，非 HTTP）

| 项目 | 值 |
|------|-----|
| 原函数 | `window.getStuControlType(rpId, courseId, courseNum, fzId)` |
| 覆盖行为 | 直接 `window.open` 打开回放 URL |
| 回放 URL 模板 | `../../../back/rp/common/rpIndex.shtml?method=studyCourseDeatil&courseId={courseId}&dataSource=1&courseNum={courseNum}&fzId={fzId}&rpId={rpId}&publicRpType=2,3` |

### 5. DOM 数据源（课程列表解析）

| 选择器 | 用途 |
|--------|------|
| `ul.curr-contentr-title.curr-contentr-list.clearfloat` | 单条回放列表项 |
| `span.topm` | 主课程名称 |
| `a[onclick*="getStuControlType("]` | 回放入口，onclick 含四个 ID 参数 |

**onclick 参数顺序**：`rpId`, `courseId`, `courseNum`, `fzId`

## 配置常量（脚本顶部）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `SKIP_AMOUNT` | 10 | 快捷键跳转秒数 |
| `REFRESH_DELAY` | 150 | DOM 变化后刷新防抖 ms |
| `MAX_ATTEMPTS` | 50 | 等待 `getStuControlType` 重试次数 |
| 分片并发 | 10 | `downloadAndMergeSegments` 内硬编码 |

## 代码结构

单文件油猴脚本 `course-helper.js`，按模块划分：

1. 常量与 UI 状态
2. URL/参数解析
3. 网络请求（GM XHR）
4. 下载与合并
5. DOM 提取与面板 UI
6. 回放绕过与快捷键

## 后人迭代指南

1. **页面改版**：用 DevTools 检查 `COURSE_LIST_SELECTOR`、`REPLAY_SELECTOR` 是否仍匹配
2. **HLS 变量改名**：更新 `extractHlsUrlsFromHtml` 中的正则
3. **详情页 URL 变化**：修改 `VIDEO_PAGE_URL_TEMPLATE` 与 `buildReplayUrl`
4. **下载失败**：在 Network 面板对比 m3u8/分片请求，确认是否需 Cookie 或新域名
5. **Tampermonkey 权限**：确保 `@grant GM.xmlHttpRequest` 未被移除

## 免责声明

仅供个人离线学习，请遵守学校与平台相关规定，勿传播下载内容。
