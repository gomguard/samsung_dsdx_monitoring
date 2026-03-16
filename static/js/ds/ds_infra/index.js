/* DS Infra — EC2 인스턴스 현황 */

let instanceData = [];

async function loadEC2Status() {
    const container = document.getElementById('instance-container');
    const refreshBtn = document.querySelector('.btn-refresh');

    refreshBtn.disabled = true;
    container.innerHTML = `
        <div class="loading-overlay">
            <div style="width:40px;height:40px;border:3px solid #e2e8f0;border-top-color:#2563eb;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px;"></div>
            인스턴스 정보를 불러오는 중...
        </div>`;

    try {
        const res = await fetch('/ds/infra/api/ec2-status/');
        const data = await res.json();

        if (!data.success) {
            container.innerHTML = '<div class="loading-overlay" style="color:#ef4444;">인스턴스 정보를 불러올 수 없습니다.</div>';
            showToast('인스턴스 조회에 실패했습니다.', 'error');
            return;
        }

        instanceData = data.instances || [];
        renderInstances();
        renderSummary();
    } catch (e) {
        container.innerHTML = '<div class="loading-overlay" style="color:#ef4444;">인스턴스 정보를 불러올 수 없습니다.</div>';
        showToast('서버 연결에 실패했습니다.', 'error');
    } finally {
        refreshBtn.disabled = false;
    }
}

function renderSummary() {
    let running = 0, stopped = 0, other = 0, noaws = 0;

    instanceData.forEach(inst => {
        if (!inst.is_aws) { noaws++; return; }
        if (inst.state === 'running') running++;
        else if (inst.state === 'stopped') stopped++;
        else other++;
    });

    const total = instanceData.length;
    document.getElementById('cnt-total').textContent = total;
    document.getElementById('cnt-running').textContent = running;
    document.getElementById('cnt-stopped').textContent = stopped;
    document.getElementById('cnt-noaws').textContent = noaws;
}

function renderInstances() {
    const container = document.getElementById('instance-container');

    if (instanceData.length === 0) {
        container.innerHTML = '<div class="loading-overlay">등록된 인스턴스가 없습니다.</div>';
        return;
    }

    let html = `
        <table class="instance-table">
            <thead>
                <tr>
                    <th style="width:50px;text-align:center;">No</th>
                    <th>리테일러</th>
                    <th>리전명</th>
                    <th style="text-align:center;">상태</th>
                    <th style="text-align:center;">제어</th>
                </tr>
            </thead>
            <tbody>`;

    instanceData.forEach((inst, idx) => {
        const dotClass = inst.is_aws ? (inst.state || 'unknown') : 'noaws';
        const badgeClass = inst.is_aws ? `badge-${inst.state || 'unknown'}` : 'badge-noaws';
        const stateText = inst.is_aws ? getStateText(inst.state) : 'AWS 아님';
        const retailerName = inst.retailers.join(', ');

        const powerIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 2v10"/><path d="M18.36 6.64A9 9 0 1 1 5.64 6.64"/></svg>`;
        let actionHtml = '';
        if (inst.is_aws) {
            if (inst.state === 'pending' || inst.state === 'stopping') {
                actionHtml = `<div class="action-btns"><button class="btn-power" disabled title="${getStateText(inst.state)}">${powerIcon}</button></div>`;
            } else {
                const startDisabled = inst.state === 'running' ? ' disabled' : '';
                const stopDisabled = inst.state === 'stopped' ? ' disabled' : '';
                actionHtml = `<div class="action-btns">
                    <button class="btn-power start"${startDisabled} onclick="ec2Action('${inst.key}', 'start', '${retailerName}')" title="시작">${powerIcon}</button>
                    <button class="btn-power stop"${stopDisabled} onclick="ec2Action('${inst.key}', 'stop', '${retailerName}')" title="중지">${powerIcon}</button>
                </div>`;
            }
        } else {
            actionHtml = '<div style="text-align:center;color:#94a3b8;font-size:12px;">-</div>';
        }

        html += `
            <tr data-key="${inst.key}">
                <td style="text-align:center;color:#64748b;">${idx + 1}</td>
                <td>
                    <div class="retailer-tags">
                        ${inst.retailers.map(r => `<span class="retailer-tag">${r}</span>`).join('')}
                    </div>
                </td>
                <td><span class="region-text">${inst.region_name || '-'}</span></td>
                <td>
                    <div class="state-cell">
                        <span class="state-dot ${dotClass}"></span>
                        <span class="state-badge ${badgeClass}">${stateText}</span>
                    </div>
                </td>
                <td>${actionHtml}</td>
            </tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function getStateText(state) {
    const map = {
        'running': '실행 중',
        'stopped': '중지됨',
        'pending': '시작 중',
        'stopping': '중지 중',
        'shutting-down': '종료 중',
        'terminated': '삭제됨',
        'unknown': '조회 불가',
    };
    return map[state] || state || '알 수 없음';
}

async function ec2Action(key, action, retailerName) {
    const actionText = action === 'start' ? '시작' : '중지';
    const confirmed = await showConfirm(
        `${retailerName}\n인스턴스를 ${actionText}하시겠습니까?`,
        action === 'stop' ? 'warning' : 'info',
        { okText: actionText, cancelText: '취소' }
    );

    if (!confirmed) return;

    try {
        const res = await fetch('/ds/infra/api/ec2-action/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ key, action }),
        });

        const data = await res.json();

        if (data.success) {
            showToast(data.message || `${retailerName} ${actionText} 요청 완료`, 'success');
            const newState = action === 'start' ? 'pending' : 'stopping';
            updateRowState(key, newState);
        } else {
            showToast('요청 처리에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('서버 연결에 실패했습니다.', 'error');
    }
}

function updateRowState(key, newState) {
    const row = document.querySelector(`tr[data-key="${key}"]`);
    if (!row) return;
    const stateCell = row.querySelector('.state-cell');
    if (stateCell) {
        stateCell.innerHTML = `<span class="state-dot ${newState}"></span><span class="state-badge badge-${newState}">${getStateText(newState)}</span>`;
    }
    const actionCell = row.querySelector('.action-btns');
    if (actionCell) {
        const powerIcon = actionCell.querySelector('svg').outerHTML;
        actionCell.innerHTML = `<button class="btn-power" disabled title="${getStateText(newState)}">${powerIcon}</button>`;
    }
}

// getCsrfToken → security.js 공통
// showConfirm → ui.js 공통

document.addEventListener('DOMContentLoaded', loadEC2Status);
