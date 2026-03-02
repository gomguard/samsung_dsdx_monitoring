/**
 * Layer 4: 검수 확인 / 보고서 (Review & Report)
 */

(function() {
    'use strict';

    var section = (window.LAYER4 && window.LAYER4.section) || 'dashboard';
    var currentPage = 1;
    var currentReportTab = 'detail';
    var reportCache = null;

    // 검증유형 표시 이름
    var TYPE_NAMES = {
        'null_check': 'NULL 검증',
        'format_check': '형식 검증',
        'duplicate_check': '중복 검증',
        'cross_field': '크로스필드 검증'
    };

    var STATUS_NAMES = {
        'corrected': '수정',
        'normal': '확인',
        'reverted': '취소'
    };

    // ============================================================
    // 사이드바 클릭 핸들러
    // ============================================================
    window.onSubitemClick = function(groupKey, itemName) {
        var date = typeof getSelectedDate === 'function' ? getSelectedDate() : '';
        var params = [];
        if (date) params.push('date=' + date);
        if (itemName) params.push('focus=' + encodeURIComponent(itemName));
        var qs = params.length > 0 ? '?' + params.join('&') : '';

        if (groupKey === 'check_log') {
            window.location.href = '/dx/layer4/check-log/' + qs;
        } else if (groupKey === 'corrections') {
            window.location.href = '/dx/layer4/corrections/' + qs;
        } else if (groupKey === 'report') {
            window.location.href = '/dx/layer4/report/' + qs;
        }
    };

    // ============================================================
    // 공통
    // ============================================================
    window.handleSearch = function() {
        if (section === 'dashboard') {
            loadDashboardStats();
        } else if (section === 'check_log') {
            loadCheckLog();
        } else if (section === 'corrections') {
            currentPage = 1;
            loadCorrections();
        } else if (section === 'report') {
            loadReport();
        }
    };

    // ============================================================
    // 마감기록 (check_log)
    // ============================================================
    var CHECK_SECTION_NAMES = {
        retail: 'Retail',
        sentiment: '감성분석',
        youtube: 'YouTube',
        market_trend: 'Market Trend',
        market_competitor: 'Market Competitor',
        market_competitor_event: 'Competitor Event',
        market_demand: '수요증감율',
        market_promotion: 'Promotion'
    };

    var currentCheckTab = 'active';

    window.switchCheckTab = function(tab) {
        currentCheckTab = tab;
        document.getElementById('tabActive').classList.toggle('active', tab === 'active');
        document.getElementById('tabDeleted').classList.toggle('active', tab === 'deleted');
        document.getElementById('tableActive').style.display = tab === 'active' ? '' : 'none';
        document.getElementById('tableDeleted').style.display = tab === 'deleted' ? '' : 'none';
    };

    function loadCheckLog() {
        var date = getSelectedDate();
        if (!date) return;

        fetch('/dx/layer4/api/check/log/?date=' + encodeURIComponent(date) + '&layer=1')
            .then(function(r) { return r.json(); })
            .then(function(result) {
                if (!result.success) {
                    showToast(result.error || '조회 실패', 'error');
                    return;
                }
                renderCheckLog(date, result.logs, result.active_count, result.total_sections);
            })
            .catch(function(e) {
                console.error(e);
                showToast('마감기록 조회 중 오류가 발생했습니다.', 'error');
            });
    }

    function fmtTime(isoStr) {
        if (!isoStr) return '-';
        var d = new Date(isoStr);
        return d.toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function renderCheckLog(dateStr, logs, activeCount, totalSections) {
        var activeLogs = logs.filter(function(l) { return l.is_del === 0; });
        var deletedLogs = logs.filter(function(l) { return l.is_del === 1; });

        // 요약 카드
        var acEl = document.getElementById('active-count');
        if (acEl) {
            acEl.textContent = activeCount + ' / ' + totalSections;
            acEl.style.color = activeCount === totalSections ? 'var(--color-ok)' : (activeCount > 0 ? '#d97706' : 'var(--text-secondary)');
        }
        var tlEl = document.getElementById('total-logs');
        if (tlEl) tlEl.textContent = logs.length;
        var dcEl = document.getElementById('deleted-count');
        if (dcEl) {
            dcEl.textContent = deletedLogs.length;
            dcEl.style.color = deletedLogs.length > 0 ? 'var(--color-critical)' : 'var(--text-secondary)';
        }

        // 탭 카운트
        var acBadge = document.getElementById('tabActiveCount');
        if (acBadge) {
            acBadge.textContent = activeLogs.length;
            acBadge.className = 'tab-count ' + (activeLogs.length > 0 ? 'count-active' : 'count-zero');
        }
        var delBadge = document.getElementById('tabDeletedCount');
        if (delBadge) {
            delBadge.textContent = deletedLogs.length;
            delBadge.className = 'tab-count ' + (deletedLogs.length > 0 ? 'count-deleted' : 'count-zero');
        }

        // 현재 상태 테이블
        var tbodyActive = document.getElementById('tbody-active');
        if (tbodyActive) {
            if (activeLogs.length === 0) {
                tbodyActive.innerHTML = '<tr><td colspan="5" class="cl-empty-state">확인된 섹션이 없습니다.</td></tr>';
            } else {
                var rows = '';
                activeLogs.forEach(function(log) {
                    var name = CHECK_SECTION_NAMES[log.section] || log.section;
                    var statusClass = log.status === 'CRITICAL' ? 'badge-critical' : (log.status === 'WARNING' ? 'badge-warning' : 'badge-ok');
                    var stepBadge = '';
                    if (log.confirm_step === 2) stepBadge = ' <span class="badge badge-ok" style="font-size:11px;">완료</span>';
                    else if (log.confirm_step === 1) stepBadge = ' <span class="badge badge-warning" style="font-size:11px;">1차</span>';
                    var memoHtml = log.memo
                        ? '<span class="memo-cell memo-text" onclick="toggleMemoEditor(' + log.id + ', this)">' + escapeHtml(log.memo) + '</span>'
                        : '<span class="memo-cell memo-empty" onclick="toggleMemoEditor(' + log.id + ', this)">+ 메모 추가</span>';
                    var detailUrl = '/dx/layer4/check-log/detail/?date=' + dateStr + '&section=' + log.section;
                    rows += '<tr>'
                        + '<td><a href="' + detailUrl + '" style="color:var(--text-primary);text-decoration:none;font-weight:500;">' + escapeHtml(name) + ' &rsaquo;</a>' + stepBadge + '</td>'
                        + '<td><span class="badge ' + statusClass + '">' + escapeHtml(log.status) + '</span></td>'
                        + '<td>' + escapeHtml(log.created_id) + '</td>'
                        + '<td><span class="time-text">' + fmtTime(log.created_at) + '</span></td>'
                        + '<td>' + memoHtml + '</td>'
                        + '</tr>';
                });
                tbodyActive.innerHTML = rows;
            }
        }

        // 취소 이력 테이블
        var tbodyDeleted = document.getElementById('tbody-deleted');
        if (tbodyDeleted) {
            if (deletedLogs.length === 0) {
                tbodyDeleted.innerHTML = '<tr><td colspan="7" class="cl-empty-state">취소 이력이 없습니다.</td></tr>';
            } else {
                var drows = '';
                deletedLogs.forEach(function(dl) {
                    var dname = CHECK_SECTION_NAMES[dl.section] || dl.section;
                    var dstatusClass = dl.status === 'CRITICAL' ? 'badge-critical' : (dl.status === 'WARNING' ? 'badge-warning' : 'badge-ok');
                    drows += '<tr>'
                        + '<td>' + escapeHtml(dname) + '</td>'
                        + '<td><span class="badge ' + dstatusClass + '">' + escapeHtml(dl.status) + '</span></td>'
                        + '<td>' + escapeHtml(dl.created_id) + '</td>'
                        + '<td><span class="time-text">' + fmtTime(dl.created_at) + '</span></td>'
                        + '<td>' + escapeHtml(dl.updated_id || dl.created_id) + '</td>'
                        + '<td><span class="time-text">' + fmtTime(dl.updated_at) + '</span></td>'
                        + '<td>' + (dl.delete_memo ? '<span class="memo-text" title="' + escapeHtml(dl.delete_memo) + '">' + escapeHtml(dl.delete_memo) + '</span>' : '<span style="color:var(--text-secondary);opacity:0.4;">-</span>') + '</td>'
                        + '</tr>';
                });
                tbodyDeleted.innerHTML = drows;
            }
        }
    }

    window.toggleMemoEditor = function(logId, el) {
        var row = el.closest('tr');
        var existing = row.nextElementSibling;
        // 이미 열려 있으면 닫기
        if (existing && existing.classList.contains('memo-editor-row')) {
            existing.remove();
            return;
        }
        // 다른 열린 에디터 닫기
        document.querySelectorAll('.memo-editor-row').forEach(function(r) { r.remove(); });

        var current = el.classList.contains('memo-empty') ? '' : el.textContent;
        var colCount = row.children.length;
        var editorRow = document.createElement('tr');
        editorRow.className = 'memo-editor-row';
        var td = document.createElement('td');
        td.colSpan = colCount;
        td.style.cssText = 'padding:12px 16px;background:var(--bg-secondary);border-top:none;';
        td.innerHTML = '<div>'
            + '<textarea class="memo-editor-textarea" placeholder="메모를 입력하세요" style="width:100%;min-height:60px;padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;font-size:13px;resize:vertical;font-family:inherit;background:var(--bg-primary);color:var(--text-primary);box-sizing:border-box;"></textarea>'
            + '<div style="display:flex;gap:6px;margin-top:8px;justify-content:flex-end;">'
            + '<button class="memo-editor-cancel" style="padding:6px 16px;border-radius:6px;font-size:13px;font-weight:600;border:none;cursor:pointer;background:var(--bg-tertiary);color:var(--text-secondary);">취소</button>'
            + '<button class="memo-editor-save" style="padding:6px 16px;border-radius:6px;font-size:13px;font-weight:600;border:none;cursor:pointer;background:var(--page-color);color:#fff;">저장</button>'
            + '</div></div>';
        editorRow.appendChild(td);
        row.after(editorRow);

        var textarea = td.querySelector('.memo-editor-textarea');
        textarea.value = current;
        textarea.focus();

        td.querySelector('.memo-editor-cancel').onclick = function() { editorRow.remove(); };
        td.querySelector('.memo-editor-save').onclick = async function() {
            var memo = textarea.value.trim();
            try {
                var response = await fetch('/dx/layer4/api/check/memo/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({ id: logId, memo: memo })
                });
                if (!response.ok) throw new Error('HTTP ' + response.status);
                var data = await response.json();
                if (data.success) {
                    showToast('메모 저장됨', 'success');
                    loadCheckLog();
                }
            } catch (e) {
                showToast('시스템 오류가 발생했습니다.', 'error');
            }
        };
    };

    // ============================================================
    // 대시보드
    // ============================================================
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
        document.getElementById('stat-total').textContent = formatNumber(data.total || 0);
        document.getElementById('stat-corrected').textContent = formatNumber(data.corrected || 0);
        document.getElementById('stat-normal').textContent = formatNumber(data.normal || 0);
        document.getElementById('stat-reverted').textContent = formatNumber(data.reverted || 0);

        // 검증유형별 현황
        var byType = data.by_type || {};
        ['null_check', 'format_check', 'duplicate_check', 'cross_field'].forEach(function(ct) {
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
                        + '<span class="l4-type-label">' + STATUS_NAMES[st] + '</span>'
                        + '<span class="l4-type-value ' + st + '">' + formatNumber(counts[st]) + '건</span>'
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
                    + '<span class="l4-reason-text">' + escapeHtml(r.reason) + '</span>'
                    + '<span class="l4-reason-count">' + formatNumber(r.count) + '건</span>'
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
                    + '<td>' + escapeHtml(tn) + '</td>'
                    + '<td style="color:#3b82f6;font-weight:600;">' + formatNumber(corrected) + '</td>'
                    + '<td style="color:#10b981;font-weight:600;">' + formatNumber(normal) + '</td>'
                    + '<td style="color:#ef4444;font-weight:600;">' + formatNumber(reverted) + '</td>'
                    + '<td style="font-weight:700;">' + formatNumber(total) + '</td>'
                    + '</tr>';
            });
            html += '</tbody></table>';
            tableContainer.innerHTML = html;
        }
    }

    // ============================================================
    // 검수기록
    // ============================================================
    // focus 파라미터 → 고정 검증유형
    var FOCUS_TO_TYPE = { 'NULL 검수': 'null_check', '형식 검수': 'format_check', '중복 검수': 'duplicate_check', '크로스필드 검수': 'cross_field' };
    var correctionsFocus = '';
    var correctionsFixedType = '';

    var correctionsFilterBar = null;

    function getActiveType() {
        return correctionsFixedType || (document.getElementById('filter-type') ? document.getElementById('filter-type').value : 'all');
    }

    function isCrossFieldMode() {
        return getActiveType() === 'cross_field';
    }

    function buildCorrectionsFilterBar() {
        var controls = [];

        // focus 없으면 검증유형 드롭다운 표시
        if (!correctionsFixedType) {
            controls.push({
                type: 'select', key: 'filter-type', label: '검증유형',
                options: [
                    { value: 'all', label: '전체' },
                    { value: 'null_check', label: 'NULL 검증' },
                    { value: 'format_check', label: '형식 검증' },
                    { value: 'duplicate_check', label: '중복 검증' },
                    { value: 'cross_field', label: '크로스필드 검증' }
                ],
                onChange: function() {
                    currentPage = 1; correctionsTable = null;
                    // 크로스필드 선택 시 필터바 재구성
                    var newType = document.getElementById('filter-type').value;
                    if ((newType === 'cross_field') !== (correctionsLastType === 'cross_field')) {
                        correctionsLastType = newType;
                        buildCorrectionsFilterBar();
                    }
                    loadCorrections();
                }
            });
        }

        // 크로스필드일 때 카테고리/룰 드롭다운 추가
        if (isCrossFieldMode()) {
            controls.push({
                type: 'select', key: 'filter-category', label: '카테고리',
                options: [
                    { value: 'all', label: '전체' },
                    { value: 'TV', label: 'TV' },
                    { value: 'HHP', label: 'HHP' }
                ],
                onChange: function() { currentPage = 1; correctionsTable = null; loadCorrections(); }
            });
            controls.push({
                type: 'select', key: 'filter-rule', label: '검증규칙명',
                options: [{ value: 'all', label: '전체' }],
                onChange: function() { currentPage = 1; correctionsTable = null; loadCorrections(); }
            });
        }

        controls.push({
            type: 'select', key: 'filter-status', label: '상태',
            options: [
                { value: 'all', label: '전체' },
                { value: 'corrected', label: '수정' },
                { value: 'normal', label: '확인' },
                { value: 'reverted', label: '취소' }
            ],
            onChange: function() { currentPage = 1; correctionsTable = null; loadCorrections(); }
        });

        correctionsFilterBar = new FilterBar('#corrections-filter-bar', { controls: controls, plain: true, sticky: false }).render();

        // 검증유형 드롭다운 값 복원
        if (!correctionsFixedType && correctionsLastType !== 'all') {
            var typeEl = document.getElementById('filter-type');
            if (typeEl) typeEl.value = correctionsLastType;
        }
    }

    var correctionsLastType = 'all';

    function initCorrectionsFilterBar() {
        var focusParam = new URLSearchParams(window.location.search).get('focus') || '';
        correctionsFocus = focusParam;
        correctionsFixedType = FOCUS_TO_TYPE[focusParam] || '';
        correctionsLastType = correctionsFixedType || 'all';
        buildCorrectionsFilterBar();
    }

    window.loadCorrections = function(page) {
        var date = getSelectedDate();
        if (!date) return;

        if (page !== undefined) currentPage = page;
        if (currentPage === 1) correctionsTable = null;

        var type = getActiveType();
        var status = document.getElementById('filter-status') ? document.getElementById('filter-status').value : 'all';
        var category = document.getElementById('filter-category') ? document.getElementById('filter-category').value : 'all';
        var ruleName = document.getElementById('filter-rule') ? document.getElementById('filter-rule').value : 'all';

        var url = '/dx/layer4/api/corrections/?date=' + encodeURIComponent(date)
            + '&type=' + encodeURIComponent(type)
            + '&status=' + encodeURIComponent(status)
            + '&category=' + encodeURIComponent(category)
            + '&rule_name=' + encodeURIComponent(ruleName)
            + '&page=' + currentPage
            + '&page_size=50';

        fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast(data.error || '조회 실패', 'error');
                    return;
                }
                // 룰 드롭다운 갱신
                if (data.rule_options) {
                    updateRuleDropdown(data.rule_options);
                }
                renderCorrections(data);
            })
            .catch(function(e) {
                console.error(e);
                showToast('검수기록 조회 중 오류가 발생했습니다.', 'error');
            });
    };

    function updateRuleDropdown(ruleOptions) {
        var sel = document.getElementById('filter-rule');
        if (!sel) return;
        var currentVal = sel.value;
        var html = '<option value="all">전체</option>';
        ruleOptions.forEach(function(r) {
            html += '<option value="' + escapeHtml(r.name) + '">' + escapeHtml(r.name) + '</option>';
        });
        sel.innerHTML = html;
        // 기존 선택값 복원
        if (currentVal !== 'all') {
            sel.value = currentVal;
            if (sel.value !== currentVal) sel.value = 'all';
        }
    }

    var correctionsTable = null;

    function getCorrectionsColumns() {
        var cols = [
            { key: 'no', label: 'No.', width: 50, align: 'center' }
        ];
        if (!correctionsFixedType) {
            cols.push({ key: 'correction_type', label: '검증유형', width: 90, align: 'center' });
        }
        if (isCrossFieldMode()) {
            cols.push(
                { key: 'table_name', label: '카테고리', width: 60 },
                { key: 'rule_name', label: '검증규칙명', width: 150 },
                { key: 'retailer', label: '리테일러', width: 90 },
                { key: 'record_id', label: 'Record', width: 80 },
                { key: 'column_name', label: '컬럼', width: 140 },
                { key: 'old_value', label: '이전값' },
                { key: 'new_value', label: '변경한 값' },
                { key: 'status', label: '상태', width: 70, align: 'center' },
                { key: 'reason', label: '이유' },
                { key: 'memo', label: '메모' },
                { key: 'created_id', label: '수정자', width: 70 },
                { key: 'created_at', label: '수정일', width: 140 }
            );
        } else {
            cols.push(
                { key: 'table_name', label: '카테고리', width: 60 },
                { key: 'retailer', label: '리테일러', width: 90 },
                { key: 'record_id', label: 'Record', width: 80 },
                { key: 'column_name', label: '컬럼', width: 160 },
                { key: 'old_value', label: '이전값' },
                { key: 'new_value', label: '변경한 값' },
                { key: 'status', label: '상태', width: 70, align: 'center' },
                { key: 'reason', label: '이유' },
                { key: 'memo', label: '메모' },
                { key: 'created_id', label: '수정자', width: 70 },
                { key: 'created_at', label: '수정일', width: 140 }
            );
        }
        return cols;
    }

    function renderCorrections(data) {
        var container = document.getElementById('corrections-table-container');
        var items = data.items || [];

        if (items.length === 0) {
            container.innerHTML = '<div class="l4-empty-state"><p>검수기록이 없습니다.</p></div>';
            correctionsTable = null;
            renderPagination(0, 0, 0);
            return;
        }

        var startNo = (data.page - 1) * data.page_size;

        if (!correctionsTable) {
            container.innerHTML = '';
            correctionsTable = new CommonTable(container, {
                variant: 'detail',
                columns: getCorrectionsColumns(),
                resize: true,
                section: true,
                vlines: true,
                showTotalCount: true
            });
            correctionsTable.render();
        }

        var CATEGORY_NAME = {
            'tv_retail_com': 'TV', 'hhp_retail_com': 'HHP',
            'youtube_collection_logs': 'YouTube', 'youtube_videos': 'YouTube', 'youtube_comments': 'YouTube',
            'market_trend': 'Market Trend', 'market_comp_product': 'Market', 'market_comp_event': 'Market',
            'openai_forecast_results': '수요증감율'
        };
        var crossFieldMode = isCrossFieldMode();
        correctionsTable.renderBody(items, function(item, idx) {
            var statusName = STATUS_NAMES[item.status] || item.status;
            var categoryName = CATEGORY_NAME[item.table_name] || item.table_name;
            var html = '<tr>'
                + '<td style="text-align:center">' + (startNo + idx + 1) + '</td>';
            if (!correctionsFixedType) {
                var typeName = TYPE_NAMES[item.correction_type] || item.correction_type;
                html += '<td style="text-align:center"><span class="l4-type-badge">' + escapeHtml(typeName) + '</span></td>';
            }
            html += '<td>' + escapeHtml(categoryName) + '</td>';
            if (crossFieldMode) {
                html += '<td>' + escapeHtml(item.rule_name || '-') + '</td>';
            }
            html += '<td>' + escapeHtml(item.retailer || '-') + '</td>'
                + '<td>' + escapeHtml(String(item.record_id)) + '</td>'
                + '<td>' + escapeHtml(item.column_name) + '</td>'
                + '<td title="' + escapeHtml(item.old_value || '') + '">' + escapeHtml(item.old_value || '-') + '</td>'
                + '<td title="' + escapeHtml(item.new_value || '') + '">' + escapeHtml(item.new_value || '-') + '</td>'
                + '<td style="text-align:center"><span class="l4-status ' + item.status + '">' + escapeHtml(statusName) + '</span></td>'
                + '<td>' + escapeHtml(item.reason || '-') + '</td>'
                + '<td title="' + escapeHtml(item.memo || '') + '">' + escapeHtml(item.memo || '-') + '</td>'
                + '<td>' + escapeHtml(item.created_id) + '</td>'
                + '<td>' + escapeHtml(item.created_at) + '</td>'
                + '</tr>';
            return html;
        });

        renderPagination(data.page, data.total_pages, data.total);
    }

    function renderPagination(page, totalPages, total) {
        var container = document.getElementById('corrections-pagination');
        if (!container) return;

        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        var html = '<div style="display:flex;justify-content:center;gap:4px;margin-top:16px;">';

        if (page > 1) {
            html += '<button class="app-btn app-btn-sm app-btn-outline" onclick="loadCorrections(1)">&laquo;</button>';
            html += '<button class="app-btn app-btn-sm app-btn-outline" onclick="loadCorrections(' + (page - 1) + ')">&lsaquo;</button>';
        }

        var start = Math.max(1, page - 2);
        var end = Math.min(totalPages, page + 2);

        for (var i = start; i <= end; i++) {
            if (i === page) {
                html += '<button class="app-btn app-btn-sm" style="background:var(--layer-color);color:white;border-color:var(--layer-color);">' + i + '</button>';
            } else {
                html += '<button class="app-btn app-btn-sm app-btn-outline" onclick="loadCorrections(' + i + ')">' + i + '</button>';
            }
        }

        if (page < totalPages) {
            html += '<button class="app-btn app-btn-sm app-btn-outline" onclick="loadCorrections(' + (page + 1) + ')">&rsaquo;</button>';
            html += '<button class="app-btn app-btn-sm app-btn-outline" onclick="loadCorrections(' + totalPages + ')">&raquo;</button>';
        }

        html += '</div>';
        container.innerHTML = html;
    }

    // ============================================================
    // 보고서
    // ============================================================
    window.switchReportTab = function(tab) {
        currentReportTab = tab;
        document.querySelectorAll('.l4-tab').forEach(function(el) {
            el.classList.toggle('active', el.dataset.tab === tab);
        });
        document.getElementById('report-detail').style.display = tab === 'detail' ? '' : 'none';
        document.getElementById('report-summary').style.display = tab === 'summary' ? '' : 'none';
    };

    window.copyReport = function() {
        var el = currentReportTab === 'detail'
            ? document.getElementById('report-detail')
            : document.getElementById('report-summary');
        var text = el ? el.innerText : '';
        if (!text || text.trim() === '날짜를 선택하고 조회 버튼을 클릭하세요.') {
            showToast('복사할 보고서가 없습니다.', 'warning');
            return;
        }
        copyText(text);
        showToast('보고서가 클립보드에 복사되었습니다.', 'success');
    };

    function loadReport() {
        var date = getSelectedDate();
        if (!date) return;

        fetch('/dx/layer4/api/report/?date=' + encodeURIComponent(date))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast(data.error || '조회 실패', 'error');
                    return;
                }
                reportCache = data;
                renderReport(data);
            })
            .catch(function(e) {
                console.error(e);
                showToast('보고서 조회 중 오류가 발생했습니다.', 'error');
            });
    }

    // 보고서 테이블 생성 헬퍼
    // DOM 헬퍼: 텍스트 div 생성
    function createDiv(className, text) {
        var el = document.createElement('div');
        if (className) el.className = className;
        if (text) el.textContent = text;
        return el;
    }

    // CommonTable 기반 보고서 테이블 생성
    function createReportTable(parentEl, columns, data, renderRow) {
        var container = document.createElement('div');
        container.style.margin = '8px 0 16px';
        parentEl.appendChild(container);
        var table = new CommonTable(container, {
            variant: 'detail', columns: columns, resize: false, vlines: true, bordered: true
        });
        table.render();
        table.renderBody(data, renderRow);
        return table;
    }

    // 리테일러 고정 정렬 순서
    var RETAILER_ORDER = [
        'TV Amazon', 'TV Bestbuy', 'TV Walmart',
        'HHP Amazon', 'HHP Bestbuy', 'HHP Walmart'
    ];

    function sortRetailerKeys(keys) {
        return keys.sort(function(a, b) {
            var ia = RETAILER_ORDER.indexOf(a);
            var ib = RETAILER_ORDER.indexOf(b);
            if (ia === -1) ia = 9999;
            if (ib === -1) ib = 9999;
            return ia - ib;
        });
    }

    // 중복/형식/NULL 검증 리테일러별 그룹 렌더링
    // itemField: Item 컬럼에 표시할 필드 ('old_value' 등)
    // itemLabel: 테이블 헤더 라벨 ('item' or 'Item')
    function renderRetailerGroupedSection(parentEl, sectionNo, typeName, tableGroups, typeSummaryData, itemField, itemLabel) {
        if (!tableGroups || Object.keys(tableGroups).length === 0) return;
        var corrected = (typeSummaryData && typeSummaryData.corrected) || 0;
        var normal = (typeSummaryData && typeSummaryData.normal) || 0;
        var total = corrected + normal;

        var section = createDiv('report-section');
        section.appendChild(createDiv('report-section-title',
            '■ ' + sectionNo + '. ' + typeName + ' (' + total + '건)'));

        var TABLE_CATEGORY = { 'tv_retail_com': 'TV', 'hhp_retail_com': 'HHP' };

        // 리테일러별 → (필드+조치)별 그룹핑
        var retailerData = {};
        Object.keys(tableGroups).forEach(function(tn) {
            var category = TABLE_CATEGORY[tn] || tn;
            tableGroups[tn].forEach(function(d) {
                var retailerName = d.retailer ? (category + ' ' + d.retailer) : category;
                if (!retailerData[retailerName]) retailerData[retailerName] = { total: 0, groups: {} };
                retailerData[retailerName].total++;

                // 그룹 결정: 수정 → 필드별 하나로, 확인 → reason별
                var action, groupKey;
                if (d.status === 'normal') {
                    action = d.reason || '확인';
                    groupKey = 'normal|' + (d.column_name || '') + '|' + action;
                } else {
                    action = (d.column_name || '') + ' 수정';
                    groupKey = 'corrected|' + (d.column_name || '');
                }

                if (!retailerData[retailerName].groups[groupKey]) {
                    retailerData[retailerName].groups[groupKey] = { column: d.column_name || '', action: action, items: [], count: 0 };
                }
                retailerData[retailerName].groups[groupKey].count++;
                var val = d[itemField];
                if (val) retailerData[retailerName].groups[groupKey].items.push(val);
            });
        });

        // 리테일러별 서브섹션 렌더링 (고정 순서)
        var retailerIdx = 1;
        sortRetailerKeys(Object.keys(retailerData)).forEach(function(name) {
            var rd = retailerData[name];
            section.appendChild(createDiv('rpt-sub-title',
                '(' + retailerIdx + ') ' + name + '(' + rd.total + '건)'));

            var rows = Object.keys(rd.groups).map(function(gk) {
                var g = rd.groups[gk];
                var uniqueItems = g.items.filter(function(v, i, a) { return a.indexOf(v) === i; });
                return { column: g.column, count: g.count, item: uniqueItems.join(', '), action: g.action };
            });

            createReportTable(section, [
                { key: 'column', label: '필드', width: 140 },
                { key: 'count', label: '건수', width: 60, align: 'center' },
                { key: 'item', label: itemLabel },
                { key: 'action', label: '조치 및 확인사항' }
            ], rows, function(d) {
                return '<tr>'
                    + '<td>' + escapeHtml(d.column) + '</td>'
                    + '<td style="text-align:center">' + d.count + '</td>'
                    + '<td>' + escapeHtml(d.item) + '</td>'
                    + '<td>' + escapeHtml(d.action) + '</td>'
                    + '</tr>';
            });

            retailerIdx++;
        });

        parentEl.appendChild(section);
    }

    // 중복검증 전용: 리테일러별 한 행 (서브섹션 없이 플랫 테이블)
    function renderDuplicateSection(parentEl, sectionNo, typeName, tableGroups, typeSummaryData) {
        if (!tableGroups || Object.keys(tableGroups).length === 0) return;
        var corrected = (typeSummaryData && typeSummaryData.corrected) || 0;
        var normal = (typeSummaryData && typeSummaryData.normal) || 0;
        var total = corrected + normal;

        var section = createDiv('report-section');
        section.appendChild(createDiv('report-section-title',
            '■ ' + sectionNo + '. ' + typeName + ' (' + total + '건)'));

        var TABLE_CATEGORY = { 'tv_retail_com': 'TV', 'hhp_retail_com': 'HHP' };

        // 리테일러별 그룹핑
        var retailerData = {};
        Object.keys(tableGroups).forEach(function(tn) {
            var category = TABLE_CATEGORY[tn] || tn;
            tableGroups[tn].forEach(function(d) {
                var retailerName = d.retailer ? (category + ' ' + d.retailer) : category;
                if (!retailerData[retailerName]) retailerData[retailerName] = { total: 0, items: [], action: '' };
                retailerData[retailerName].total++;
                if (d.item) retailerData[retailerName].items.push(d.item);
                if (!retailerData[retailerName].action) {
                    retailerData[retailerName].action = d.memo || '중복 삭제';
                }
            });
        });

        var rows = sortRetailerKeys(Object.keys(retailerData)).map(function(name) {
            var rd = retailerData[name];
            var uniqueItems = rd.items.filter(function(v, i, a) { return a.indexOf(v) === i; });
            return { retailer: name, count: rd.total, item: uniqueItems.join(', '), action: rd.action };
        });

        createReportTable(section, [
            { key: 'retailer', label: '리테일러', width: 140 },
            { key: 'count', label: '건수', width: 60, align: 'center' },
            { key: 'item', label: 'Item' },
            { key: 'action', label: '조치 및 확인사항' }
        ], rows, function(d) {
            return '<tr>'
                + '<td>' + escapeHtml(d.retailer) + '</td>'
                + '<td style="text-align:center">' + d.count + '</td>'
                + '<td>' + escapeHtml(d.item) + '</td>'
                + '<td>' + escapeHtml(d.action) + '</td>'
                + '</tr>';
        });

        parentEl.appendChild(section);
    }

    // 크로스필드 검증 전용: rule별 그룹 렌더링
    function renderCrossfieldSection(parentEl, sectionNo, typeName, tableGroups, typeSummaryData) {
        if (!tableGroups || Object.keys(tableGroups).length === 0) return;
        var corrected = (typeSummaryData && typeSummaryData.corrected) || 0;
        var normal = (typeSummaryData && typeSummaryData.normal) || 0;
        var total = corrected + normal;

        var section = createDiv('report-section');
        section.appendChild(createDiv('report-section-title',
            '■ ' + sectionNo + '. ' + typeName + ' (' + total + '건)'));

        var TABLE_CATEGORY = { 'tv_retail_com': 'TV', 'hhp_retail_com': 'HHP' };

        // detail_code별 그룹핑 (TV/HHP 동일 규칙 합산)
        var ruleGroups = {};
        Object.keys(tableGroups).forEach(function(tn) {
            var category = TABLE_CATEGORY[tn] || tn;
            tableGroups[tn].forEach(function(d) {
                var ruleKey = d.detail_code || d.rule_name || '규칙 ' + (d.rule_id || 0);
                if (!ruleGroups[ruleKey]) ruleGroups[ruleKey] = { name: d.rule_name || ruleKey, items: [] };
                var item = Object.assign({}, d);
                item._category = category;
                ruleGroups[ruleKey].items.push(item);
            });
        });

        // rule별 서브섹션
        var ruleIdx = 1;
        Object.keys(ruleGroups).forEach(function(ruleKey) {
            var rg = ruleGroups[ruleKey];
            section.appendChild(createDiv('rpt-sub-title',
                '(' + ruleIdx + ') ' + rg.name + ' (' + rg.items.length + '건)'));

            // 리테일러별 → 조치별 그룹핑
            var retailerData = {};
            rg.items.forEach(function(d) {
                var retailerName = d.retailer ? (d._category + ' ' + d.retailer) : d._category;
                if (!retailerData[retailerName]) retailerData[retailerName] = { total: 0, groups: {} };
                retailerData[retailerName].total++;

                var action, groupKey;
                if (d.status === 'normal') {
                    action = d.reason || '확인';
                    groupKey = 'normal|' + action;
                } else {
                    action = '수정';
                    groupKey = 'corrected';
                }

                if (!retailerData[retailerName].groups[groupKey]) {
                    retailerData[retailerName].groups[groupKey] = { action: action, items: [], count: 0 };
                }
                retailerData[retailerName].groups[groupKey].count++;
                if (d.item) retailerData[retailerName].groups[groupKey].items.push(d.item);
            });

            // 리테일러별 행 생성
            var rows = [];
            sortRetailerKeys(Object.keys(retailerData)).forEach(function(name) {
                var rd = retailerData[name];
                Object.keys(rd.groups).forEach(function(gk) {
                    var g = rd.groups[gk];
                    var uniqueItems = g.items.filter(function(v, i, a) { return a.indexOf(v) === i; });
                    rows.push({ retailer: name, count: g.count, item: uniqueItems.join(', '), action: g.action });
                });
            });

            createReportTable(section, [
                { key: 'retailer', label: '리테일러', width: 120 },
                { key: 'count', label: '건수', width: 60, align: 'center' },
                { key: 'item', label: 'Item' },
                { key: 'action', label: '조치 및 확인사항' }
            ], rows, function(d) {
                return '<tr>'
                    + '<td>' + escapeHtml(d.retailer) + '</td>'
                    + '<td style="text-align:center">' + d.count + '</td>'
                    + '<td>' + escapeHtml(d.item) + '</td>'
                    + '<td>' + escapeHtml(d.action) + '</td>'
                    + '</tr>';
            });

            ruleIdx++;
        });

        parentEl.appendChild(section);
    }

    // correction_type별 상세 섹션 렌더링 (DOM 기반)
    function renderGroupedSection(parentEl, sectionNo, typeName, tableGroups, typeSummaryData) {
        if (!tableGroups || Object.keys(tableGroups).length === 0) return;
        var corrected = (typeSummaryData && typeSummaryData.corrected) || 0;
        var normal = (typeSummaryData && typeSummaryData.normal) || 0;

        var section = createDiv('report-section');
        section.appendChild(createDiv('report-section-title',
            '■ ' + sectionNo + '. ' + typeName + ' (수정 ' + corrected + '건, 확인 ' + normal + '건)'));

        var detailCols = [
            { key: 'no', label: 'No', width: 40, align: 'center' },
            { key: 'column_name', label: '컬럼' },
            { key: 'old_value', label: '변경전' },
            { key: 'new_value', label: '변경후' },
            { key: 'status', label: '상태', width: 70, align: 'center' },
            { key: 'reason', label: '사유' },
            { key: 'memo', label: '메모' }
        ];

        Object.keys(tableGroups).forEach(function(tn) {
            var items = tableGroups[tn];
            var tCorrected = 0, tNormal = 0;
            items.forEach(function(d) {
                if (d.status === 'corrected') tCorrected++;
                else tNormal++;
            });
            section.appendChild(createDiv('rpt-sub-title',
                '▸ ' + tn + ' — 수정 ' + tCorrected + '건, 확인 ' + tNormal + '건'));

            createReportTable(section, detailCols, items, function(d, idx) {
                var statusText = d.status === 'corrected' ? '수정' : '확인';
                return '<tr>'
                    + '<td style="text-align:center">' + (idx + 1) + '</td>'
                    + '<td>' + escapeHtml(d.column_name) + '</td>'
                    + '<td>' + escapeHtml(d.old_value || '-') + '</td>'
                    + '<td>' + escapeHtml(d.new_value || '-') + '</td>'
                    + '<td style="text-align:center">' + statusText + '</td>'
                    + '<td>' + escapeHtml(d.reason || '') + '</td>'
                    + '<td>' + escapeHtml(d.memo || '') + '</td>'
                    + '</tr>';
            });
        });

        parentEl.appendChild(section);
    }

    function renderReport(data) {
        var detailEl = document.getElementById('report-detail');
        var summaryEl = document.getElementById('report-summary');

        var date = data.date || '';
        var collectionStatus = data.collection_status || [];
        var collectionIssues = data.collection_issues || [];
        var typeSummary = data.type_summary || {};
        var groupedDetails = data.grouped_details || {};

        // 전체 통계 계산
        var totalCorrected = 0, totalNormal = 0;
        Object.keys(typeSummary).forEach(function(ct) {
            totalCorrected += (typeSummary[ct].corrected || 0);
            totalNormal += (typeSummary[ct].normal || 0);
        });

        var hasCollection = collectionStatus.length > 0;
        var hasIssues = collectionIssues.length > 0;
        var hasCorrections = totalCorrected > 0 || totalNormal > 0;

        if (!hasCollection && !hasIssues && !hasCorrections) {
            detailEl.innerHTML = '<div class="l4-empty-state"><p>해당 날짜에 검수 기록이 없습니다.</p></div>';
            summaryEl.innerHTML = '<div class="l4-empty-state"><p>해당 날짜에 검수 기록이 없습니다.</p></div>';
            return;
        }

        // === 상세 보고서 (DOM 기반) ===
        detailEl.innerHTML = '';
        detailEl.appendChild(createDiv('report-title', '[DX] ' + date + ' 검수 보고서'));

        // ━━━ 요약 테이블 ━━━
        var summarySection = createDiv('report-section');
        summarySection.appendChild(createDiv('report-section-title', '■ 요약'));

        var issueCount = collectionIssues.length;
        var TYPES_ORDER = ['null_check', 'duplicate_check', 'format_check', 'cross_field'];
        // 수집현황 비고: 섹션별 메모 조합
        var collMemos = [];
        collectionStatus.forEach(function(cs) {
            if (cs.memo) {
                var name = CHECK_SECTION_NAMES[cs.section] || cs.section;
                collMemos.push(name + ':\n' + cs.memo);
            }
        });
        var collRemarks = collMemos.length > 0 ? collMemos.join('\n') : '특이사항 없음';
        var summaryData = [{ category: '수집현황', count: issueCount + '건', remarks: collRemarks }];
        var TABLE_SECTION = {
            'tv_retail_com': 'Retail', 'hhp_retail_com': 'Retail',
            'youtube_collection_logs': 'YouTube', 'youtube_videos': 'YouTube', 'youtube_comments': 'YouTube',
            'market_trend': 'Market Trend', 'market_comp_product': 'Market', 'market_comp_event': 'Market',
            'openai_forecast_results': '수요증감율'
        };
        TYPES_ORDER.forEach(function(ct) {
            var c = typeSummary[ct] || {};
            var total = (c.corrected || 0) + (c.normal || 0);
            var remarks = '';
            if (total === 0) {
                remarks = '특이사항 없음';
            } else {
                // 섹션별 수정/확인 건수 자동 생성
                var tableGroups = groupedDetails[ct] || {};
                var sectionStats = {};
                Object.keys(tableGroups).forEach(function(tn) {
                    var sName = TABLE_SECTION[tn] || tn;
                    if (!sectionStats[sName]) sectionStats[sName] = { corrected: 0, normal: 0 };
                    tableGroups[tn].forEach(function(d) {
                        if (d.status === 'corrected') sectionStats[sName].corrected++;
                        else if (d.status === 'normal') sectionStats[sName].normal++;
                    });
                });
                var parts = [];
                Object.keys(sectionStats).forEach(function(sName) {
                    var s = sectionStats[sName];
                    var sub = [];
                    if (s.corrected > 0) sub.push('수정 ' + s.corrected + '건');
                    if (s.normal > 0) sub.push('확인 ' + s.normal + '건');
                    parts.push(sName + ' ' + sub.join(', '));
                });
                remarks = parts.join(' / ');
            }
            summaryData.push({ category: TYPE_NAMES[ct], count: total + '건', remarks: remarks });
        });

        createReportTable(summarySection, [
            { key: 'category', label: '구분', width: 150 },
            { key: 'count', label: '이슈건수', width: 80, align: 'center' },
            { key: 'remarks', label: '비고' }
        ], summaryData, function(item) {
            return '<tr>'
                + '<td>' + escapeHtml(item.category) + '</td>'
                + '<td style="text-align:center">' + escapeHtml(item.count) + '</td>'
                + '<td style="white-space:pre-line">' + escapeHtml(item.remarks) + '</td>'
                + '</tr>';
        });
        detailEl.appendChild(summarySection);

        // ━━━ 1. 수집현황 ━━━
        var collSection = createDiv('report-section');
        collSection.appendChild(createDiv('report-section-title', '■ 1. 수집현황'));

        if (hasCollection) {
            var sectionNames = collectionStatus.map(function(cs) {
                return CHECK_SECTION_NAMES[cs.section] || cs.section;
            });
            collSection.appendChild(createDiv('report-item', '수집 항목: ' + sectionNames.join(', ')));
        } else {
            collSection.appendChild(createDiv('report-item', '- 수집현황 기록 없음'));
        }

        // 수집 이슈 내역
        if (hasIssues) {
            collSection.appendChild(createDiv('rpt-sub-title', '▸ 수집 이슈'));
            collectionIssues.forEach(function(issue, idx) {
                var sectionName = CHECK_SECTION_NAMES[issue.section] || issue.section;
                var statusTag = issue.resolution_status === 'resolved' ? '[확인] ' : '';
                collSection.appendChild(createDiv('report-item', '(' + (idx + 1) + ') ' + statusTag + '[' + sectionName + '] ' + issue.title));
                var fields = [
                    { label: '일시', value: issue.issue_date },
                    { label: '현상', value: issue.symptom },
                    { label: '원인', value: issue.cause },
                    { label: '조치', value: issue.action }
                ];
                if (issue.resolution_status === 'resolved' && issue.resolution_memo) {
                    fields.push({ label: '처리사유', value: issue.resolution_memo });
                }
                fields.forEach(function(f) {
                    if (f.value) {
                        var item = createDiv('report-item', f.label + ': ' + f.value);
                        item.style.paddingLeft = '32px';
                        collSection.appendChild(item);
                    }
                });
            });
        }

        // 수요증감율 부족 키워드
        var missingKeywords = data.missing_keywords || [];
        if (missingKeywords.length > 0) {
            collSection.appendChild(createDiv('rpt-sub-title', '▸ 수요증감율 부족 키워드'));
            // 이벤트별 그룹핑
            var kwByEvent = {};
            missingKeywords.forEach(function(kw) {
                var key = kw.event_name;
                if (!kwByEvent[key]) kwByEvent[key] = { category: kw.category, event_date: kw.event_date, products: [] };
                kwByEvent[key].products.push(kw.product_name);
            });
            var kwData = Object.keys(kwByEvent).map(function(eventName) {
                var g = kwByEvent[eventName];
                return { event_name: eventName, category: g.category, products: g.products.join(', '), count: g.products.length };
            });
            createReportTable(collSection, [
                { key: 'event_name', label: '이벤트' },
                { key: 'category', label: '카테고리', align: 'center' },
                { key: 'products', label: '부족 키워드' },
                { key: 'count', label: '건수', align: 'center' }
            ], kwData, function(item) {
                return '<tr>'
                    + '<td>' + escapeHtml(item.event_name) + '</td>'
                    + '<td style="text-align:center">' + escapeHtml(item.category) + '</td>'
                    + '<td>' + escapeHtml(item.products) + '</td>'
                    + '<td style="text-align:center">' + item.count + '</td>'
                    + '</tr>';
            });
        }
        detailEl.appendChild(collSection);

        // ━━━ 2~5. 검증 상세 (NULL / 중복 / 형식 / 크로스필드) ━━━
        var sectionNo = 2;
        ['null_check', 'duplicate_check', 'format_check', 'cross_field'].forEach(function(ct) {
            var tableGroups = groupedDetails[ct];
            var hasData = tableGroups && Object.keys(tableGroups).length > 0;
            if (hasData) {
                if (ct === 'duplicate_check') {
                    renderDuplicateSection(detailEl, sectionNo, TYPE_NAMES[ct], tableGroups, typeSummary[ct]);
                } else if (ct === 'cross_field') {
                    renderCrossfieldSection(detailEl, sectionNo, TYPE_NAMES[ct], tableGroups, typeSummary[ct]);
                } else {
                    renderRetailerGroupedSection(detailEl, sectionNo, TYPE_NAMES[ct], tableGroups, typeSummary[ct], 'item', 'Item');
                }
            } else {
                var emptySection = createDiv('report-section');
                var c = typeSummary[ct] || {};
                var total = (c.corrected || 0) + (c.normal || 0);
                emptySection.appendChild(createDiv('report-section-title',
                    '■ ' + sectionNo + '. ' + TYPE_NAMES[ct] + ' (' + total + '건)'));
                emptySection.appendChild(createDiv('report-item', '- 특이사항 없음'));
                detailEl.appendChild(emptySection);
            }
            sectionNo++;
        });

        // === 한줄 요약 ===
        var sHtml = '<div class="report-title">[DX] ' + date + ' 검수 요약</div>';

        // 수집현황 한줄
        if (hasCollection || hasIssues) {
            var summaryParts = [];
            if (hasCollection) {
                var allOk = collectionStatus.every(function(cs) { return cs.status === 'OK'; });
                if (allOk) {
                    summaryParts.push('전체 정상 (' + collectionStatus.length + '개 섹션)');
                } else {
                    var statusIssues = collectionStatus.filter(function(cs) { return cs.status !== 'OK'; });
                    var issueParts = statusIssues.map(function(cs) {
                        var name = CHECK_SECTION_NAMES[cs.section] || cs.section;
                        return name + ' ' + cs.rate.toFixed(1) + '%';
                    });
                    summaryParts.push('이슈: ' + issueParts.join(', '));
                }
            }
            if (hasIssues) {
                summaryParts.push('수집 이슈 ' + collectionIssues.length + '건');
            }
            collectionStatus.forEach(function(cs) {
                if (cs.memo) {
                    var name = CHECK_SECTION_NAMES[cs.section] || cs.section;
                    summaryParts.push(name + ': ' + cs.memo);
                }
            });
            sHtml += '<div class="report-item">[수집현황] → ' + summaryParts.join(' / ') + '</div>';
        }

        // 유형별 한줄씩
        ['null_check', 'duplicate_check', 'format_check', 'cross_field'].forEach(function(ct) {
            var c = typeSummary[ct];
            if (!c) return;
            var corrected = c.corrected || 0;
            var normal = c.normal || 0;
            if (corrected === 0 && normal === 0) return;

            var parts = [];
            if (corrected > 0) parts.push('수정 ' + corrected + '건');
            if (normal > 0) parts.push('확인 ' + normal + '건');
            sHtml += '<div class="report-item">[' + TYPE_NAMES[ct] + '] → ' + parts.join(', ') + '</div>';
        });

        summaryEl.innerHTML = sHtml;
    }

    // ============================================================
    // 유틸리티
    // ============================================================
    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function formatNumber(n) {
        return (n || 0).toLocaleString();
    }

    // ============================================================
    // 초기화
    // ============================================================
    document.addEventListener('DOMContentLoaded', function() {
        if (section === 'corrections') {
            initCorrectionsFilterBar();
        }
        initFilterBar();
        handleSearch();
    });

})();
