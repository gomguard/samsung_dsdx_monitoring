"""
DS Layer 2 Report Services: 리테일러 마감 비즈니스 로직
- 리테일러별 이상치 저장/삭제
- 리테일러 저장 현황 조회
"""

import json
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection
from apps.common.response import log_error
from apps.ds.ds_layer2.stats.services import (
    get_batches_for_date, get_expected_count,
    get_quality_counts, get_quality_counts_by_time_range
)


def get_retailer_stats(cursor, retailer, target_date, include_file_info=False):
    """
    리테일러의 통계 데이터 계산
    """
    cursor.execute("""
        SELECT retailer_id, table_name, country, mall_name
        FROM ssd_crawl_db.ds_monitoring_targets
        WHERE retailer = %s AND is_active = 1
    """, (retailer,))
    target_row = cursor.fetchone()

    if not target_row:
        return None

    retailer_id = target_row[0]
    table_name = target_row[1]
    country = target_row[2]
    mall_name = target_row[3]

    batches_by_retailer = get_batches_for_date(target_date)
    retailer_batches = batches_by_retailer.get(retailer, [])
    batch_count = len(retailer_batches)
    rerun_count = max(0, batch_count - 1)

    total_quality = get_quality_counts(cursor, table_name, target_date)
    total_count = total_quality.get('total', 0)

    if batch_count >= 2:
        last_batch = retailer_batches[-1]
        final_quality = get_quality_counts_by_time_range(cursor, table_name, target_date, last_batch['start_time'], None)
        final_batch_count = final_quality.get('total', 0)
        quality = final_quality
    else:
        final_batch_count = total_count
        quality = total_quality

    expected_count = get_expected_count(cursor, country, mall_name)
    completion_rate = round((final_batch_count / expected_count * 100), 2) if expected_count > 0 else 0

    null_union = quality.get('null_union', 0)
    imageurl_invalid = quality.get('imageurl_invalid', 0)
    price_zero = quality.get('price_zero', 0)
    partial_null = quality.get('partial_null', 0)
    anomaly_total = null_union + imageurl_invalid + price_zero + partial_null

    file_name = ''
    file_size = 0
    if include_file_info:
        from apps.ds.ds_layer4.report.services import get_file_info_for_date
        file_info_cache = get_file_info_for_date(target_date)
        retailer_file = file_info_cache.get(retailer, {})
        file_name = retailer_file.get('file_name', '')
        file_size = retailer_file.get('file_size', 0)

    return {
        'retailer_id': retailer_id,
        'expected_count': expected_count,
        'total_count': total_count,
        'final_batch_count': final_batch_count,
        'completion_rate': completion_rate,
        'rerun_count': rerun_count,
        'anomaly_total': anomaly_total,
        'anomaly_title_null': null_union,
        'anomaly_image_null': quality.get('imageurl_null', 0),
        'anomaly_partial_null': partial_null,
        'anomaly_price_zero': price_zero,
        'file_name': file_name,
        'file_size': file_size
    }


def save_retailer(crawl_date, retailer, anomalies, memo, user_id):
    """리테일러 1개 마감 저장"""
    try:
        if not crawl_date or not retailer:
            return {'success': False, 'error': '필수 파라미터가 누락되었습니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()
        stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
        if not stats:
            cursor.close()
            conn.close()
            return {'success': False, 'error': f'{retailer} 타겟 정보를 찾을 수 없습니다.'}

        retailer_id = stats['retailer_id']

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))

        cursor.execute("""
            SELECT id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
            ORDER BY updated_at DESC LIMIT 1
        """, (crawl_date, retailer_id))
        old_daily = cursor.fetchone()

        if old_daily:
            report_daily_id = old_daily[0]
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_daily
                SET is_del = 0,
                    expected_count = %s, final_batch_count = %s, total_count = %s,
                    completion_rate = %s, rerun_count = %s,
                    anomaly_total = %s, anomaly_title_null = %s, anomaly_image_null = %s,
                    anomaly_partial_null = %s, anomaly_price_zero = %s,
                    memo = %s, updated_at = %s, updated_id = %s
                WHERE id = %s
            """, (
                stats['expected_count'],
                stats['final_batch_count'],
                stats['total_count'],
                stats['completion_rate'],
                stats['rerun_count'],
                stats['anomaly_total'],
                stats['anomaly_title_null'],
                stats['anomaly_image_null'],
                stats['anomaly_partial_null'],
                stats['anomaly_price_zero'],
                memo,
                now, user_id,
                report_daily_id
            ))
        else:
            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                    crawl_date, retailer_id, expected_count, final_batch_count, total_count,
                    completion_rate, rerun_count, file_name, file_size,
                    anomaly_total, anomaly_title_null, anomaly_image_null,
                    anomaly_partial_null, anomaly_price_zero,
                    memo, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, %s, 0, %s, %s
                )
            """, (
                crawl_date, retailer_id,
                stats['expected_count'],
                stats['final_batch_count'],
                stats['total_count'],
                stats['completion_rate'],
                stats['rerun_count'],
                stats['anomaly_total'],
                stats['anomaly_title_null'],
                stats['anomaly_image_null'],
                stats['anomaly_partial_null'],
                stats['anomaly_price_zero'],
                memo,
                now, user_id
            ))
            report_daily_id = cursor.lastrowid

        cursor.execute("""
            SELECT id, retailersku, screenshot_id, cause, memo
            FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
        """, (crawl_date, retailer_id))
        old_anomaly_rows = cursor.fetchall()

        old_anomaly_map = {}
        for row in old_anomaly_rows:
            sku = row[1]
            if sku and sku not in old_anomaly_map:
                old_anomaly_map[sku] = {
                    'id': row[0],
                    'screenshot_id': row[2],
                    'cause': row[3],
                    'memo': row[4]
                }

        anomaly_ids = []
        for anomaly in anomalies:
            sku = anomaly.get('retailersku', '')
            old = old_anomaly_map.pop(sku, None) if sku else None

            if old:
                cursor.execute("""
                    UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                    SET is_del = 0,
                        country_code = %s, title = %s, retailprice = %s,
                        ships_from = %s, sold_by = %s, imageurl = %s, producturl = %s,
                        updated_at = %s, updated_id = %s
                    WHERE id = %s
                """, (
                    anomaly.get('country_code', ''),
                    anomaly.get('title', ''),
                    anomaly.get('retailprice'),
                    anomaly.get('ships_from', ''),
                    anomaly.get('sold_by', ''),
                    anomaly.get('imageurl', ''),
                    anomaly.get('producturl', ''),
                    now, user_id,
                    old['id']
                ))
                anomaly_ids.append(old['id'])
            else:
                cursor.execute("""
                    INSERT INTO ssd_crawl_db.ds_monitoring_report_anomaly (
                        crawl_date, retailer_id, country_code, title, retailprice,
                        ships_from, sold_by, imageurl, producturl, retailersku,
                        screenshot_id, cause, memo, is_del, created_at, created_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s
                    )
                """, (
                    crawl_date, retailer_id,
                    anomaly.get('country_code', ''),
                    anomaly.get('title', ''),
                    anomaly.get('retailprice'),
                    anomaly.get('ships_from', ''),
                    anomaly.get('sold_by', ''),
                    anomaly.get('imageurl', ''),
                    anomaly.get('producturl', ''),
                    anomaly.get('retailersku', ''),
                    anomaly.get('screenshot_id'),
                    anomaly.get('cause', ''),
                    anomaly.get('memo', ''),
                    now, user_id
                ))
                anomaly_ids.append(cursor.lastrowid)

        orphan_screenshot_ids = [
            v['screenshot_id'] for v in old_anomaly_map.values()
            if v['screenshot_id']
        ]
        if orphan_screenshot_ids:
            placeholders = ','.join(['%s'] * len(orphan_screenshot_ids))
            cursor.execute(f"""
                UPDATE ssd_crawl_db.ds_monitoring_file
                SET is_del = 1, updated_at = %s
                WHERE file_id IN ({placeholders}) AND is_del = 0
            """, [now] + orphan_screenshot_ids)

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{retailer} 저장 완료',
            'report_daily_id': report_daily_id,
            'anomaly_count': len(anomaly_ids),
            'anomaly_ids': anomaly_ids
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def delete_retailer(crawl_date, retailer, user_id):
    """리테일러 1개 마감 삭제 (soft delete)"""
    try:
        if not crawl_date or not retailer:
            return {'success': False, 'error': '필수 파라미터가 누락되었습니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            SELECT retailer_id FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return {'success': False, 'error': f'{retailer} 타겟 정보를 찾을 수 없습니다.'}
        retailer_id = row[0]

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))
        daily_deleted = cursor.rowcount

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))
        anomaly_deleted = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{retailer} 삭제 완료',
            'daily_deleted': daily_deleted,
            'anomaly_deleted': anomaly_deleted
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def get_retailer_save_status(target_date):
    """리테일러별 마감 저장 현황 조회"""
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT t.retailer, d.anomaly_total, d.anomaly_title_null, d.anomaly_image_null,
                   d.anomaly_partial_null, d.anomaly_price_zero, d.created_at, d.created_id
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date = %s AND d.is_del = 0
        """, (target_date,))
        rows = cursor.fetchall()

        saved_retailers = {}
        for row in rows:
            saved_retailers[row[0]] = {
                'retailer': row[0],
                'anomaly_total': row[1],
                'anomaly_title_null': row[2],
                'anomaly_image_null': row[3],
                'anomaly_partial_null': row[4],
                'anomaly_price_zero': row[5],
                'created_at': row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else None,
                'created_id': row[7]
            }

        cursor.close()
        conn.close()

        return {
            'success': True,
            'date': target_date,
            'saved_retailers': saved_retailers
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}
