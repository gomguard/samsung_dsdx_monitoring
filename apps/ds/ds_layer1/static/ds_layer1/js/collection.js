/**
 * DS Layer 1 — 수집현황
 * 공유 상태 + 데이터 로딩 + 테이블 렌더링 + 재실행
 */

// ── 공유 상태 ──
let currentMainTab = 'collection';
let statsData = null;
let fileserverData = null;
let currentBatchView = 'final';
var layer2Data = null;
var reportStatusData = null;

// ── 날짜 이동 ──
function setPrevDay() {
    const dateInput = document.getElementById('targetDate');
    const current = new Date(dateInput.value);
    current.setDate(current.getDate() - 1);
    dateInput.value = formatLocalDate(current);
    loadData();
}

function setNextDay() {
    const dateInput = document.getElementById('targetDate');
    const [year, month, day] = dateInput.value.split('-').map(Number);
    const nextDate = new Date(year, month - 1, day + 1);
    const nextStr = formatLocalDate(nextDate);
    const todayStr = formatLocalDate(new Date());

    if (nextStr > todayStr) {
        showToast('오늘 이후 날짜로는 조회할 수 없습니다.', 'warning');
        return;
    }

    dateInput.value = nextStr;
    loadData();
}

// ── 데이터 로딩 ──
async function loadData() {
    let date = document.getElementById('targetDate').value;
    if (!validateQueryDate(date, 'targetDate')) {
        date = document.getElementById('targetDate').value;
    }
    setPersistedDate(date);

    document.getElementById('allLoading').classList.remove('hidden');
    document.getElementById('allContent').innerHTML = '';

    try {
        await fetch('/ds/layer1/api/batch/init/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ date: date })
        }).catch(() => {});

        const [statsResponse, layer2Response, statusResponse] = await Promise.all([
            fetch(`/ds/layer1/api/stats/?date=${date}&batch_view=${currentBatchView}`),
            fetch(`/ds/layer2/api/stats/?date=${date}&batch_view=${currentBatchView}`),
            fetch(`/ds/layer2/api/status/?date=${date}`)
        ]);

        statsData = await statsResponse.json();
        layer2Data = await layer2Response.json();
        reportStatusData = await statusResponse.json();

        updateSummary(statsData);
        renderAllView(statsData);

    } catch (error) {
        console.error('Error loading data:', error);
        document.getElementById('allContent').innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }

    document.getElementById('allLoading').classList.add('hidden');
}

// ── 유틸 ──
function getLayer2Status(retailerName) {
    if (!layer2Data || !layer2Data.results) return null;
    const found = layer2Data.results.find(r => r.retailer === retailerName);
    if (!found) return null;
    if (found.status === 'success') return null;
    return found;
}

function getStatusClass(rateOrStatus) {
    if (typeof rateOrStatus === 'string') return rateOrStatus;
    if (rateOrStatus > 100) return 'over100';
    if (rateOrStatus >= 100) return 'success';
    return 'danger';
}

function getStatusLabel(status) {
    const labels = {
        'success': '정상',
        'warning': '경고',
        'danger': '이상',
        'pending': '대기중',
        'collecting': '수집중',
        'error': '오류',
        'over100': '재실행'
    };
    return labels[status] || '확인필요';
}

// ── 요약 카드 ──
function updateSummary(data) {
    if (data.summary) {
        document.getElementById('totalTables').textContent = data.summary.total_tables || 0;
        document.getElementById('totalExpected').textContent = (data.summary.total_expected || 0).toLocaleString();
        document.getElementById('totalActual').textContent = (data.summary.total_actual || 0).toLocaleString();

        const rate = data.summary.total_completion_rate || 0;
        const rateEl = document.getElementById('totalRate');
        rateEl.textContent = rate + '%';
        rateEl.className = 'summary-value ' + getStatusClass(rate);
    }
}

// ── 수집현황 테이블 ──
function renderAllView(data) {
    const container = document.getElementById('allContent');

    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="loading">데이터가 없습니다.</div>';
        return;
    }

    const serverDate = data.timestamp ? data.timestamp.split('T')[0] : '';
    const serverToday = new Date(serverDate);
    const serverYesterday = new Date(serverToday);
    serverYesterday.setDate(serverYesterday.getDate() - 1);
    const queryDate = data.date;
    const todayStr = serverToday.toISOString().split('T')[0];
    const yesterdayStr = serverYesterday.toISOString().split('T')[0];
    const isToday = queryDate === todayStr;
    const isYesterday = queryDate === yesterdayStr;
    const isClosed = reportStatusData && reportStatusData.is_closed;
    const showRerun = isToday || (isYesterday && !isClosed);

    let html = `
        <table class="retailer-table">
            <thead>
                <tr>
                    <th>No</th>
                    <th>리테일러</th>
                    <th>지역</th>
                    <th>국가</th>
                    <th>수집시간(KST)</th>
                    <th>예상</th>
                    <th>수집</th>
                    <th>완료율</th>
                    <th>상태</th>
                    ${showRerun ? '<th class="col-rerun">재실행</th>' : ''}
                </tr>
            </thead>
            <tbody>
    `;

    for (const item of data.results) {
        const statusClass = item.completion_rate > 100 ? 'over100' : item.status;
        const l2Status = getLayer2Status(item.retailer);
        const showL2Badge = l2Status && statusClass !== 'collecting' && statusClass !== 'pending';
        const l2BadgeClass = showL2Badge ? (l2Status.null_union > 0 ? 'danger' : 'warning') : '';
        const l2Badge = showL2Badge ? `<span class="layer2-badge ${l2BadgeClass}" title="L2 비정상: ${l2Status.error_count}건">L2 확인</span>` : '';

        const expandBtn = (item.has_multi_batch && currentBatchView === 'all')
            ? `<button class="expand-btn" onclick="event.stopPropagation(); toggleBatchRows('${escJs(item.retailer)}')" id="expandBtn_${esc(item.retailer)}">▶ 배치별</button>`
            : '';

        const finalStartTime = item.final_start_time ? `'${item.final_start_time}'` : 'null';
        const finalEndTime = item.final_end_time ? `'${item.final_end_time}'` : 'null';

        html += `
            <tr onclick="openDetail('${escJs(item.table_name)}', '${escJs(item.retailer)}', '${escJs(item.country)}', ${finalStartTime}, ${finalEndTime})" title="클릭하여 상세 보기" data-retailer="${esc(item.retailer)}">
                <td>${item.no}</td>
                <td><span class="retailer-name">${item.retailer}</span>${l2Badge} ${expandBtn}</td>
                <td>${item.region}</td>
                <td><span class="country-badge">${item.country}</span></td>
                <td>${item.korea_time}</td>
                <td>${item.expected.toLocaleString()}</td>
                <td>${item.actual.toLocaleString()}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div class="completion-bar">
                            <div class="completion-fill ${statusClass}" style="width: ${Math.min(item.completion_rate, 100)}%"></div>
                        </div>
                        <span>${item.completion_rate}%</span>
                    </div>
                </td>
                <td>
                    <span class="status-badge ${statusClass}">
                        <span class="status-dot"></span>
                        ${getStatusLabel(statusClass)}
                    </span>
                </td>
                ${showRerun ? (() => {
                    const isSaved = reportStatusData && reportStatusData.saved_retailers && reportStatusData.saved_retailers[item.retailer];
                    return `<td class="col-rerun" onclick="event.stopPropagation()">
                    ${item.has_instance && statusClass !== 'pending' && !isSaved
                        ? `<button class="btn-rerun" data-retailer="${esc(item.retailer)}" onclick="rerunCrawler('${escJs(item.retailer)}')" title="${esc(item.retailer)} 크롤러 재실행">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="23 4 23 10 17 10"/>
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                            </svg>
                        </button>`
                        : `<button class="btn-rerun" disabled title="${isSaved ? '수집 완료' : statusClass === 'pending' ? '수집 대기중' : 'instance_id 없음'}" style="opacity:0.3; cursor:not-allowed;">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="23 4 23 10 17 10"/>
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                            </svg>
                        </button>`
                    }
                </td>`;
                })() : ''}
            </tr>
        `;

        if (item.has_multi_batch && item.batches && currentBatchView === 'all') {
            for (const batch of item.batches) {
                const batchStatusClass = batch.completion_rate >= 100 ? 'success' : 'danger';
                const l2ErrorCount = batch.l2_error_count || 0;
                const l2Badge = l2ErrorCount > 0
                    ? `<span class="batch-error-badge has-error">L2: ${l2ErrorCount}건</span>`
                    : '';
                const endTimeParam = batch.end_time === '다음날' ? 'null' : `'${batch.end_time}'`;
                html += `
                    <tr class="batch-sub-row hidden" data-parent="${esc(item.retailer)}"
                        onclick="openDetail('${escJs(item.table_name)}', '${escJs(item.retailer)}', '${escJs(item.country)}', '${escJs(batch.start_time)}', ${endTimeParam})"
                        title="클릭하여 배치 상세 보기">
                        <td></td>
                        <td colspan="3">
                            <span class="batch-indicator">
                                <span class="batch-time">${batch.start_time} ~ ${batch.end_time}</span>
                                <span class="batch-memo">${batch.memo || ''}</span>
                                ${l2Badge}
                            </span>
                        </td>
                        <td></td>
                        <td>${item.expected.toLocaleString()}</td>
                        <td>${batch.actual.toLocaleString()}</td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div class="completion-bar">
                                    <div class="completion-fill ${batchStatusClass}" style="width: ${Math.min(batch.completion_rate, 100)}%"></div>
                                </div>
                                <span>${batch.completion_rate}%</span>
                            </div>
                        </td>
                        <td>
                            <span class="status-badge ${batchStatusClass}">
                                <span class="status-dot"></span>
                                ${getStatusLabel(batchStatusClass)}
                            </span>
                        </td>
                        ${showRerun ? '<td></td>' : ''}
                    </tr>
                `;
            }
        }
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

function toggleBatchRows(retailer) {
    const subRows = document.querySelectorAll(`.batch-sub-row[data-parent="${retailer}"]`);
    const btn = document.getElementById(`expandBtn_${retailer}`);

    if (subRows.length === 0) return;

    const isExpanded = !subRows[0].classList.contains('hidden');

    subRows.forEach(row => {
        if (isExpanded) {
            row.classList.add('hidden');
        } else {
            row.classList.remove('hidden');
        }
    });

    if (btn) {
        if (isExpanded) {
            btn.textContent = '▶ 배치별';
            btn.classList.remove('expanded');
        } else {
            btn.textContent = '▼ 접기';
            btn.classList.add('expanded');
        }
    }
}

// ── 크롤러 재실행 ──
async function rerunCrawler(retailer) {
    const confirmed = await showConfirm(`${retailer}\n크롤러를 재실행하시겠습니까?`);
    if (!confirmed) return;

    const date = document.getElementById('targetDate').value;
    const btn = document.querySelector(`button.btn-rerun[data-retailer="${retailer}"]`);

    if (btn) {
        btn.classList.add('loading');
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
                <circle cx="12" cy="12" r="10" stroke-dasharray="30" stroke-dashoffset="10"/>
            </svg>
        `;
    }

    try {
        const response = await fetch('/ds/layer1/api/rerun-crawler/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                retailer: retailer,
                crawl_date: date
            })
        });

        const result = await response.json();
        if (result.success) {
            showToast(`${retailer} 크롤러 재실행 요청 완료`);
            if (btn) {
                btn.classList.remove('loading');
                btn.disabled = true;
                btn.onclick = null;
                btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
            }
        } else {
            showToast(result.error || '재실행 요청 실패');
            if (btn) {
                btn.classList.remove('loading');
                btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`;
            }
        }
    } catch (error) {
        showToast('재실행 요청 실패');
        if (btn) {
            btn.classList.remove('loading');
            btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`;
        }
    }
}
