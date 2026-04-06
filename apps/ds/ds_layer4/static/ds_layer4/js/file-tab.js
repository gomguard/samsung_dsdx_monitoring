/* ================================================================
 *  DS Layer4 – file-tab.js
 *  파일 탭: 리테일러별 7일평균 + 파일용량(오늘) + 파일명 + 파일메모
 *  7일 평균 클릭 → 모달로 7일 히스토리 표시
 * ================================================================ */

const FILE_ABNORMAL_THRESHOLD = 200;
let fileTabHistoryData = null;
let fileTabReportData = null;

async function loadFileTab() {
    const date = document.getElementById('targetDate').value;
    const content = document.getElementById('fileTabContent');
    content.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';

    try {
        const [historyRes, reportRes] = await Promise.all([
            fetch(`/ds/layer4/api/file-size-history/?end_date=${date}&days=7`).then(r => r.json()),
            fetch(`/ds/layer4/api/report-list/?date=${date}&view=status`).then(r => r.json())
        ]);

        fileTabHistoryData = historyRes;
        fileTabReportData = reportRes;
        renderFileTab();
    } catch (error) {
        console.error('File tab load error:', error);
        content.innerHTML = '<div class="empty-state"><h3>오류 발생</h3><p>' + esc(error.message) + '</p></div>';
    }
}

function renderFileTab() {
    const content = document.getElementById('fileTabContent');
    const historyData = fileTabHistoryData;
    const reportData = fileTabReportData;
    if (!historyData || !reportData) return;

    const dailyReports = reportData.daily_reports || [];
    const isClosed = reportData.is_closed || false;

    const historyMap = {};
    if (historyData.retailers) {
        historyData.retailers.forEach(r => {
            historyMap[r.retailer] = { avg: r.avg, sizes: r.sizes };
        });
    }

    let html = '<table class="report-table"><thead><tr>';
    if (!isClosed) {
        html += '<th class="text-center" style="width: 40px;"><input type="checkbox" id="fileSelectAll" class="memo-checkbox" onchange="toggleFileSelectAll()"></th>';
    }
    html += '<th>리테일러</th>';
    html += '<th class="text-center">7일 평균</th>';
    html += '<th class="text-center">파일용량</th>';
    html += '<th>파일명</th>';
    html += '<th style="min-width: 350px;">파일메모</th>';
    html += '</tr></thead><tbody>';

    dailyReports.forEach(report => {
        const history = historyMap[report.retailer] || { avg: 0, sizes: [] };
        const avg = history.avg || 0;
        const todaySize = report.file_size || 0;
        const diff = todaySize - avg;
        const isAbnormal = avg > 0 && todaySize > 0 && Math.abs(diff) > FILE_ABNORMAL_THRESHOLD;
        const escFileMemo = (report.file_memo || '').replace(/"/g, '&quot;');

        html += '<tr>';
        if (!isClosed) {
            html += '<td class="text-center"><input type="checkbox" id="fileCheck_' + report.id + '" class="memo-checkbox file-checkbox" onchange="toggleFileInput(' + report.id + ')"></td>';
        }
        html += '<td><strong>' + esc(report.retailer) + '</strong></td>';

        // 7일 평균 (클릭 시 모달)
        html += '<td class="text-center"><a href="javascript:void(0)" onclick="openFileHistoryModal(\'' + esc(report.retailer) + '\')" style="font-weight:600;color:var(--text-primary);text-decoration:none;cursor:pointer;" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">' + (avg > 0 ? avg.toLocaleString() : '-') + '</a></td>';

        // 파일용량 (오늘)
        var sizeStyle = 'text-align:center;font-weight:600;';
        if (isAbnormal) {
            sizeStyle += 'color:#dc2626;';
        }
        var sizeText = todaySize > 0 ? todaySize.toLocaleString() : '-';
        if (isAbnormal) {
            var sign = diff > 0 ? '+' : '';
            sizeText += '<br><span style="font-size:11px;font-weight:400;">(' + sign + diff.toLocaleString() + ')</span>';
        }
        html += '<td style="' + sizeStyle + '">' + sizeText + '</td>';

        // 파일명
        html += '<td style="font-size:13px;">' + (report.file_name || '-') + '</td>';

        // 파일메모
        html += '<td>';
        html += '<textarea id="fileTabMemo_' + report.id + '" class="inline-input" placeholder="파일메모 입력" disabled data-original="' + escFileMemo + '" onchange="saveFileTabMemo(' + report.id + ')" rows="2" style="resize:vertical;min-height:36px;">' + (report.file_memo || '').replace(/</g, '&lt;') + '</textarea>';
        html += '</td>';

        html += '</tr>';
    });

    if (dailyReports.length === 0) {
        var colCount = (isClosed ? 0 : 1) + 5;
        html += '<tr><td colspan="' + colCount + '" class="text-center text-muted">저장된 데이터가 없습니다.</td></tr>';
    }

    html += '</tbody></table>';
    content.innerHTML = html;
}

// 7일 히스토리 모달
function openFileHistoryModal(retailer) {
    const historyData = fileTabHistoryData;
    if (!historyData) return;

    const dates = historyData.dates || [];
    const dateHeaders = [...dates].reverse().map(d => {
        const parts = d.split('-');
        return parts[1] + '/' + parts[2];
    });

    const retailerData = (historyData.retailers || []).find(r => r.retailer === retailer);
    if (!retailerData) return;

    const avg = retailerData.avg || 0;
    const sizes = [...retailerData.sizes].reverse();

    var html = '<table style="border-collapse:collapse;width:100%;margin-top:8px;">';
    html += '<thead><tr>';
    html += '<th style="padding:10px 16px;font-size:13px;color:#6b7280;text-align:center;border-bottom:2px solid #e5e7eb;font-weight:600;">7일 평균</th>';
    dateHeaders.forEach(function(d, i) {
        var thStyle = 'padding:10px 16px;font-size:13px;text-align:center;border-bottom:2px solid #e5e7eb;';
        if (i === 0) thStyle += 'background:#fffde7;font-weight:600;color:#1a365d;';
        else thStyle += 'color:#6b7280;';
        html += '<th style="' + thStyle + '">' + d + '</th>';
    });
    html += '</tr></thead><tbody><tr>';

    // 평균
    html += '<td style="padding:12px 16px;text-align:center;font-weight:700;font-size:14px;border-bottom:1px solid #e5e7eb;">' + (avg > 0 ? avg.toLocaleString() : '-') + '</td>';

    // 날짜별
    sizes.forEach(function(s, i) {
        var tdStyle = 'padding:12px 16px;text-align:center;font-size:14px;border-bottom:1px solid #e5e7eb;';
        var isAbnormal = avg > 0 && s > 0 && Math.abs(s - avg) > FILE_ABNORMAL_THRESHOLD;
        if (i === 0) {
            if (isAbnormal) {
                tdStyle += 'background:#fee2e2;color:#dc2626;font-weight:600;';
            } else {
                tdStyle += 'background:#fffde7;font-weight:600;';
            }
        }
        html += '<td style="' + tdStyle + '">' + (s > 0 ? s.toLocaleString() : '-') + '</td>';
    });
    html += '</tr></tbody></table>';

    AppModal.setTitle('fileHistory', retailer + ' — 7일 파일용량 히스토리');
    AppModal.setBody('fileHistory', html);
    AppModal.open('fileHistory');
}

// 파일탭 메모 저장
async function saveFileTabMemo(dailyId) {
    const input = document.getElementById('fileTabMemo_' + dailyId);
    if (!input) return;
    const fileMemo = input.value;
    const original = input.dataset.original || '';
    if (fileMemo === original) return;

    try {
        const res = await fetch('/ds/layer4/api/daily-update/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ daily_id: dailyId, file_memo: fileMemo, user_id: currentUserId })
        });
        const data = await res.json();
        if (data.success) {
            input.dataset.original = fileMemo;
            showToast('파일메모 저장 완료', 'success');
        } else {
            showToast(data.error || '저장 실패', 'error');
        }
    } catch (e) {
        showToast('저장 중 오류 발생', 'error');
    }
}

// 파일탭 전체 선택 토글
function toggleFileSelectAll() {
    const selectAll = document.getElementById('fileSelectAll');
    document.querySelectorAll('.file-checkbox').forEach(cb => {
        cb.checked = selectAll.checked;
        const id = cb.id.replace('fileCheck_', '');
        const input = document.getElementById('fileTabMemo_' + id);
        if (input) {
            input.disabled = !selectAll.checked;
            if (!selectAll.checked) {
                input.value = input.dataset.original || '';
            }
        }
    });
    updateFileSaveButton();
}

// 파일탭 개별 체크박스 토글
function toggleFileInput(dailyId) {
    const cb = document.getElementById('fileCheck_' + dailyId);
    const input = document.getElementById('fileTabMemo_' + dailyId);
    if (cb && input) {
        input.disabled = !cb.checked;
        if (cb.checked) {
            input.focus();
        } else {
            input.value = input.dataset.original || '';
        }
    }
    const all = document.querySelectorAll('.file-checkbox');
    const checked = document.querySelectorAll('.file-checkbox:checked');
    const selectAll = document.getElementById('fileSelectAll');
    if (selectAll) selectAll.checked = all.length === checked.length;
    updateFileSaveButton();
}

// 저장 버튼 상태 업데이트
function updateFileSaveButton() {
    const checked = document.querySelectorAll('.file-checkbox:checked');
    const btn = document.getElementById('fileSaveBtn');
    if (btn) btn.disabled = checked.length === 0;
}

// 체크된 파일메모 일괄 저장
async function saveCheckedFileMemos() {
    const checked = document.querySelectorAll('.file-checkbox:checked');
    if (checked.length === 0) return;

    const memos = [];
    checked.forEach(cb => {
        const id = cb.id.replace('fileCheck_', '');
        const input = document.getElementById('fileTabMemo_' + id);
        if (input) {
            memos.push({ daily_id: parseInt(id), file_memo: input.value });
        }
    });

    try {
        const res = await fetch('/ds/layer4/api/daily-update/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ memos: memos, user_id: currentUserId })
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || '파일메모 저장 완료', 'success');
            loadFileTab();
        } else {
            showToast(data.error || '저장 실패', 'error');
        }
    } catch (e) {
        showToast('저장 중 오류 발생', 'error');
    }
}
