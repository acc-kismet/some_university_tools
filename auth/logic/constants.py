"""IDS 统一认证常量。"""

IDS_HOST = "https://ids.hit.edu.cn"
AUTH_BASE = f"{IDS_HOST}/authserver"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )
}

JW_SCHEDULE_PROBE_URL = "http://jw.hitsz.edu.cn/component/queryrcxxlist"
