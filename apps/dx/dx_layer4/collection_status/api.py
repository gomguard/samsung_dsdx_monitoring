"""
수집 현황 API — 리테일러별 수집 건수 및 컬럼별 NULL 현황, 이메일 발송
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.db import get_dx_connection
from apps.common.response import safe_error
from apps.common.params import parse_date
from apps.common.db import dx_table
from apps.common.retail_columns import load_retail_columns
from config.config import EMAIL_CONFIG

_EMAIL_LOG_TABLE = dx_table('monitoring_email_logs')


_TABLE_MAP = {
    'tv': 'tv_retail_com',
    'hhp': 'hhp_retail_com',
}

_DATE_COL_MAP = {
    'tv': 'crawl_datetime',
    'hhp': 'crawl_strdatetime',
}


def collection_status_data(request):
    """리테일러별 수집 건수 + 컬럼별 NULL 수 조회"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    category = request.GET.get('category', 'tv')  # 'tv' | 'hhp'
    if category not in _TABLE_MAP:
        return JsonResponse({'error': '잘못된 카테고리입니다.'}, status=400)

    table_name = _TABLE_MAP[category]
    date_col = _DATE_COL_MAP[category]

    all_col_data = load_retail_columns()
    retailer_columns = all_col_data.get(category, {})

    if not retailer_columns:
        return JsonResponse({'success': True, 'retailers': []})

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        retailers = []
        for retailer, columns in sorted(retailer_columns.items()):
            if not columns:
                continue

            # 컬럼별 NULL 카운트 SQL 동적 생성
            null_parts = []
            for col in columns:
                null_parts.append(
                    f"SUM(CASE WHEN {col} IS NULL OR CAST({col} AS TEXT) = '' THEN 1 ELSE 0 END) AS null_{col}"
                )

            sql = (
                f"SELECT COUNT(*) AS total_count, {', '.join(null_parts)} "
                f"FROM {table_name} "
                f"WHERE account_name = %s AND ({date_col})::date = %s::date"
            )
            cursor.execute(sql, [retailer, str(target_date)])
            row = cursor.fetchone()

            total_count = row[0] if row else 0
            column_nulls = []
            for i, col in enumerate(columns):
                null_count = row[i + 1] if row else 0
                column_nulls.append({
                    'column': col,
                    'null_count': null_count,
                    'fill_rate': round((1 - null_count / total_count) * 100, 1) if total_count > 0 else 0,
                })

            retailers.append({
                'retailer': retailer,
                'total_count': total_count,
                'columns': column_nulls,
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'retailers': retailers,
        })
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)


def collection_null_detail(request):
    """특정 리테일러/컬럼의 NULL 행 상세 조회"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    category = request.GET.get('category', 'tv')
    retailer = request.GET.get('retailer', '')
    column = request.GET.get('column', '')

    if category not in _TABLE_MAP:
        return JsonResponse({'error': '잘못된 카테고리입니다.'}, status=400)
    if not retailer or not column:
        return JsonResponse({'error': '리테일러와 컬럼을 지정해주세요.'}, status=400)

    # 허용된 컬럼인지 검증 (SQL 인젝션 방지)
    all_col_data = load_retail_columns()
    retailer_columns = all_col_data.get(category, {}).get(retailer, [])
    if column not in retailer_columns:
        return JsonResponse({'error': '허용되지 않은 컬럼입니다.'}, status=400)

    table_name = _TABLE_MAP[category]
    date_col = _DATE_COL_MAP[category]
    date_expr = 'crawl_datetime' if category == 'tv' else 'crawl_strdatetime AS crawl_datetime'

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        sql = (
            f"SELECT id, {date_expr}, account_name, item, {column}, product_url "
            f"FROM {table_name} "
            f"WHERE account_name = %s AND ({date_col})::date = %s::date "
            f"AND ({column} IS NULL OR CAST({column} AS TEXT) = '') "
            f"ORDER BY item, {date_col} ASC"
        )
        cursor.execute(sql, [retailer, str(target_date)])

        col_names = ['id', 'crawl_datetime', 'account_name', 'item', column, 'product_url']
        rows = []
        for row in cursor.fetchall():
            d = {}
            for idx, val in enumerate(row):
                if hasattr(val, 'strftime'):
                    d[col_names[idx]] = val.strftime('%Y-%m-%d %H:%M:%S')
                elif val is None:
                    d[col_names[idx]] = ''
                else:
                    d[col_names[idx]] = str(val)
            rows.append(d)

        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'columns': col_names,
            'rows': rows,
        })
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)


def _save_email_log(crawl_date, subject, receiver, sender, sent_id, status, error_message=None):
    """이메일 발송 이력 저장"""
    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {_EMAIL_LOG_TABLE}
                (crawl_date, subject, receiver_email, sender_email, sent_at, sent_id, status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, [crawl_date, subject, receiver, sender, datetime.now(), sent_id, status, error_message])
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@require_POST
def send_email_report(request):
    """이메일 보고 발송 API"""
    try:
        body = json.loads(request.body)
        subject = body.get('subject', '')
        html_content = body.get('html', '')
        crawl_date = body.get('date', '')
        receiver = body.get('receiver', EMAIL_CONFIG['receiver_email'])
        sender = EMAIL_CONFIG['sender_email']
        sent_id = request.user.username if request.user.is_authenticated else 'anonymous'

        if not subject or not html_content:
            return JsonResponse({'error': '제목과 내용을 입력해주세요.'}, status=400)

        full_html = (
            '<!DOCTYPE html>'
            '<html><head><meta charset="utf-8"></head>'
            '<body style="margin:0;padding:20px;font-family:Malgun Gothic,sans-serif;font-size:13px;color:#222;">'
            + html_content
            + '</body></html>'
        )

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = receiver

        msg.attach(MIMEText(full_html, 'html', 'utf-8'))

        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(sender, EMAIL_CONFIG['sender_password'])
            server.sendmail(sender, receiver, msg.as_string())

        _save_email_log(crawl_date, subject, receiver, sender, sent_id, 'success')
        return JsonResponse({'success': True, 'message': '이메일이 발송되었습니다.'})
    except Exception as e:
        _save_email_log(crawl_date if 'crawl_date' in dir() else '', subject if 'subject' in dir() else '', receiver if 'receiver' in dir() else '', sender if 'sender' in dir() else '', sent_id if 'sent_id' in dir() else '', 'failed', str(e))
        return JsonResponse({'error': f'발송 실패: {str(e)}'}, status=500)


def email_sent_check(request):
    """해당 날짜 이메일 발송 여부 및 횟수 확인"""
    crawl_date = request.GET.get('date', '')
    if not crawl_date:
        return JsonResponse({'count': 0})

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM {_EMAIL_LOG_TABLE} WHERE crawl_date = %s AND status = 'success'",
            [crawl_date]
        )
        count = cursor.fetchone()[0]

        last_info = {}
        if count > 0:
            cursor.execute(
                f"SELECT sent_at, sent_id FROM {_EMAIL_LOG_TABLE} WHERE crawl_date = %s AND status = 'success' ORDER BY sent_at DESC",
                [crawl_date]
            )
            row = cursor.fetchone()
            last_info = {
                'sent_at': row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else '',
                'sent_id': row[1] or '',
            }

        cursor.close()
        conn.close()

        return JsonResponse({'count': count, **last_info})
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return JsonResponse({'sent': False})
