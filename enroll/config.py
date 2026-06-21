"""教务选课相关常量与接口配置。"""

# 目标站点 CAS 入口
ENTRY_URL = "http://jw.hitsz.edu.cn/casLogin"

# 教务系统 API 基址（使用 http 走内网，通常比 https 公网更快）
JW_BASE = "http://jw.hitsz.edu.cn"

# 接口路径
API_QUERY_SEMESTER = f"{JW_BASE}/Xsxk/queryXkdqXnxq"
API_QUERY_COURSES = f"{JW_BASE}/Xsxk/queryKxrw"
API_ADD_COURSE = f"{JW_BASE}/Xsxk/addGouwuche"

# 选课类型：界面名称 -> 接口代码
COURSE_TYPE_MAP = {
    "限选": "xx-b-b",
    "必修": "bx-b-b",
    "跨专业课程体系": "sx-b-b",
    "文理通识": "tsk-b-b",
    "MOOC": "mooc-b-b",
}

# 默认抢课参数
MAX_ENROLL_ATTEMPTS = 10
ENROLL_INTERVAL_SEC = 3
REQUEST_TIMEOUT_SEC = 20

# 默认分页大小（首次探测用）
DEFAULT_PAGE_SIZE = 15

# 公共表单字段默认值
BASE_FORM = {
    "cxsfmt": 0,
    "p_pylx": 1,
    "mxpylx": 1,
    "p_sfgldjr": 0,
    "p_sfredis": 0,
    "p_sfsyxkgwc": 0,
    "p_xktjz": "",
    "p_chaxunxh": "",
    "p_gjz": "",
    "p_skjs": "",
    "p_xn": "",
    "p_xq": "",
    "p_xnxq": "",
    "p_dqxn": "",
    "p_dqxq": "",
    "p_dqxnxq": "",
    "p_xkfsdm": "",
    "p_xiaoqu": "",
    "p_kkyx": "",
    "p_kclb": "",
    "p_xkxs": "",
    "p_dyc": "",
    "p_kkxnxq": "",
    "p_id": "",
    "p_sfhlctkc": "",
    "p_sfhllrlkc": "",
    "p_kxsj_xqj": "",
    "p_kxsj_ksjc": "",
    "p_kxsj_jsjc": "",
    "p_kcdm_js": "",
    "p_kcdm_cxrw": "",
    "p_kcdm_cxrw_zckc": "",
    "p_kc_gjz": "",
    "p_xzcxtjz_nj": "",
    "p_xzcxtjz_yx": "",
    "p_xzcxtjz_zy": "",
    "p_xzcxtjz_zyfx": "",
    "p_xzcxtjz_bj": "",
    "p_sfxsgwckb": 1,
    "p_skyy": "",
    "p_chaxunxkfsdm": "",
    "pageNum": 1,
    "pageSize": DEFAULT_PAGE_SIZE,
}
