"""
DS Layer 2 Report Services: 보고서 관리 비즈니스 로직
- 리테일러별 이상치 저장/삭제/수정
- 일별 보고서 마감/취소
- 파일 정보 조회/저장
- 보고서 현황 및 목록 조회
"""

import json
import paramiko
from datetime import datetime, timedelta, date
from apps.common.db import get_ds_connection
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance
from apps.common.response import log_error
from config.config import FILE_SERVER_CONFIG
from apps.ds.ds_layer2.stats.services import (
    get_monitoring_targets, get_batches_for_date, get_expected_count,
    get_quality_counts, get_quality_counts_by_time_range
)


def get_file_info_for_date(target_date):
    """
    특정 날짜의 리테일러별 파일 정보 조회 (SFTP)
    반환: {retailer_name: {'file_name': str, 'file_size': int}, ...}
    """
    date_folder = target_date.strftime('%Y%m%d')
    file_info = {}

    try:
        transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
        transport.connect(
            username=FILE_SERVER_CONFIG['username'],
            password=FILE_SERVER_CONFIG['password']
        )
        sftp = paramiko.SFTPClient.from_transport(transport)
        base_path = FILE_SERVER_CONFIG['upload_path']

        # 리테일러명 매핑 (country_retailer -> retailer_name)
        # 파일서버 파일명에는 '-'가 없으므로 제거하여 매핑 (예: x-kom -> xkom)
        targets = get_monitoring_targets()
        retailer_map = {}
        for t in targets:
            country = t[4].lower() if t[4] else ''
            mall = t[5].lower().replace(' ', '_').replace('-', '') if t[5] else ''
            key = f"{country}_{mall}"
            retailer_map[key] = t[1]  # retailer name

        # 국가별 디렉토리 조회
        try:
            country_dirs = sftp.listdir(base_path)
        except Exception:
            country_dirs = []

        for country_code in country_dirs:
            country_path = f"{base_path}/{country_code}"

            try:
                stat = sftp.stat(country_path)
                if not (stat.st_mode & 0o40000):
                    continue
            except Exception:
                continue

            date_path = f"{country_path}/{date_folder}"
            try:
                sftp.stat(date_path)
            except FileNotFoundError:
                continue

            try:
                files = sftp.listdir_attr(date_path)
                zip_files = [f for f in files if f.filename.endswith('.zip') and not (f.st_mode & 0o40000)]

                for f in zip_files:
                    filename = f.filename
                    parts = filename.replace('.zip', '').split('_')
                    if len(parts) >= 4:
                        file_country = parts[2]
                        file_retailer = '_'.join(parts[3:])
                        retailer_key = f"{file_country}_{file_retailer}"
                        retailer_name = retailer_map.get(retailer_key, file_retailer)
                    else:
                        retailer_name = country_code.upper()

                    file_info[retailer_name] = {
                        'file_name': filename,
                        'file_size': f.st_size
                    }
            except Exception:
                continue

        sftp.close()
        transport.close()

    except Exception as e:
        log_error(e)

    return file_info


def get_retailer_stats(cursor, retailer, target_date, file_info_cache=None, include_file_info=True):
    """
    리테일러의 통계 데이터 계산 (공통 함수)
    - retailer_id: 리테일러 ID
    - expected_count: 예상 수집 건수
    - total_count: 하루 전체 수집 건수
    - final_batch_count: 최종 배치 건수
    - completion_rate: 완료율
    - rerun_count: 재실행 횟수
    - 이상치 통계 (최종 배치 기준)
    - file_name, file_size: include_file_info=True일 때만 file_info_cache에서 조회
    """
    # 리테일러 타겟 정보 찾기 (retailer_id 포함)
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

    # 배치 정보 조회
    batches_by_retailer = get_batches_for_date(target_date)
    retailer_batches = batches_by_retailer.get(retailer, [])
    batch_count = len(retailer_batches)
    rerun_count = max(0, batch_count - 1)

    # 하루 전체 수집 건수 조회
    total_quality = get_quality_counts(cursor, table_name, target_date)
    total_count = total_quality.get('total', 0)

    # 최종 배치 건수 및 이상치 통계 조회
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

    # 이상치 통계 (최종 배치 기준)
    null_union = quality.get('null_union', 0)
    imageurl_invalid = quality.get('imageurl_invalid', 0)
    price_zero = quality.get('price_zero', 0)
    partial_null = quality.get('partial_null', 0)
    anomaly_total = null_union + imageurl_invalid + price_zero + partial_null

    # 파일 정보 조회 (include_file_info=True일 때만)
    file_name = ''
    file_size = 0
    if include_file_info:
        if file_info_cache is None:
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


def save_report(crawl_date, retailer, anomalies, memo, user_id):
    """
    리테일러별 이상치 데이터 저장

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명
    - anomalies: 이상치 데이터 목록 (list)
    - memo: 메모 (str)
    - user_id: 사용자 ID (str)

    반환: dict with success/message/report_daily_id/anomaly_count/anomaly_ids
    """
    try:
        if not crawl_date or not retailer:
            return {'success': False, 'error': '필수 파라미터가 누락되었습니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 통계 데이터 계산 (백엔드에서 직접, 파일 정보 제외)
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()
        stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
        if not stats:
            cursor.close()
            conn.close()
            return {'success': False, 'error': f'{retailer} 타겟 정보를 찾을 수 없습니다.'}

        retailer_id = stats['retailer_id']

        # 1. 기존 활성 데이터 soft delete (is_del = 1)
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

        # 2. report_daily — 기존 soft-deleted 레코드 복구 또는 신규 INSERT
        cursor.execute("""
            SELECT id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
            ORDER BY updated_at DESC LIMIT 1
        """, (crawl_date, retailer_id))
        old_daily = cursor.fetchone()

        if old_daily:
            # 기존 레코드 복구: 통계만 갱신, file_name/file_size는 유지
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
            # 최초 저장: 신규 INSERT (파일 정보는 별도 API에서 저장)
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

        # 3. report_anomaly — retailersku 매칭으로 복구 또는 신규 INSERT
        #    복구 시 screenshot_id, cause, memo 유지
        cursor.execute("""
            SELECT id, retailersku, screenshot_id, cause, memo
            FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
        """, (crawl_date, retailer_id))
        old_anomaly_rows = cursor.fetchall()

        # retailersku → {id, screenshot_id, cause, memo} 매핑 (첫 매칭만 사용)
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
                # 기존 레코드 복구: 상품 데이터 갱신, screenshot_id/cause/memo 유지
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
                # 신규 INSERT (매칭 안 되는 이상치)
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

        # 4. 미매칭 이상치의 스크린샷 파일 soft delete
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


def delete_report(crawl_date, retailer, user_id):
    """
    리테일러별 저장된 데이터 삭제 (soft delete)

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명
    - user_id: 사용자 ID (str)

    반환: dict with success/message/daily_deleted/anomaly_deleted
    """
    try:
        if not crawl_date or not retailer:
            return {'success': False, 'error': '필수 파라미터가 누락되었습니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # retailer_id 조회
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

        # report_daily soft delete
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))
        daily_deleted = cursor.rowcount

        # report_anomaly soft delete
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


def update_report(body):
    """
    이상치 데이터 수정 (cause, memo, screenshot_id) - 단건 또는 일괄

    파라미터 (단건):
    - body['anomaly_id']: 이상치 ID
    - body['cause']: 원인 (선택)
    - body['memo']: 메모 (선택)
    - body['screenshot_id']: 스크린샷 파일 ID (선택)

    파라미터 (일괄):
    - body['updates']: [{anomaly_id, cause, memo}, ...] 배열

    반환: dict with success/message/updated_count or anomaly_id
    """
    try:
        user_id = body.get('user_id', 'system')

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 일괄 처리
        if 'updates' in body:
            updates = body['updates']
            if not updates or not isinstance(updates, list):
                return {'success': False, 'error': 'updates 배열이 필요합니다.'}

            updated_count = 0
            for item in updates:
                anomaly_id = item.get('anomaly_id')
                if not anomaly_id:
                    continue

                update_fields = []
                update_values = []

                if 'cause' in item:
                    update_fields.append('cause = %s')
                    update_values.append(item['cause'])

                if 'memo' in item:
                    update_fields.append('memo = %s')
                    update_values.append(item['memo'])

                if 'screenshot_id' in item:
                    update_fields.append('screenshot_id = %s')
                    update_values.append(item['screenshot_id'])

                if update_fields:
                    update_fields.append('updated_at = %s')
                    update_values.append(now)
                    update_fields.append('updated_id = %s')
                    update_values.append(user_id)
                    update_values.append(anomaly_id)

                    query = f"""
                        UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                        SET {', '.join(update_fields)}
                        WHERE id = %s AND is_del = 0
                    """
                    cursor.execute(query, update_values)
                    updated_count += cursor.rowcount

            conn.commit()
            cursor.close()
            conn.close()

            return {
                'success': True,
                'message': f'{updated_count}건 저장 완료',
                'updated_count': updated_count
            }

        # 단건 처리
        anomaly_id = body.get('anomaly_id')
        if not anomaly_id:
            return {'success': False, 'error': 'anomaly_id가 필요합니다.'}

        # 업데이트할 필드들 수집
        update_fields = []
        update_values = []

        if 'cause' in body:
            update_fields.append('cause = %s')
            update_values.append(body['cause'])

        if 'memo' in body:
            update_fields.append('memo = %s')
            update_values.append(body['memo'])

        if 'screenshot_id' in body:
            update_fields.append('screenshot_id = %s')
            update_values.append(body['screenshot_id'])

        if not update_fields:
            return {'success': False, 'error': '수정할 필드가 없습니다.'}

        update_fields.append('updated_at = %s')
        update_values.append(now)
        update_fields.append('updated_id = %s')
        update_values.append(user_id)
        update_values.append(anomaly_id)

        query = f"""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET {', '.join(update_fields)}
            WHERE id = %s AND is_del = 0
        """
        cursor.execute(query, update_values)
        updated = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        if updated == 0:
            return {'success': False, 'error': '해당 데이터를 찾을 수 없습니다.'}

        return {
            'success': True,
            'message': '수정 완료',
            'anomaly_id': anomaly_id
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def update_daily_memo(body):
    """
    일별 보고서 메모 수정 (단건 또는 일괄)

    파라미터:
    - body['daily_id']: report_daily ID (단건)
    - body['memo']: 메모 (단건)
    또는
    - body['memos']: [{daily_id, memo}, ...] (일괄)

    반환: dict with success/message/updated_count or daily_id
    """
    try:
        user_id = body.get('user_id', 'system')

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 일괄 처리
        if 'memos' in body:
            memos = body['memos']
            if not memos or not isinstance(memos, list):
                return {'success': False, 'error': 'memos 배열이 필요합니다.'}

            updated_count = 0
            for item in memos:
                daily_id = item.get('daily_id')
                memo = item.get('memo', '')
                if daily_id:
                    cursor.execute("""
                        UPDATE ssd_crawl_db.ds_monitoring_report_daily
                        SET memo = %s, updated_at = %s, updated_id = %s
                        WHERE id = %s AND is_del = 0
                    """, (memo, now, user_id, daily_id))
                    updated_count += cursor.rowcount

            conn.commit()
            cursor.close()
            conn.close()

            return {
                'success': True,
                'message': f'{updated_count}건 메모 저장 완료',
                'updated_count': updated_count
            }

        # 단건 처리
        daily_id = body.get('daily_id')
        if not daily_id:
            return {'success': False, 'error': 'daily_id가 필요합니다.'}

        if 'memo' not in body:
            return {'success': False, 'error': 'memo 필드가 필요합니다.'}

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET memo = %s, updated_at = %s, updated_id = %s
            WHERE id = %s AND is_del = 0
        """, (body['memo'], now, user_id, daily_id))
        updated = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        if updated == 0:
            return {'success': False, 'error': '해당 데이터를 찾을 수 없습니다.'}

        return {
            'success': True,
            'message': '메모 수정 완료',
            'daily_id': daily_id
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def save_all_reports(crawl_date, user_id):
    """
    미저장 리테일러 일괄 현황 저장 (파일 정보 제외)

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - user_id: 사용자 ID (str)

    반환: dict with success/message/saved_count/total_retailers/already_saved
    """
    try:
        if not crawl_date:
            return {'success': False, 'error': 'crawl_date가 필요합니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
            cursor.close()
            conn.close()
            return {'success': False, 'error': '이미 마감된 날짜입니다.'}

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. 이미 저장된 retailer_id 목록 조회
        cursor.execute("""
            SELECT retailer_id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_retailer_ids = set(row[0] for row in cursor.fetchall())

        # 2. 전체 모니터링 대상 리테일러 목록 (retailer_id, retailer 포함)
        cursor.execute("""
            SELECT retailer_id, retailer FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = 1
        """)
        all_targets_map = {row[0]: row[1] for row in cursor.fetchall()}
        all_retailer_ids = set(all_targets_map.keys())

        # 3. 미저장 리테일러 자동 저장 (파일 정보 제외)
        unsaved_retailer_ids = all_retailer_ids - saved_retailer_ids
        auto_saved_count = 0
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        for retailer_id in unsaved_retailer_ids:
            retailer = all_targets_map[retailer_id]
            stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
            if not stats:
                continue

            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                    crawl_date, retailer_id, expected_count, final_batch_count, total_count,
                    completion_rate, rerun_count, file_name, file_size,
                    anomaly_total, anomaly_title_null, anomaly_image_null,
                    anomaly_partial_null, anomaly_price_zero,
                    memo, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, '', 0, %s, %s
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
                now, user_id
            ))
            auto_saved_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{crawl_date} 일괄 현황 저장 완료',
            'saved_count': auto_saved_count,
            'total_retailers': len(all_retailer_ids),
            'already_saved': len(saved_retailer_ids)
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def save_file_info(crawl_date, user_id):
    """
    파일서버에서 파일 정보 조회 후 전체 리테일러 file_name, file_size 업데이트

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - user_id: 사용자 ID (str)

    반환: dict with success/message/updated_count/file_info_count
    """
    try:
        if not crawl_date:
            return {'success': False, 'error': 'crawl_date가 필요합니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
            cursor.close()
            conn.close()
            return {'success': False, 'error': '이미 마감된 날짜입니다.'}

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        all_retailers_count = len(all_targets)

        # 현황 테이블에 저장된 리테일러 수
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_count = cursor.fetchone()[0]

        # 모든 리테일러가 저장되어 있어야 파일 정보 저장 가능
        if saved_count < all_retailers_count:
            cursor.close()
            conn.close()
            return {
                'success': False,
                'error': f'일괄 현황 저장이 먼저 필요합니다. (저장: {saved_count}/{all_retailers_count})'
            }

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        # 파일서버에서 파일 정보 조회
        file_info_cache = get_file_info_for_date(target_date)

        # 전체 리테일러 목록 (retailer_id, retailer 포함)
        cursor.execute("""
            SELECT retailer_id, retailer FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = 1
        """)
        targets_list = cursor.fetchall()

        # 각 리테일러별로 파일 정보 업데이트
        updated_count = 0
        for target_row in targets_list:
            retailer_id = target_row[0]
            retailer = target_row[1]
            retailer_file = file_info_cache.get(retailer, {})
            file_name = retailer_file.get('file_name', '')
            file_size = retailer_file.get('file_size', 0)

            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_daily
                SET file_name = %s, file_size = %s, updated_at = %s, updated_id = %s
                WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
            """, (file_name, file_size, now, user_id, crawl_date, retailer_id))
            updated_count += cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{crawl_date} 파일 정보 저장 완료',
            'updated_count': updated_count,
            'file_info_count': len(file_info_cache)
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def close_report(crawl_date, user_id):
    """
    일별 최종 마감
    - 모든 리테일러가 현황 테이블에 저장되어 있어야 마감 가능
    - report_close 테이블에 마감 상태 저장
    - report_close_history 테이블에 이력 저장

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - user_id: 사용자 ID (str)

    반환: dict with success/message
    """
    try:
        if not crawl_date:
            return {'success': False, 'error': 'crawl_date가 필요합니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
            cursor.close()
            conn.close()
            return {'success': False, 'error': '이미 마감된 날짜입니다.'}

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        all_retailers_count = len(all_targets)

        # 현황 테이블에 저장된 리테일러 수
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_count = cursor.fetchone()[0]

        # 모든 리테일러가 저장되어 있어야 마감 가능
        if saved_count < all_retailers_count:
            cursor.close()
            conn.close()
            return {
                'success': False,
                'error': f'일괄 현황 저장이 먼저 필요합니다. (저장: {saved_count}/{all_retailers_count})'
            }

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 마감 상태 저장 (report_close 테이블)
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close
                (crawl_date, is_closed, closed_at, closed_id, created_at, updated_at)
            VALUES (%s, 1, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_closed = 1, closed_at = %s, closed_id = %s, updated_at = %s
        """, (crawl_date, now, user_id, now, now, now, user_id, now))

        # 마감 이력 저장 (report_close_history 테이블)
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close_history
                (crawl_date, action, action_at, action_id)
            VALUES (%s, 'close', %s, %s)
        """, (crawl_date, now, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{crawl_date} 마감 완료'
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def cancel_close_report(crawl_date, user_id, memo):
    """
    마감 취소
    - report_close 테이블의 is_closed = 0 으로 변경
    - report_close_history 테이블에 cancel 이력 저장

    파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - user_id: 사용자 ID (str)
    - memo: 취소 사유 (str)

    반환: dict with success/message
    """
    try:
        if not crawl_date:
            return {'success': False, 'error': 'crawl_date가 필요합니다.'}

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 마감 상태 확인
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if not close_row or close_row[0] != 1:
            cursor.close()
            conn.close()
            return {'success': False, 'error': '마감되지 않은 날짜입니다.'}

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 마감 취소 (is_closed = 0)
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_close
            SET is_closed = 0, updated_at = %s
            WHERE crawl_date = %s
        """, (now, crawl_date))

        # 취소 이력 저장
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close_history
                (crawl_date, action, action_at, action_id, memo)
            VALUES (%s, 'cancel', %s, %s, %s)
        """, (crawl_date, now, user_id, memo))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'success': True,
            'message': f'{crawl_date} 마감 취소 완료'
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def get_report_status(target_date):
    """
    날짜별 저장/마감 현황 조회

    파라미터:
    - target_date: 수집일자 (YYYY-MM-DD str), None이면 어제 날짜

    반환: dict with success/date/is_closed/saved_retailers
    """
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜별 마감 여부 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (target_date,))
        close_row = cursor.fetchone()
        is_closed = close_row[0] == 1 if close_row else False

        # 리테일러별 저장 현황
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
            'is_closed': is_closed,
            'saved_retailers': saved_retailers
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def get_report_list(target_date, retailer_filter, view_mode):
    """
    저장된 이상치 목록 조회 (보고서 관리용)

    파라미터:
    - target_date: 수집일자 (YYYY-MM-DD str), None이면 어제 날짜
    - retailer_filter: 리테일러명 (str or None, 없으면 전체)
    - view_mode: 'status'(현황) | 'detail'(상세) - 기본 'status'

    반환: dict with success/date/view/is_closed/daily_reports/anomalies/...
    """
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    if not view_mode:
        view_mode = 'status'

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜별 마감 여부 및 마감 정보 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed, closed_at, closed_id FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (target_date,))
        close_row = cursor.fetchone()
        is_closed = close_row[0] == 1 if close_row else False
        closed_at = close_row[1].strftime('%Y-%m-%d %H:%M:%S') if close_row and close_row[1] else None
        closed_id = close_row[2] if close_row else None

        # 리테일러별 일일 보고서 목록 조회 (ds_monitoring_targets.sort_order 순서)
        daily_query = """
            SELECT d.id, t.retailer, d.expected_count, d.final_batch_count, d.total_count,
                   d.completion_rate, d.rerun_count, d.anomaly_total, d.anomaly_title_null,
                   d.anomaly_image_null, d.anomaly_partial_null, d.anomaly_price_zero,
                   d.memo, d.created_at, d.created_id, d.file_name, d.file_size,
                   t.instance_id
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date = %s AND d.is_del = 0
        """
        params = [target_date]
        if retailer_filter:
            daily_query += " AND t.retailer = %s"
            params.append(retailer_filter)
        daily_query += " ORDER BY t.sort_order, t.retailer"

        cursor.execute(daily_query, params)
        daily_rows = cursor.fetchall()

        daily_reports = []
        for row in daily_rows:
            instance_id = row[17] if len(row) > 17 else None
            daily_reports.append({
                'id': row[0],
                'retailer': row[1],
                'expected_count': row[2],
                'final_batch_count': row[3],
                'total_count': row[4],
                'completion_rate': float(row[5]) if row[5] else 0,
                'rerun_count': row[6],
                'anomaly_total': row[7],
                'anomaly_title_null': row[8],
                'anomaly_image_null': row[9],
                'anomaly_partial_null': row[10],
                'anomaly_price_zero': row[11],
                'memo': row[12] or '',
                'created_at': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else None,
                'created_id': row[14],
                'file_name': row[15] or '',
                'file_size': row[16] or 0,
                'has_screenshot': bool(instance_id)
            })

        anomalies = []
        cause_options = {}

        if view_mode == 'detail':
            # 상세 모드: 이상치 전체 목록 조회
            anomaly_query = """
                SELECT a.id, t.retailer, a.country_code, a.title, a.retailprice, a.ships_from, a.sold_by,
                       a.imageurl, a.producturl, a.retailersku, a.screenshot_id, a.cause, a.memo, a.created_at, a.created_id,
                       a.updated_at, a.updated_id
                FROM ssd_crawl_db.ds_monitoring_report_anomaly a
                LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
                WHERE a.crawl_date = %s AND a.is_del = 0
            """
            params = [target_date]
            if retailer_filter:
                anomaly_query += " AND t.retailer = %s"
                params.append(retailer_filter)
            anomaly_query += " ORDER BY t.sort_order, t.retailer, a.id"

            cursor.execute(anomaly_query, params)
            anomaly_rows = cursor.fetchall()

            for row in anomaly_rows:
                anomalies.append({
                    'id': row[0],
                    'retailer': row[1],
                    'country_code': row[2],
                    'title': row[3],
                    'retailprice': row[4],
                    'ships_from': row[5],
                    'sold_by': row[6],
                    'imageurl': row[7],
                    'producturl': row[8],
                    'retailersku': row[9] or '',
                    'screenshot_id': row[10],
                    'cause': row[11],
                    'memo': row[12],
                    'created_at': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else None,
                    'created_id': row[14],
                    'updated_at': row[15].strftime('%Y-%m-%d %H:%M:%S') if row[15] else None,
                    'updated_id': row[16]
                })

            # 리테일러별 원인 옵션 조회
            cursor.execute("""
                SELECT t.retailer, o.option_name
                FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options o
                JOIN ssd_crawl_db.ds_monitoring_targets t ON o.retailer_id = t.retailer_id
                WHERE o.is_active = 1
                ORDER BY t.retailer, o.sort_order, o.option_id
            """)
            cause_rows = cursor.fetchall()
            for row in cause_rows:
                retailer = row[0]
                option_name = row[1]
                if retailer not in cause_options:
                    cause_options[retailer] = []
                cause_options[retailer].append(option_name)

        # 리테일러별 원인 카운트 요약 조회 (현황 메모 자동입력용)
        cause_summary_query = """
            SELECT t.retailer,
                   COALESCE(a.cause, '') as cause,
                   COUNT(*) as cnt
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.crawl_date = %s AND a.is_del = 0
            GROUP BY t.retailer, a.cause
            ORDER BY t.retailer, cnt DESC
        """
        cursor.execute(cause_summary_query, [target_date])
        cause_summary_rows = cursor.fetchall()
        cause_summary = {}
        for row in cause_summary_rows:
            retailer = row[0]
            cause = row[1] or '미입력'
            cnt = row[2]
            if retailer not in cause_summary:
                cause_summary[retailer] = {}
            cause_summary[retailer][cause] = cnt

        # 이상치 요약 카운트 조회 (현황/상세 공통)
        summary_query = """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN a.cause IS NOT NULL AND a.cause != '' THEN 1 ELSE 0 END) as filled_cause,
                   SUM(CASE WHEN a.memo IS NOT NULL AND a.memo != '' THEN 1 ELSE 0 END) as filled_memo
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            WHERE a.crawl_date = %s AND a.is_del = 0
        """
        summary_params = [target_date]
        if retailer_filter:
            summary_query += """ AND a.retailer_id IN (
                SELECT t.retailer_id FROM ssd_crawl_db.ds_monitoring_targets t WHERE t.retailer = %s
            )"""
            summary_params.append(retailer_filter)
        cursor.execute(summary_query, summary_params)
        summary_row = cursor.fetchone()
        total_anomalies = summary_row[0] if summary_row else 0
        filled_cause = summary_row[1] if summary_row else 0
        filled_memo = summary_row[2] if summary_row else 0

        # 리테일러별 스크린샷 캡쳐 현황 조회
        screenshot_query = """
            SELECT t.retailer,
                   COUNT(*) as total,
                   SUM(CASE WHEN a.screenshot_id IS NOT NULL THEN 1 ELSE 0 END) as captured
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.crawl_date = %s AND a.is_del = 0
            GROUP BY t.retailer
        """
        cursor.execute(screenshot_query, [target_date])
        screenshot_rows = cursor.fetchall()
        screenshot_status_by_retailer = {}
        total_screenshots = 0
        captured_screenshots = 0
        for row in screenshot_rows:
            screenshot_status_by_retailer[row[0]] = {'total': row[1], 'captured': row[2]}
            total_screenshots += row[1]
            captured_screenshots += row[2]

        # 캡쳐 로그: 30분 넘은 running → failed 자동 정리 (비정상 종료 안전장치)
        running_captures = {}
        try:
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_capture_log
                SET status = 'failed'
                WHERE crawl_date = %s AND status = 'running'
                AND triggered_at < %s
            """, (target_date, datetime.now() - timedelta(minutes=30)))
            if cursor.rowcount > 0:
                conn.commit()

            # 30분 이내 running 조회
            cursor.execute("""
                SELECT t.retailer, cl.triggered_at
                FROM ssd_crawl_db.ds_monitoring_capture_log cl
                JOIN ssd_crawl_db.ds_monitoring_targets t ON cl.retailer_id = t.retailer_id
                WHERE cl.crawl_date = %s AND cl.status = 'running'
                AND cl.triggered_at >= %s
            """, (target_date, datetime.now() - timedelta(minutes=30)))
            for row in cursor.fetchall():
                running_captures[row[0]] = row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else None
        except:
            pass

        # daily_reports에 all_screenshots_captured + capture_running 필드 추가
        for report in daily_reports:
            retailer = report['retailer']
            status = screenshot_status_by_retailer.get(retailer, {'total': 0, 'captured': 0})
            report['all_screenshots_captured'] = status['total'] > 0 and status['total'] == status['captured']
            report['capture_running'] = retailer in running_captures

        cursor.close()
        conn.close()

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        total_retailers = len(all_targets)

        return {
            'success': True,
            'date': target_date,
            'view': view_mode,
            'is_closed': is_closed,
            'closed_at': closed_at,
            'closed_id': closed_id,
            'daily_reports': daily_reports,
            'anomalies': anomalies,
            'total_anomalies': total_anomalies,
            'filled_cause': filled_cause,
            'filled_memo': filled_memo,
            'total_screenshots': total_screenshots,
            'captured_screenshots': captured_screenshots,
            'total_retailers': total_retailers,
            'cause_options': cause_options,
            'cause_summary': cause_summary
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}


def get_file_size_history(end_date, days):
    """
    최근 N일간 리테일러별 파일 용량 조회

    파라미터:
    - end_date: 기준일 (date 객체 or None, None이면 어제)
    - days: 조회 일수 (int, 기본 7, 최대 90)

    반환: dict with dates/retailers
    """
    if days is None:
        days = 7
    try:
        days = max(1, min(int(days), 90))
    except (ValueError, TypeError):
        days = 7

    if not end_date:
        end_date = date.today() - timedelta(days=1)

    start_date = end_date - timedelta(days=days - 1)

    conn = None
    cursor = None
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜 목록 생성
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        # 리테일러별 파일 용량 조회 (sort_order 순서)
        cursor.execute("""
            SELECT t.retailer, d.crawl_date, d.file_size
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date BETWEEN %s AND %s AND d.is_del = 0
            ORDER BY t.sort_order, t.retailer, d.crawl_date
        """, (start_date, end_date))
        rows = cursor.fetchall()

        # 리테일러별로 그룹화
        retailer_data = {}
        retailer_order = []

        for retailer, crawl_date, file_size in rows:
            if retailer not in retailer_data:
                retailer_data[retailer] = {}
                retailer_order.append(retailer)
            # crawl_date가 문자열이면 그대로, date 객체면 변환
            date_key = crawl_date if isinstance(crawl_date, str) else crawl_date.strftime('%Y-%m-%d')
            retailer_data[retailer][date_key] = file_size or 0

        # 결과 포맷
        retailers = []
        for retailer in retailer_order:
            sizes = [retailer_data[retailer].get(d, 0) for d in dates]
            valid_sizes = [s for s in sizes if s > 0]
            avg = round(sum(valid_sizes) / len(valid_sizes)) if valid_sizes else 0
            retailers.append({
                'retailer': retailer,
                'sizes': sizes,
                'avg': avg
            })

        return {
            'dates': dates,
            'retailers': retailers
        }

    except Exception as e:
        log_error(e)
        return {'success': False, 'error': str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
