"""
Market Competitor / Event 공통 유틸리티
- 분기 계산
- 경쟁사 배치 조회
"""


def get_quarter_info(target_date):
    """분기 시작/종료일, 분기명 반환"""
    target_month = target_date.month
    target_year = target_date.year

    if target_month <= 3:
        quarter_start = f"{target_year}-01-01"
        quarter_end = f"{target_year}-03-31"
        quarter_name = "Q1"
    elif target_month <= 6:
        quarter_start = f"{target_year}-04-01"
        quarter_end = f"{target_year}-06-30"
        quarter_name = "Q2"
    elif target_month <= 9:
        quarter_start = f"{target_year}-07-01"
        quarter_end = f"{target_year}-09-30"
        quarter_name = "Q3"
    else:
        quarter_start = f"{target_year}-10-01"
        quarter_end = f"{target_year}-12-31"
        quarter_name = "Q4"

    return {
        'quarter_start': quarter_start,
        'quarter_end': quarter_end,
        'quarter_name': quarter_name,
    }


def get_competitor_batch(cursor, quarter_start, quarter_end):
    """해당 분기 최신 batch_id 조회 → (batch_id, last_run)"""
    cursor.execute("""
        SELECT batch_id, MAX(created_at) as last_run
        FROM market_comp_product
        WHERE batch_id IS NOT NULL
          AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
        GROUP BY batch_id
        ORDER BY last_run DESC
        LIMIT 1
    """, (quarter_start, quarter_end))
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return None, None
