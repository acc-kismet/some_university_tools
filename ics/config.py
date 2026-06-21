"""课表 ICS 配置。"""

from datetime import datetime

# 课表查询日期范围（按学期修改）
START_DATE = datetime(2025, 6, 22)
END_DATE = datetime(2026, 2, 1)

# 目标站点 CAS 入口（未登录时会 302 到 IDS）
ENTRY_URL = "http://jw.hitsz.edu.cn/casLogin"

# 日程查询接口
SCHEDULE_QUERY_URL = "http://jw.hitsz.edu.cn/component/queryrcxxlist"

# 默认地点前缀
LOCATION_PREFIX = "哈尔滨工业大学深圳校区"

# 默认时区
TIMEZONE = "Asia/Shanghai"

# 提前提醒分钟数（当前未写入 ICS，可扩展）
REMIND_MINUTES = 15
