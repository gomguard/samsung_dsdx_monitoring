/**
 * 5단계 방어 체계 모니터링 시스템 - 테이블 공통 JavaScript
 *
 * ============================================================
 * 함수 목록
 * ============================================================
 *
 * [페이지네이션]
 * - enablePagination(tbodySelector, options)
 *     : 테이블에 페이지네이션 기능 추가
 *     옵션:
 *       - perPage: 한 페이지당 행 수 (기본 25)
 *       - onRender: 렌더링 후 콜백
 *       - deferRender: true면 초기 렌더링 스킵
 *     반환:
 *       - render(): 페이지 렌더링
 *       - reset(): 1페이지로 리셋
 *       - goTo(page): 특정 페이지로 이동
 *       - getCurrentPage(): 현재 페이지 반환
 *     주의: 필터 시 data-filtered="hidden" 속성 사용
 *
 * [컬럼 리사이즈]
 * - enableColumnResize(tableOrSelector)
 *     : 테이블 헤더 드래그로 열 너비 조정 기능 추가
 *
 * [자동 적용]
 * - .auto-resize 클래스가 있는 테이블 → 컬럼 리사이즈 자동 적용
 * - .auto-paginate 클래스가 있는 테이블 → 페이지네이션 자동 적용
 *     data-per-page="25" 속성으로 페이지당 행 수 설정 가능
 *
 * - getTablePager(tableSelector)
 *     : 자동 적용된 pager 인스턴스 반환
 *
 * ============================================================
 */

// 자동 적용된 pager 인스턴스 저장소
const _tablePagers = new Map();

// ============================================================
// 페이지네이션
// ============================================================

function enablePagination(tbodySelector, options = {}) {
    const perPage = options.perPage || 25;
    const onRender = options.onRender || null;
    const tbody = typeof tbodySelector === 'string'
        ? document.querySelector(tbodySelector)
        : tbodySelector;

    if (!tbody) return null;

    let currentPage = 1;

    // 페이지네이션 컨테이너 생성
    const paginationEl = document.createElement('div');
    paginationEl.className = 'pagination';
    const table = tbody.closest('table');
    const wrapper = table.parentElement;
    wrapper.parentElement.insertBefore(paginationEl, wrapper.nextSibling);

    function getFilteredRows() {
        // 필터에 의해 숨겨지지 않은 행만 반환
        return Array.from(tbody.querySelectorAll('tr')).filter(
            r => r.getAttribute('data-filtered') !== 'hidden'
        );
    }

    function render() {
        const allRows = Array.from(tbody.querySelectorAll('tr'));
        const visibleRows = getFilteredRows();

        const totalPages = Math.max(1, Math.ceil(visibleRows.length / perPage));
        if (currentPage > totalPages) currentPage = totalPages;

        const start = (currentPage - 1) * perPage;
        const end = start + perPage;

        // 모든 행 숨기기
        allRows.forEach(r => r.style.display = 'none');

        // 필터 통과한 행 중 현재 페이지에 해당하는 것만 보이기
        visibleRows.forEach((row, i) => {
            if (i >= start && i < end) {
                row.style.display = '';
            }
        });

        renderControls(visibleRows.length, totalPages);

        if (onRender) onRender(visibleRows, start);
    }

    function renderControls(totalItems, totalPages) {
        if (totalItems === 0) {
            paginationEl.innerHTML = '<span class="pagination-info">0개</span>';
            return;
        }

        const start = (currentPage - 1) * perPage + 1;
        const end = Math.min(currentPage * perPage, totalItems);

        let html = `<span class="pagination-info">${totalItems}개 중 ${start}-${end}</span>`;
        html += '<div class="pagination-buttons">';

        // 이전
        html += `<button class="pagination-btn" ${currentPage <= 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&laquo;</button>`;

        // 페이지 번호
        const maxButtons = 5;
        let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        if (startPage > 1) {
            html += `<button class="pagination-btn" data-page="1">1</button>`;
            if (startPage > 2) html += `<span class="pagination-dots">...</span>`;
        }

        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="pagination-btn ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += `<span class="pagination-dots">...</span>`;
            html += `<button class="pagination-btn" data-page="${totalPages}">${totalPages}</button>`;
        }

        // 다음
        html += `<button class="pagination-btn" ${currentPage >= totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">&raquo;</button>`;
        html += '</div>';

        paginationEl.innerHTML = html;

        // 이벤트
        paginationEl.querySelectorAll('.pagination-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', function () {
                currentPage = parseInt(this.dataset.page);
                render();
            });
        });
    }

    function reset() {
        currentPage = 1;
        render();
    }

    // 초기 렌더 (deferRender 옵션이면 건너뜀)
    if (!options.deferRender) render();

    return { render, reset, goTo: (p) => { currentPage = p; render(); }, getCurrentPage: () => currentPage };
}

// ============================================================
// 컬럼 리사이즈
// ============================================================

function enableColumnResize(tableOrSelector) {
    const table = typeof tableOrSelector === 'string'
        ? document.querySelector(tableOrSelector)
        : tableOrSelector;

    if (!table || !table.querySelector('thead')) return;

    const thead = table.querySelector('thead');
    const ths = thead.querySelectorAll('th');

    ths.forEach(th => {
        // 리사이즈 핸들 생성
        const handle = document.createElement('div');
        handle.className = 'col-resize-handle';
        th.style.position = 'relative';
        th.appendChild(handle);

        let startX, startWidth, thEl;

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            e.stopPropagation();
            thEl = th;
            startX = e.pageX;
            startWidth = th.offsetWidth;

            // 드래그 중 시각 표시
            handle.classList.add('active');

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            const diff = e.pageX - startX;
            const newWidth = Math.max(40, startWidth + diff);
            thEl.style.width = newWidth + 'px';
            thEl.style.minWidth = newWidth + 'px';
        }

        function onMouseUp() {
            handle.classList.remove('active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
    });
}

// ============================================================
// CSS 주입 (한 번만)
// ============================================================

(function () {
    if (document.getElementById('table-utils-style')) return;
    const style = document.createElement('style');
    style.id = 'table-utils-style';
    style.textContent = `
        /* 페이지네이션 */
        .pagination {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            font-size: 13px;
            color: var(--text-secondary);
        }
        .pagination-info {
            font-size: 13px;
        }
        .pagination-buttons {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .pagination-btn {
            min-width: 32px;
            height: 32px;
            padding: 0 8px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .pagination-btn:hover:not([disabled]) {
            background: var(--bg-secondary);
            color: var(--text-primary);
        }
        .pagination-btn.active {
            background: #7c3aed;
            color: white;
            border-color: #7c3aed;
        }
        .pagination-btn[disabled] {
            opacity: 0.4;
            cursor: default;
        }
        .pagination-dots {
            padding: 0 4px;
            color: var(--text-secondary);
        }

        /* 컬럼 리사이즈 */
        .col-resize-handle {
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 5px;
            cursor: col-resize;
            user-select: none;
            z-index: 1;
        }
        .col-resize-handle:hover,
        .col-resize-handle.active {
            background: rgba(139, 92, 246, 0.3);
        }
    `;
    document.head.appendChild(style);
})();

// ============================================================
// 자동 적용된 pager 가져오기
// ============================================================

function getTablePager(tableSelector) {
    return _tablePagers.get(tableSelector) || null;
}

// ============================================================
// 자동 초기화 (DOMContentLoaded)
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // .auto-resize 클래스가 있는 테이블에 컬럼 리사이즈 적용
    document.querySelectorAll('table.auto-resize').forEach(table => {
        enableColumnResize(table);
    });

    // .auto-paginate 클래스가 있는 테이블에 페이지네이션 적용
    document.querySelectorAll('table.auto-paginate').forEach(table => {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        const perPage = parseInt(table.dataset.perPage) || 25;
        const pager = enablePagination(tbody, { perPage });

        // 테이블 ID나 클래스로 pager 저장
        const key = table.id || table.className;
        if (key) {
            _tablePagers.set(key, pager);
        }
    });
});
