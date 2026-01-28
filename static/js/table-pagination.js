/**
 * 테이블 페이지네이션 공통 모듈
 *
 * 사용법:
 *   const pager = enablePagination('#tableBody', { perPage: 25 });
 *
 *   // 필터 적용 후 페이지네이션 갱신
 *   pager.reset();
 *
 * 옵션:
 *   perPage: 한 페이지당 행 수 (기본 25)
 *
 * 주의: 필터에서 행을 숨길 때 data-filtered="hidden" 속성을 사용해야 합니다.
 *       display:none 대신 이 속성으로 필터 상태를 관리합니다.
 */
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

// CSS 주입 (한 번만)
(function () {
    if (document.getElementById('pagination-style')) return;
    const style = document.createElement('style');
    style.id = 'pagination-style';
    style.textContent = `
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
    `;
    document.head.appendChild(style);
})();
