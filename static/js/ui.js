/**
 * UI 컴포넌트 함수
 *
 * - showLoading(container)                    : 로딩 스피너 표시
 * - showError(container, message)             : 에러 메시지 표시
 * - showToast(message, type, duration)        : 토스트 알림 (success, error, warning, info)
 * - showConfirm(msg, type, options)           : 커스텀 확인 다이얼로그 (Promise 반환)
 */

function showLoading(container) {
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <span style="margin-left: 12px;">로딩 중...</span>
        </div>
    `;
}

function showError(container, message) {
    container.innerHTML = `
        <div class="loading" style="color: var(--color-critical);"></div>
    `;
    container.querySelector('.loading').textContent = message || '데이터를 불러올 수 없습니다.';
}

function showToast(message, type = 'info', duration = 3000) {
    const existingToast = document.getElementById('commonToast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.id = 'commonToast';
    toast.className = 'common-toast';

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    const colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };

    toast.innerHTML = `
        <span style="margin-right: 8px; font-size: 16px;">${icons[type] || icons.info}</span>
        <span></span>
    `;
    toast.querySelectorAll('span')[1].textContent = message;

    toast.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) scale(0.9);
        background: ${colors[type] || colors.info};
        color: white;
        padding: 14px 28px;
        border-radius: 12px;
        font-size: 14px;
        font-weight: 500;
        z-index: 10000;
        opacity: 0;
        transition: all 0.3s ease;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: center;
    `;

    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translate(-50%, -50%) scale(1)';
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translate(-50%, -50%) scale(0.9)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showConfirm(msg, type, options) {
    if (!type) type = 'info';
    if (!options) options = {};

    var icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" width="40" height="40"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" width="40" height="40"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6"/><path d="M9 9l6 6"/></svg>',
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" width="40" height="40"><path d="M12 9v2m0 4h.01M5.07 19H19a2 2 0 0 0 1.75-2.96L13.74 4a2 2 0 0 0-3.5 0L3.32 16.04A2 2 0 0 0 5.07 19z"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" width="40" height="40"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
    };
    var colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };

    return new Promise(function(resolve) {
        var existing = document.getElementById('confirmOverlay');
        if (existing) existing.remove();

        var overlay = document.createElement('div');
        overlay.id = 'confirmOverlay';
        overlay.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:10002; display:flex; justify-content:center; align-items:center;';
        overlay.innerHTML =
            '<div style="background:#fff; border-radius:12px; padding:28px 32px 20px; min-width:320px; max-width:440px; box-shadow:0 12px 40px rgba(0,0,0,0.25); text-align:center;">' +
                '<div style="margin-bottom:12px;">' + icons[type] + '</div>' +
                '<div id="confirmMsg" style="font-size:15px; font-weight:500; color:#1a1a1a; line-height:1.5; margin-bottom:24px; white-space:pre-line;"></div>' +
                '<div style="display:flex; gap:10px; justify-content:center;">' +
                    '<button id="confirmOk" style="padding:9px 28px; border-radius:8px; font-size:14px; font-weight:600; border:none; cursor:pointer; background:' + colors[type] + '; color:#fff; transition:opacity 0.15s;">' + (options.okText || '확인') + '</button>' +
                    (options.hideCancel ? '' : '<button id="confirmCancel" style="padding:9px 28px; border-radius:8px; font-size:14px; font-weight:600; border:none; cursor:pointer; background:#f3f4f6; color:#1a1a1a; transition:opacity 0.15s;">' + (options.cancelText || '취소') + '</button>') +
                '</div>' +
            '</div>';
        document.body.appendChild(overlay);

        document.getElementById('confirmMsg').textContent = msg;

        var ok = document.getElementById('confirmOk');
        var cancel = document.getElementById('confirmCancel');

        function cleanup() {
            overlay.remove();
            ok.removeEventListener('click', onOk);
            if (cancel) cancel.removeEventListener('click', onCancel);
            overlay.removeEventListener('click', onBg);
        }
        function onOk() { cleanup(); resolve(true); }
        function onCancel() { cleanup(); resolve(false); }
        function onBg(e) { if (e.target === overlay) { cleanup(); resolve(false); } }
        ok.addEventListener('click', onOk);
        if (cancel) cancel.addEventListener('click', onCancel);
        overlay.addEventListener('click', onBg);
    });
}
