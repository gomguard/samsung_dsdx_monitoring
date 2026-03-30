"""
DS Layer 2 Stats Service: 데이터 품질 검수 비즈니스 로직
"""
from datetime import datetime
from apps.common.db import ds_connection
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance
from apps.common.response import log_error
from apps.ds.ds_layer4.report.report_services import is_report_closed
from . import stats_repositories

def get_layer_stats(target_date, batch_view):
    data = {'timestamp': datetime.now().isoformat(), 'date': str(target_date), 'layer': 2, 'data_source': 'ds', 'results': [], 'summary': {}}
    try:
        with ds_connection() as (conn, cursor):
            close_result = is_report_closed(str(target_date), existing=(conn, cursor))
            is_closed = close_result.get('is_closed', False)
            closed_data = {}
            if is_closed:
                try:
                    cursor.execute("""
                        SELECT t.retailer, r.expected_count, r.total_count, r.anomaly_total, r.anomaly_title_null, r.anomaly_image_null, r.anomaly_partial_null, r.anomaly_price_zero, r.final_batch_count
                        FROM ssd_crawl_db.ds_monitoring_report_daily r JOIN ssd_crawl_db.ds_monitoring_targets t ON r.retailer_id = t.retailer_id WHERE r.crawl_date = %s AND r.is_del = 0
                    """, (target_date,))
                    for row in cursor.fetchall():
                        anomaly_total = row[3] or 0
                        a_title_null = row[4] or 0
                        a_image_null = row[5] or 0
                        a_partial_null = row[6] or 0
                        a_price_zero = row[7] or 0
                        a_imageurl_invalid = max(0, anomaly_total - a_title_null - a_price_zero - a_partial_null)
                        snap_total = row[2] or 0
                        snap_final = row[8] or 0
                        closed_data[row[0]] = {
                            'expected_count': row[1] or 0, 'total': snap_total, 'final_batch_count': snap_final,
                            'title_null': a_title_null, 'imageurl_null': a_image_null, 'null_union': a_title_null,
                            'imageurl_invalid': a_imageurl_invalid, 'price_zero': a_price_zero, 'partial_null': a_partial_null,
                            'all_null': 0, 'valid': max(0, snap_total - anomaly_total), 'valid_final': max(0, snap_final - anomaly_total),
                            'error_count': anomaly_total,
                        }
                except: is_closed = False

            batches_by_retailer = stats_repositories.fetch_batches_for_date(target_date)
            results, total_records = [], 0
            stats_keys = ['title_null','imageurl_null','null_union','imageurl_invalid','price_zero','partial_null','all_null','valid']
            totals = {k:0 for k in stats_keys}

            for idx, (table_name, retailer, region, korea_time, country, mall_name, instance_id, schedule_name) in enumerate(load_monitoring_targets_with_instance(), 1):
                retailer_batches = batches_by_retailer.get(retailer, [])
                if is_closed and retailer in closed_data:
                    snap = closed_data[retailer]
                    total, valid = (snap['final_batch_count'], snap['valid_final']) if (batch_view == 'final' and snap['final_batch_count'] != snap['total']) else (snap['total'], snap['valid'])
                    error_count = snap['error_count']
                    status = 'pending' if total == 0 else ('success' if error_count == 0 else ('warning' if error_count < total * 0.05 else 'danger'))
                    
                    total_records += total
                    for k in stats_keys: totals[k] += snap[k] if k != 'valid' else valid
                    
                    results.append({
                        'no': idx, 'table_name': table_name, 'retailer': retailer, 'region': region, 'country': country, 'mall_name': mall_name,
                        'total': total, 'expected_count': snap['expected_count'],
                        'title_null': snap['title_null'], 'imageurl_null': snap['imageurl_null'], 'null_union': snap['null_union'],
                        'imageurl_invalid': snap['imageurl_invalid'], 'price_zero': snap['price_zero'], 'partial_null': snap['partial_null'],
                        'all_null': snap['all_null'], 'valid': valid, 'error_count': error_count, 'status': status,
                        'batch_count': 0, 'has_multi_batch': False, 'batches': [], 'final_start_time': None, 'final_end_time': None, 'has_screenshot': bool(instance_id)
                    })
                    continue

                final_start_time, final_end_time = None, None
                if len(retailer_batches) >= 2 and batch_view == 'final':
                    final_start_time = retailer_batches[-1]['start_time']
                    quality = stats_repositories.fetch_quality_counts_by_time_range(cursor, table_name, target_date, final_start_time, None)
                else:
                    quality = stats_repositories.fetch_quality_counts(cursor, table_name, target_date)

                total = quality.get('total', 0)
                total_records += total
                expected_count = stats_repositories.fetch_expected_count(cursor, country, mall_name)
                
                for k in stats_keys: totals[k] += quality.get(k, 0)
                error_count = quality.get('null_union',0) + quality.get('imageurl_invalid',0) + quality.get('price_zero',0) + quality.get('partial_null',0)
                status = 'pending' if total == 0 else ('success' if error_count == 0 else ('warning' if error_count < total * 0.05 else 'danger'))
                
                batch_count = len(retailer_batches)
                has_multi_batch = batch_count >= 2 and batch_view == 'all'
                batch_details = []
                if has_multi_batch:
                    for i, batch in enumerate(retailer_batches):
                        st = batch['start_time']
                        et = retailer_batches[i+1]['start_time'] if i+1 < len(retailer_batches) else None
                        bq = stats_repositories.fetch_quality_counts_by_time_range(cursor, table_name, target_date, st, et)
                        batch_details.append({
                            'id': batch['id'], 'start_time': st, 'end_time': et if et else '다음날', 'memo': batch['memo'],
                            'total': bq.get('total',0), 'null_union': bq.get('null_union',0), 'imageurl_invalid': bq.get('imageurl_invalid',0),
                            'partial_null': bq.get('partial_null',0), 'error_count': bq.get('null_union',0) + bq.get('imageurl_invalid',0) + bq.get('price_zero',0) + bq.get('partial_null',0)
                        })

                results.append({
                    'no': idx, 'table_name': table_name, 'retailer': retailer, 'region': region, 'country': country, 'mall_name': mall_name,
                    'total': total, 'expected_count': expected_count,
                    'title_null': quality.get('title_null',0), 'imageurl_null': quality.get('imageurl_null',0), 'null_union': quality.get('null_union',0),
                    'imageurl_invalid': quality.get('imageurl_invalid',0), 'price_zero': quality.get('price_zero',0), 'partial_null': quality.get('partial_null',0),
                    'all_null': quality.get('all_null',0), 'valid': quality.get('valid',0), 'error_count': error_count, 'status': status,
                    'batch_count': batch_count, 'has_multi_batch': has_multi_batch, 'batches': batch_details, 'final_start_time': final_start_time, 'final_end_time': final_end_time, 'has_screenshot': bool(instance_id)
                })

            total_error = totals['null_union'] + totals['imageurl_invalid'] + totals['price_zero'] + totals['partial_null']
            overall_status = 'pending' if total_records == 0 else ('success' if total_error == 0 else ('warning' if total_error < total_records * 0.05 else 'danger'))
            
            data['results'] = results
            data['summary'] = {
                'total_tables': len(load_monitoring_targets()), 'total_records': total_records,
                **totals, 'total_error': total_error, 'status': overall_status, 'is_closed': is_closed
            }
    except Exception as e:
        data['error'] = log_error(e)
    return data

def get_table_null_detail(target_date, table_name, error_type, page, page_size, start_time, end_time, sort_by, sort_order):
    data = {'timestamp': datetime.now().isoformat(), 'date': str(target_date), 'table': table_name, 'error_type': error_type, 'page': page, 'page_size': page_size, 'data': []}
    res = stats_repositories.fetch_table_null_detail(table_name, target_date, error_type, page, page_size, start_time, end_time, sort_by, sort_order)
    if res:
        items = []
        for row in res['rows']:
            crawl_dt = row[7] or ''
            if crawl_dt and len(crawl_dt) >= 14: crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:{crawl_dt[12:14]}"
            elif crawl_dt and len(crawl_dt) >= 12: crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:00"
            items.append({'title': row[0] or '', 'retailprice': row[1] or '', 'ships_from': row[2] or '', 'sold_by': row[3] or '', 'imageurl': row[4] or '', 'producturl': row[5] or '', 'retailersku': row[6] or '', 'crawl_datetime': crawl_dt})
        
        retailer_info = next((t for t in load_monitoring_targets() if t[0] == table_name), None)
        data['retailer'] = retailer_info[1] if retailer_info else table_name
        data['region'] = retailer_info[2] if retailer_info else ''
        data['country'] = retailer_info[4] if retailer_info else ''
        data['total_count'] = res['total_count']
        data['total_pages'] = (res['total_count'] + page_size - 1) // page_size if res['total_count'] > 0 else 1
        data['data'] = items
        data['sort_by'] = sort_by
        data['sort_order'] = sort_order
        if start_time: data['time_range'] = f"{start_time} ~ {end_time if end_time else '다음날'}"
    return data
