/**
 * 공통 사이드바 — initSidebar, toggleSidebarGroup, navigateSidebarGroup
 * onSubitemClick은 각 레이어 JS에서 정의 (레이어별 동작이 다름)
 */

function initSidebar() {
    var sidebar = document.getElementById('dx-sidebar');
    if (!sidebar) return;
    var storageKey = sidebar.dataset.storageKey || 'dxSidebarCollapsed';

    // localStorage에서 접힌 상태 복원
    if (localStorage.getItem(storageKey) === '1') {
        sidebar.classList.add('collapsed');
    }

    // 접기/펼치기 버튼
    var btn = sidebar.querySelector('.sidebar-collapse-btn');
    if (btn) {
        btn.addEventListener('click', function() {
            var collapsed = sidebar.classList.toggle('collapsed');
            localStorage.setItem(storageKey, collapsed ? '1' : '');
        });
    }
}

function toggleSidebarGroup(rowEl) {
    var group = rowEl.closest('.sidebar-group');
    if (group) group.classList.toggle('expanded');
}

function navigateSidebarGroup(rowEl) {
    var key = rowEl.dataset.key;
    var sidebar = document.getElementById('dx-sidebar');
    var baseUrl = sidebar ? (sidebar.dataset.baseUrl || '') : '';
    if (!key || !baseUrl) return;

    var dateEl = document.getElementById('target-date');
    var dateParam = (dateEl && dateEl.value) ? '?date=' + dateEl.value : '';
    window.location.href = baseUrl + key.replace(/_/g, '-') + '/' + dateParam;
}

document.addEventListener('DOMContentLoaded', initSidebar);
