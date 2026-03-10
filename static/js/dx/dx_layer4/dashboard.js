/**
 * Layer 4 대시보드
 */

(function() {
    'use strict';

    function loadDashboardStats() {
        var date = getSelectedDate();
        if (!date) return;

        fetch('/dx/layer4/api/dashboard-stats/?date=' + encodeURIComponent(date))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast(data.error || '조회 실패', 'error');
                    return;
                }
                renderDashboard(data);
            })
            .catch(function(e) {
                console.error(e);
                showToast('대시보드 조회 중 오류가 발생했습니다.', 'error');
            });
    }

    function renderDashboard(data) {
        // 요약 카드
        document.getElementById('stat-total').textContent = L4.formatNumber(data.total || 0);
        document.getElementById('stat-corrected').textContent = L4.formatNumber(data.corrected || 0);
        document.getElementById('stat-normal').textContent = L4.formatNumber(data.normal || 0);
        document.getElementById('stat-reverted').textContent = L4.formatNumber(data.reverted || 0);

        // 검증유형별 현황
        var byType = data.by_type || {};
        ['null_check', 'format_check', 'duplicate_check', 'cross_field', 'field_missing'].forEach(function(ct) {
            var el = document.getElementById('type-' + ct);
            if (!el) return;
            var counts = byType[ct];
            if (!counts || Object.keys(counts).length === 0) {
                el.innerHTML = '<span class="l4-no-data">데이터 없음</span>';
                return;
            }
            var html = '';
            ['corrected', 'normal', 'reverted'].forEach(function(st) {
                if (counts[st]) {
                    html += '<div class="l4-type-row">'
                        + '<span class="l4-type-label">' + L4.STATUS_NAMES[st] + '</span>'
                        + '<span class="l4-type-value ' + st + '">' + L4.formatNumber(counts[st]) + '건</span>'
                        + '</div>';
                }
            });
            el.innerHTML = html || '<span class="l4-no-data">데이터 없음</span>';
        });

        // 원인별 현황
        var reasonContainer = document.getElementById('reason-container');
        var reasons = data.by_reason || [];
        if (reasons.length === 0) {
            reasonContainer.innerHTML = '<span class="l4-no-data">데이터 없음</span>';
        } else {
            var maxCount = Math.max.apply(null, reasons.map(function(r) { return r.count; }));
            var html = '<div class="l4-reason-list">';
            reasons.forEach(function(r) {
                var pct = maxCount > 0 ? Math.round(r.count / maxCount * 100) : 0;
                html += '<div class="l4-reason-row">'
                    + '<span class="l4-reason-text">' + L4.escapeHtml(r.reason) + '</span>'
                    + '<span class="l4-reason-count">' + L4.formatNumber(r.count) + '건</span>'
                    + '<div class="l4-reason-bar"><div class="l4-reason-bar-fill" style="width:' + pct + '%"></div></div>'
                    + '</div>';
            });
            html += '</div>';
            reasonContainer.innerHTML = html;
        }

        // 테이블별 현황
        var tableContainer = document.getElementById('table-container');
        var byTable = data.by_table || {};
        var tables = Object.keys(byTable);
        if (tables.length === 0) {
            tableContainer.innerHTML = '<span class="l4-no-data">데이터 없음</span>';
        } else {
            var html = '<table class="l4-table-summary"><thead><tr>'
                + '<th>테이블</th><th>수정</th><th>확인</th><th>취소</th><th>합계</th>'
                + '</tr></thead><tbody>';
            tables.forEach(function(tn) {
                var c = byTable[tn];
                var corrected = c.corrected || 0;
                var normal = c.normal || 0;
                var reverted = c.reverted || 0;
                var total = corrected + normal + reverted;
                html += '<tr>'
                    + '<td>' + L4.escapeHtml(tn) + '</td>'
                    + '<td style="color:#3b82f6;font-weight:600;">' + L4.formatNumber(corrected) + '</td>'
                    + '<td style="color:#10b981;font-weight:600;">' + L4.formatNumber(normal) + '</td>'
                    + '<td style="color:#ef4444;font-weight:600;">' + L4.formatNumber(reverted) + '</td>'
                    + '<td style="font-weight:700;">' + L4.formatNumber(total) + '</td>'
                    + '</tr>';
            });
            html += '</tbody></table>';
            tableContainer.innerHTML = html;
        }
    }

    // 핸들러 등록
    L4._sectionHandler['dashboard'] = loadDashboardStats;

})();
