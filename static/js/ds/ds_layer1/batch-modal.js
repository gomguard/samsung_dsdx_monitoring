/**
 * DS Layer 1 — 배치관리 모달 (admin only)
 * 배치 CRUD + 리테일러 필터 + 신규 배치 추가
 *
 * DS_L1_CONFIG.isStaff === true 일 때만 활성화
 */

if (DS_L1_CONFIG.isStaff) {

var batchData = [];
var retailerList = [];

window.openBatchModal = async function() {
    const date = document.getElementById('targetDate').value;
    document.getElementById('batchModalDate').textContent = date;
    document.getElementById('batchModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    if (retailerList.length === 0 && statsData && statsData.results) {
        retailerList = [];
        statsData.results.forEach(r => {
            if (!retailerList.includes(r.retailer)) {
                retailerList.push(r.retailer);
            }
        });
        const select = document.getElementById('batchRetailerFilter');
        select.innerHTML = '<option value="">전체</option>';
        retailerList.forEach(r => {
            select.innerHTML += `<option value="${esc(r)}">${esc(r)}</option>`;
        });
    }

    await loadBatchData();
};

window.closeBatchModal = function() {
    document.getElementById('batchModal').classList.add('hidden');
    document.body.style.overflow = '';
};

window.closeBatchModalOnOverlay = function(event) {
    if (event.target === event.currentTarget) {
        closeBatchModal();
    }
};

window.loadBatchData = async function() {
    const date = document.getElementById('targetDate').value;

    document.getElementById('batchLoading').classList.remove('hidden');
    document.getElementById('batchContent').innerHTML = '';

    try {
        const response = await fetch(`/ds/layer1/api/batch/?date=${date}`);
        const data = await response.json();

        if (data.error) {
            document.getElementById('batchContent').innerHTML = `<div class="batch-empty">${esc(data.error)}</div>`;
        } else {
            batchData = data.batches || [];
            renderBatchTable();
        }
    } catch (error) {
        console.error('Error loading batch data:', error);
        document.getElementById('batchContent').innerHTML = '<div class="batch-empty">데이터 로드 실패</div>';
    }

    document.getElementById('batchLoading').classList.add('hidden');
};

window.filterBatches = function() {
    renderBatchTable();
};

window.renderBatchTable = function() {
    const filter = document.getElementById('batchRetailerFilter').value;
    const filtered = filter ? batchData.filter(b => b.retailer === filter) : batchData;

    if (filtered.length === 0) {
        document.getElementById('batchContent').innerHTML = `
            <div class="batch-empty">
                <p>등록된 배치가 없습니다.</p>
                <p style="margin-top: 8px; font-size: 12px;">"기본 배치 생성" 버튼을 클릭하여 기본 배치를 생성하세요.</p>
            </div>
        `;
        document.getElementById('batchInfo').textContent = '총 0개 배치';
        return;
    }

    const grouped = {};
    filtered.forEach(batch => {
        if (!grouped[batch.retailer]) {
            grouped[batch.retailer] = [];
        }
        grouped[batch.retailer].push(batch);
    });

    const retailerOrder = statsData && statsData.results
        ? statsData.results.map(r => r.retailer)
        : [];

    const sortedRetailers = Object.keys(grouped).sort((a, b) => {
        const idxA = retailerOrder.indexOf(a);
        const idxB = retailerOrder.indexOf(b);
        if (idxA === -1 && idxB === -1) return a.localeCompare(b);
        if (idxA === -1) return 1;
        if (idxB === -1) return -1;
        return idxA - idxB;
    });

    let html = `
        <table class="batch-table">
            <thead>
                <tr>
                    <th>리테일러</th>
                    <th>시작시간</th>
                    <th>종료시간</th>
                    <th>메모</th>
                    <th>액션</th>
                </tr>
            </thead>
            <tbody>
    `;

    for (const retailer of sortedRetailers) {
        const batches = grouped[retailer];
        batches.sort((a, b) => a.start_time.localeCompare(b.start_time));

        batches.forEach((batch, idx) => {
            const endTime = idx < batches.length - 1 ? batches[idx + 1].start_time.substring(0, 5) : '다음날';

            html += `
                <tr data-batch-id="${batch.id}">
                    <td><strong>${batch.retailer}</strong></td>
                    <td>
                        <input type="time" value="${batch.start_time.substring(0, 5)}"
                               id="time_${batch.id}" onchange="markChanged(${batch.id})">
                    </td>
                    <td style="color: var(--text-secondary);">${endTime}</td>
                    <td>
                        <input type="text" value="${batch.memo || ''}" placeholder="메모 입력"
                               id="memo_${batch.id}" onchange="markChanged(${batch.id})">
                    </td>
                    <td>
                        <div class="batch-actions">
                            <button class="app-btn app-btn-sm btn-save" onclick="saveBatch(${batch.id})" id="saveBtn_${batch.id}" disabled>저장</button>
                            ${idx === 0 ? '' : `<button class="app-btn app-btn-sm btn-delete" onclick="deleteBatch(${batch.id})">삭제</button>`}
                        </div>
                    </td>
                </tr>
            `;
        });
    }

    html += '</tbody></table>';
    document.getElementById('batchContent').innerHTML = html;
    document.getElementById('batchInfo').textContent = `총 ${filtered.length}개 배치`;
};

window.markChanged = function(batchId) {
    document.getElementById(`saveBtn_${batchId}`).disabled = false;
};

window.saveBatch = async function(batchId) {
    const startTime = document.getElementById(`time_${batchId}`).value;
    const memo = document.getElementById(`memo_${batchId}`).value;

    try {
        const response = await fetch('/ds/layer1/api/batch/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                id: batchId,
                start_time: startTime + ':00',
                memo: memo
            })
        });

        const result = await response.json();

        if (result.error) {
            showToast('저장 실패: ' + result.error, 'error');
        } else {
            showToast('저장되었습니다.', 'success');
            document.getElementById(`saveBtn_${batchId}`).disabled = true;
            await loadBatchData();
        }
    } catch (error) {
        showToast('저장 중 오류 발생: ' + error, 'error');
    }
};

window.deleteBatch = async function(batchId) {
    const confirmed = await showConfirm('이 배치를 삭제하시겠습니까?', 'warning');
    if (!confirmed) return;

    try {
        const response = await fetch('/ds/layer1/api/batch/delete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ id: batchId })
        });

        const result = await response.json();

        if (result.error) {
            showToast('삭제 실패: ' + result.error, 'error');
        } else {
            showToast('삭제되었습니다.', 'success');
            await loadBatchData();
        }
    } catch (error) {
        showToast('삭제 중 오류 발생: ' + error, 'error');
    }
};

window.initBatches = async function() {
    const date = document.getElementById('targetDate').value;

    const confirmed = await showConfirm(`${date} 날짜에 기본 배치를 생성하시겠습니까?`, 'info');
    if (!confirmed) return;

    try {
        const response = await fetch('/ds/layer1/api/batch/init/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ date: date })
        });

        const result = await response.json();

        if (result.error) {
            showToast('생성 실패: ' + result.error, 'error');
        } else {
            showToast(result.message, 'success');
            await loadBatchData();
        }
    } catch (error) {
        showToast('생성 중 오류 발생: ' + error, 'error');
    }
};

window.showAddBatchForm = function() {
    const filter = document.getElementById('batchRetailerFilter').value;

    if (!filter) {
        showToast('먼저 리테일러를 선택하세요.', 'warning');
        return;
    }

    if (document.getElementById('newBatchRow')) {
        document.getElementById('newTime').focus();
        return;
    }

    const tbody = document.querySelector('.batch-table tbody');
    if (!tbody) {
        document.getElementById('batchContent').innerHTML = `
            <table class="batch-table">
                <thead>
                    <tr>
                        <th>리테일러</th>
                        <th>시작시간</th>
                        <th>종료시간</th>
                        <th>메모</th>
                        <th>액션</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        `;
    }

    const newRow = document.createElement('tr');
    newRow.id = 'newBatchRow';
    newRow.style.background = '#eff6ff';
    newRow.innerHTML = `
        <td><strong>${filter}</strong> <span style="color: #3b82f6; font-size: 11px;">(신규)</span></td>
        <td>
            <input type="time" id="newTime" value="09:00">
        </td>
        <td style="color: var(--text-secondary);">-</td>
        <td>
            <input type="text" id="newMemo" value="재실행" placeholder="메모 입력">
        </td>
        <td>
            <div class="batch-actions">
                <button class="app-btn app-btn-sm btn-save" onclick="saveNewBatch('${filter}')">저장</button>
                <button class="app-btn app-btn-sm app-btn-cancel" onclick="cancelNewBatch()">취소</button>
            </div>
        </td>
    `;

    const tableBody = document.querySelector('.batch-table tbody');
    tableBody.appendChild(newRow);
    document.getElementById('newTime').focus();

    newRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

window.cancelNewBatch = function() {
    const newRow = document.getElementById('newBatchRow');
    if (newRow) {
        newRow.remove();
    }
};

window.saveNewBatch = async function(retailer) {
    const time = document.getElementById('newTime').value;
    const memo = document.getElementById('newMemo').value;

    if (!time) {
        showToast('시작시간을 입력하세요.', 'warning');
        return;
    }

    await addBatch(retailer, time, memo || '');
};

window.addBatch = async function(retailer, time, memo) {
    const date = document.getElementById('targetDate').value;

    try {
        const response = await fetch('/ds/layer1/api/batch/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                date: date,
                retailer: retailer,
                start_time: time + ':00',
                memo: memo
            })
        });

        const result = await response.json();

        if (result.error) {
            showToast('추가 실패: ' + result.error, 'error');
        } else {
            showToast('배치가 추가되었습니다.', 'success');
            await loadBatchData();
        }
    } catch (error) {
        showToast('추가 중 오류 발생: ' + error, 'error');
    }
};

} // end if (DS_L1_CONFIG.isStaff)

// 배치 모달이 없는 경우 빈 함수 제공
if (!window.closeBatchModal) {
    window.closeBatchModal = function() {};
}
