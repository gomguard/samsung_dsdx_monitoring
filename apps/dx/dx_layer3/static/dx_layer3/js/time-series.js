async function loadTimeSeriesPage(date, checkName, detailCode, days) {
    days = days || 1;
    var catContainer = document.getElementById('categories-container') || document.getElementById('category-checks');
    if (!catContainer) return;

    // detail_code 결정
    if (!detailCode) {
        if (checkName.includes('HHP') && checkName.includes('중앙값')) detailCode = 'hhp_price_median';
        else if (checkName.includes('HHP') && checkName.includes('/mo')) detailCode = 'hhp_price_format';
        else if (checkName.includes('TV') && checkName.includes('중앙값')) detailCode = 'tv_price_median';
    }
    if (!detailCode) { catContainer.innerHTML = '<div class="l3-empty">알 수 없는 검증 유형입니다.</div>'; return; }

    catContainer.innerHTML = '<div class="loading">데이터를 불러오는 중...</div>';

    try {
        var apiUrl = '/layer3/api/time-series-detail/?date=' + date + '&detail_code=' + encodeURIComponent(detailCode) + '&days=' + days;
        var res = await fetch(apiUrl);
        var data = await res.json();

        var anomalyCount = data.anomaly_count || 0;
        var itemCount = (data.items && data.items.length) || 0;

        var html = '<button class="btn-back" onclick="window.location.href=\'/dx/layer3/time-series/?date=' + date + '\'">← 뒤로가기</button>';
        html += '<div class="inline-detail-view">';
        html += '<div class="inline-detail-header"><div>';
        html += '<div class="inline-detail-title">' + esc(checkName) + ' (' + anomalyCount + '건)</div>';
        html += '<div class="inline-detail-subtitle">' + esc(data.error_message || '') + '</div>';
        html += '</div><div style="display:flex;align-items:center;">';
        html += '<div style="display:flex;align-items:center;gap:6px;margin-right:12px;">';
        html += '<label style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">일수:</label>';
        html += '<input type="number" id="ts-days" value="' + days + '" min="1" max="30" style="width:50px;padding:3px 6px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;font-size:12px;text-align:center;" onkeydown="if(event.key===\'Enter\')loadTimeSeriesPage(\'' + date + '\',\'' + esc(checkName).replace(/'/g, "\\'") + '\',\'' + esc(detailCode) + '\',parseInt(document.getElementById(\'ts-days\').value)||1)">';
        html += '<button onclick="loadTimeSeriesPage(\'' + date + '\',\'' + esc(checkName).replace(/'/g, "\\'") + '\',\'' + esc(detailCode) + '\',parseInt(document.getElementById(\'ts-days\').value)||1)" style="padding:3px 10px;font-size:12px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;background:var(--page-color,#0d9488);color:#fff;cursor:pointer;white-space:nowrap;">조회</button>';
        html += '</div>';
        html += '<div class="inline-detail-date">' + date + '</div>';
        html += '</div></div>';

        if (itemCount === 0) {
            html += '<p style="padding:16px 24px;">이상치 데이터가 없습니다.</p>';
        } else {
            html += '<div id="ts-page-table"></div>';
        }
        html += '</div>';
        catContainer.innerHTML = html;

        if (itemCount === 0) return;

        var container = document.getElementById('ts-page-table');
        var columns = [
            { key: 'id', label: 'id', width: 80 },
            { key: 'item', label: 'Item', width: 160 },
            { key: 'account_name', label: 'Retailer', width: 100 },
            { key: 'final_sku_price', label: '가격', width: 120 },
            { key: 'median_price', label: '중앙값(7일)', width: 120 },
            { key: 'crawl_datetime', label: '수집시간', width: 160 },
            { key: 'product_url', label: 'URL', width: 200 }
        ];
        var table = new CommonTable(container, {
            variant: 'detail',
            columns: columns,
            resize: true,
            vlines: true,
            showTotalCount: true
        });
        table.render();

        // item rowspan 계산
        var items = data.items;
        var itemSpans = {};
        var itemSkip = {};
        var si = 0;
        while (si < items.length) {
            var itemVal = items[si].item;
            var ei = si + 1;
            while (ei < items.length && items[ei].item === itemVal) ei++;
            itemSpans[si] = ei - si;
            for (var k = si + 1; k < ei; k++) itemSkip[k] = true;
            si = ei;
        }

        table.renderBody(items, function(row, idx) {
            var h = '<tr>';
            h += '<td>' + esc(String(row.id || '-')) + '</td>';
            if (itemSkip[idx]) {
                // item rowspan 중간행 — td 생략
            } else {
                var span = itemSpans[idx] || 1;
                h += '<td rowspan="' + span + '" style="vertical-align:middle;">' + esc(row.item || '-') + '</td>';
            }
            h += '<td>' + esc(row.account_name || '-') + '</td>';
            h += '<td>' + esc(row.final_sku_price || '-') + '</td>';
            h += '<td>' + esc(row.median_price || '-') + '</td>';
            h += '<td>' + esc(row.crawl_datetime || '-') + '</td>';
            if (row.product_url) {
                h += '<td><a href="' + esc(row.product_url) + '" target="_blank" style="color:var(--page-color);text-decoration:none;">'
                    + '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:3px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
                    + esc(row.product_url) + '</a></td>';
            } else {
                h += '<td>-</td>';
            }
            h += '</tr>';
            return h;
        });
    } catch (e) {
        console.error(e);
        catContainer.innerHTML = '<div class="section-card"><h3>' + esc(checkName) + '</h3><p>오류가 발생했습니다.</p></div>';
    }
}
