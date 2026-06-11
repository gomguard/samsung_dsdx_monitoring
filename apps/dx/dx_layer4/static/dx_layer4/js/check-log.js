/**
 * Layer 4 마감기록
 */

(function() {
    'use strict';

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
                    var name = L4.CHECK_SECTION_NAMES[log.section] || log.section;
                    var statusClass = log.status === 'CRITICAL' ? 'badge-critical' : (log.status === 'WARNING' ? 'badge-warning' : 'badge-ok');
                    var stepBadge = '';
                    if (log.confirm_step === 2) stepBadge = ' <span class="badge badge-ok" style="font-size:11px;">완료</span>';
                    else if (log.confirm_step === 1) stepBadge = ' <span class="badge badge-warning" style="font-size:11px;">1차</span>';
                    var memoHtml = log.memo
                        ? '<span class="memo-cell memo-text" onclick="toggleMemoEditor(' + log.id + ', this)">' + L4.escapeHtml(log.memo) + '</span>'
                        : '<span class="memo-cell memo-empty" onclick="toggleMemoEditor(' + log.id + ', this)">+ 메모 추가</span>';
                    var detailUrl = '/dx/layer4/check-log/detail/?date=' + dateStr + '&section=' + log.section;
                    rows += '<tr>'
                        + '<td><a href="' + detailUrl + '" style="color:var(--text-primary);text-decoration:none;font-weight:500;">' + L4.escapeHtml(name) + ' &rsaquo;</a>' + stepBadge + '</td>'
                        + '<td><span class="badge ' + statusClass + '">' + L4.escapeHtml(log.status) + '</span></td>'
                        + '<td>' + L4.escapeHtml(log.created_id) + '</td>'
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
                    var dname = L4.CHECK_SECTION_NAMES[dl.section] || dl.section;
                    var dstatusClass = dl.status === 'CRITICAL' ? 'badge-critical' : (dl.status === 'WARNING' ? 'badge-warning' : 'badge-ok');
                    drows += '<tr>'
                        + '<td>' + L4.escapeHtml(dname) + '</td>'
                        + '<td><span class="badge ' + dstatusClass + '">' + L4.escapeHtml(dl.status) + '</span></td>'
                        + '<td>' + L4.escapeHtml(dl.created_id) + '</td>'
                        + '<td><span class="time-text">' + fmtTime(dl.created_at) + '</span></td>'
                        + '<td>' + L4.escapeHtml(dl.updated_id || dl.created_id) + '</td>'
                        + '<td><span class="time-text">' + fmtTime(dl.updated_at) + '</span></td>'
                        + '<td>' + (dl.delete_memo ? '<span class="memo-text" title="' + L4.escapeHtml(dl.delete_memo) + '">' + L4.escapeHtml(dl.delete_memo) + '</span>' : '<span style="color:var(--text-secondary);opacity:0.4;">-</span>') + '</td>'
                        + '</tr>';
                });
                tbodyDeleted.innerHTML = drows;
            }
        }
    }

    window.toggleMemoEditor = function(logId, el) {
        var row = el.closest('tr');
        var existing = row.nextElementSibling;
        if (existing && existing.classList.contains('memo-editor-row')) {
            existing.remove();
            return;
        }
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

    // 핸들러 등록
    L4._sectionHandler['check_log'] = loadCheckLog;

})();
