"""
DX Layer 1 YouTube Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_youtube_today(cursor, target_date_str):
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
    """, (target_date_str,))
    return cursor.fetchall()


def get_youtube_expected(cursor):
    cursor.execute("""
        SELECT category, COUNT(*) as keyword_count
        FROM youtube_keywords
        WHERE status = 'active'
        GROUP BY category
    """)
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_youtube_avg(cursor, target_date_str):
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
            WHERE DATE(l.started_at) >= %s::date - INTERVAL '8 days'
              AND DATE(l.started_at) < %s::date
            GROUP BY k.category, DATE(l.started_at)
        ) daily_stats
        GROUP BY category
    """, (target_date_str, target_date_str))
    return {row[0]: {'avg_video': float(row[1] or 0), 'avg_comment': float(row[2] or 0)} for row in cursor.fetchall()}


def get_youtube_logs(cursor, target_date_str, category):
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
    cursor.execute(query, (target_date_str, category))
    return columns, cursor.fetchall()


def get_youtube_videos(cursor, target_date_str, category):
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
    cursor.execute(query, (target_date_str, category))
    return columns, cursor.fetchall()


def get_youtube_comments(cursor, target_date_str, category):
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
        LIMIT 500
    """
    cursor.execute(query, (target_date_str, category))
    return columns, cursor.fetchall()
