from datetime import datetime, timedelta
from apps.common.response import log_error
from apps.common.dx_schedules import get_schedule_kst_info, get_kst_time_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES


def get_layer1_stats(cursor, target_date, now):
    """
    YouTube(Consumer) 수집 현황 통계
    - 기대값(활성 키워드 수) 대비 수집률 기준
    - 기준: 100% 이상 = OK, 90~99% = WARNING, 90% 미만 = CRITICAL
    - 수집 시간: DB에서 로드 (US 04:00 ~ 08:00)

    Returns:
        {'check': {...}, 'failed_items': []}
    """
    result = {'check': None, 'failed_items': []}

    try:
        # DB에서 YouTube 스케줄 정보 가져오기 (KST 변환 포함)
        youtube_info = get_schedule_kst_info('youtube', target_date, now)

        # youtube_info가 None인 경우 기본값 사용
        if not youtube_info:
            kst_start = get_kst_time_info(4, target_date)
            youtube_info = {
                'us_start_hour': 4,
                'collection_duration_min': 240,
                'kst_start': kst_start,
                'kst_end': {'full_display': f"{target_date} 22:00"},  # 4시 + 4시간 (KST 18시 + 4시간)
                'time_status': None,
                'is_pending': False,
                'is_collecting': False,
                'collection_done': True
            }

        # YouTube 상태 판정 (스케줄 기반)
        youtube_status = youtube_info['time_status']
        youtube_pending = youtube_info['is_pending'] or youtube_info['is_collecting']

        # 전일 YouTube 수집량 (카테고리별)
        cursor.execute("""
            SELECT
                COALESCE(k.category, 'Unknown') as category,
                COUNT(*) as log_count,
                SUM(CASE WHEN l.status = 'completed' THEN 1 ELSE 0 END) as success_count,
                COALESCE(SUM(l.videos_collected), 0) as video_count,
                COALESCE(SUM(l.comments_collected), 0) as comment_count
            FROM youtube_collection_logs l
            LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
            WHERE DATE(l.started_at) = %s
            GROUP BY k.category
            ORDER BY k.category
        """, (target_date,))
        youtube_today = cursor.fetchall()

        # 기대건수: 활성 키워드 수 (status='active')
        cursor.execute("""
            SELECT category, COUNT(*) as keyword_count
            FROM youtube_keywords
            WHERE status = 'active'
            GROUP BY category
        """)
        youtube_expected_rows = cursor.fetchall()
        youtube_expected_map = {row[0]: row[1] for row in youtube_expected_rows}

        # 7일 평균 (전일 제외) - 로그 건수 기준
        cursor.execute("""
            SELECT
                category,
                ROUND(AVG(daily_log_count), 1) as avg_log_count,
                ROUND(AVG(daily_comment_count), 1) as avg_comment_count
            FROM (
                SELECT
                    COALESCE(k.category, 'Unknown') as category,
                    DATE(l.started_at) as log_date,
                    COUNT(*) as daily_log_count,
                    COALESCE(SUM(l.comments_collected), 0) as daily_comment_count
                FROM youtube_collection_logs l
                LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.started_at) >= %s - INTERVAL '8 days'
                  AND DATE(l.started_at) < %s
                GROUP BY k.category, DATE(l.started_at)
            ) daily_stats
            GROUP BY category
        """, (target_date, target_date))
        youtube_avg_rows = cursor.fetchall()
        youtube_avg = {row[0]: {'avg_video': float(row[1] or 0), 'avg_comment': float(row[2] or 0)} for row in youtube_avg_rows}

        # YouTube 카테고리별 상세 데이터
        youtube_categories = []
        youtube_total_actual = 0
        youtube_total_expected = 0
        youtube_statuses = []

        for row in youtube_today:
            category = row[0]
            log_count = row[1] or 0
            success_count = row[2]
            video_count = row[3] or 0
            comment_count = row[4] or 0

            # 기대건수: 활성 키워드 수
            expected = youtube_expected_map.get(category, 0)
            # 7일 평균
            avg_data = youtube_avg.get(category, {'avg_video': 0, 'avg_comment': 0})
            avg_7day = avg_data['avg_video']

            # 수집률 계산 (기대건수 기준)
            if expected > 0:
                rate = (log_count / expected) * 100
            else:
                rate = 100 if log_count > 0 else 0

            # 상태 판정: 스케줄 기반 시간대 상태 + 결과 기준
            if youtube_info['is_pending']:
                status = 'PENDING'
            elif expected == 0:
                status = 'OK' if log_count > 0 else 'WARNING'
            elif rate >= 100:
                status = 'OK'
            elif youtube_info['is_collecting']:
                status = 'COLLECTING'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            youtube_statuses.append(status)
            youtube_total_actual += log_count
            youtube_total_expected += expected

            youtube_categories.append({
                'name': category,
                'log_count': log_count,
                'video_count': video_count,
                'comment_count': comment_count,
                'expected': expected,  # 기대건수 (활성 키워드 수)
                'avg_7day': round(avg_7day),  # 7일 평균
                'rate': round(rate, 1),
                'status': status
            })

        # YouTube 전체 상태
        if youtube_total_expected > 0:
            youtube_overall_rate = (youtube_total_actual / youtube_total_expected) * 100
        else:
            youtube_overall_rate = 100 if youtube_total_actual > 0 else 0

        # 전체 상태 판정: 스케줄 기반 시간대 상태 + 결과 기준
        if youtube_info['is_pending']:
            youtube_overall_status = 'PENDING'
        elif youtube_total_expected == 0:
            youtube_overall_status = 'OK' if youtube_total_actual > 0 else 'WARNING'
        elif youtube_overall_rate >= 100:
            youtube_overall_status = 'OK'
        elif youtube_info['is_collecting']:
            youtube_overall_status = 'COLLECTING'
        elif youtube_overall_rate >= 90:
            youtube_overall_status = 'WARNING'
        else:
            youtube_overall_status = 'CRITICAL'

        youtube_ok_count = len([s for s in youtube_statuses if s == 'OK'])

        # TV, HHP 순서로 정렬
        category_order = {'TV': 0, 'HHP': 1}
        youtube_categories.sort(key=lambda x: category_order.get(x['name'], 99))

        result['check'] = {
            'name': SECTION_TITLES['youtube'],
            'description': f'{youtube_ok_count}/{len(youtube_statuses)} 카테고리 정상',
            'actual': youtube_total_actual,
            'expected': round(youtube_total_expected),
            'rate': round(youtube_overall_rate, 1),
            'status': youtube_overall_status,
            'check_type': 'youtube',
            'us_time': f'{target_date} {youtube_info["us_start_hour"]:02d}:00',
            'kr_time': youtube_info['kst_start']['full_display'],
            'kr_time_end': youtube_info['kst_end']['full_display'],
            'is_dst': youtube_info['kst_start']['is_dst'],
            'categories': youtube_categories
        }

    except Exception as e:
        log_error(e)

    return result


def get_youtube_raw_data(cursor, category, data_type, target_date):
    """
    YouTube 원본 데이터 조회
    - category: TV 또는 HHP
    - data_type: logs, videos, comments (기본: logs)
    - target_date: 조회 날짜 (date 객체)

    Returns:
        {
            'category': str,
            'date': str,
            'data_type': str,
            'columns': list,
            'data': list,
            'total_count': int
        }
    """
    results = {
        'category': category,
        'date': str(target_date),
        'data_type': data_type,
        'columns': [],
        'data': [],
        'total_count': 0
    }

    try:
        if data_type == 'logs':
            # 수집 로그 데이터
            columns = [
                'id', 'keyword', 'category', 'status', 'videos_collected',
                'comments_collected', 'started_at', 'completed_at', 'error_message'
            ]

            query = """
                SELECT
                    l.id,
                    k.keyword,
                    k.category,
                    l.status,
                    l.videos_collected,
                    l.comments_collected,
                    l.started_at,
                    l.completed_at,
                    l.error_message
                FROM youtube_collection_logs l
                LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.started_at) = %s
                AND k.category = %s
                ORDER BY l.id DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category))

        elif data_type == 'videos':
            # 비디오 데이터 - 모든 컬럼
            columns = [
                'video_id', 'keyword', 'title', 'description', 'published_at',
                'channel_country', 'channel_custom_url', 'channel_subscriber_count', 'channel_video_count',
                'view_count', 'like_count', 'comment_count', 'category_id', 'category',
                'engagement_rate', 'reviewed_brand', 'reviewed_series', 'reviewed_item',
                'product_sentiment_score', 'product_sentiment_score_comment', 'comment_text_summary',
                'created_at'
            ]

            query = """
                SELECT
                    v.video_id,
                    v.keyword,
                    v.title,
                    v.description,
                    v.published_at,
                    v.channel_country,
                    v.channel_custom_url,
                    v.channel_subscriber_count,
                    v.channel_video_count,
                    v.view_count,
                    v.like_count,
                    v.comment_count,
                    v.category_id,
                    v.category,
                    v.engagement_rate,
                    v.reviewed_brand,
                    v.reviewed_series,
                    v.reviewed_item,
                    v.product_sentiment_score,
                    v.product_sentiment_score_comment,
                    v.comment_text_summary,
                    v.created_at
                FROM youtube_videos v
                LEFT JOIN youtube_keywords k ON v.keyword = k.keyword
                WHERE DATE(v.created_at) = %s
                AND k.category = %s
                ORDER BY v.created_at DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category))

        elif data_type == 'comments':
            # 댓글 데이터 - 전체 컬럼
            columns = [
                'comment_id', 'video_id', 'comment_type', 'parent_comment_id',
                'comment_text_display', 'like_count', 'reply_count',
                'published_at', 'sentiment_score', 'created_at'
            ]

            query = """
                SELECT DISTINCT
                    c.comment_id,
                    c.video_id,
                    c.comment_type,
                    c.parent_comment_id,
                    c.comment_text_display,
                    c.like_count,
                    c.reply_count,
                    c.published_at,
                    c.sentiment_score,
                    c.created_at
                FROM youtube_comments c
                JOIN youtube_videos v ON c.video_id = v.video_id
                WHERE DATE(c.created_at) = %s
                AND v.keyword IN (SELECT keyword FROM youtube_keywords WHERE category = %s)
                ORDER BY c.created_at DESC
            """
            cursor.execute(query, (target_date, category))

        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

    except Exception as e:
        results['error'] = log_error(e)

    return results
