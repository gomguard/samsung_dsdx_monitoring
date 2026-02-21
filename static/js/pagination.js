/**
 * 페이지네이션 공통 컴포넌트
 *
 * 파일 위치: static/js/pagination.js
 * 스타일: static/css/common.css
 *
 * ============================================================
 * 사용법
 * ============================================================
 *
 * // 번호형 (기본)
 * const pager = new Pagination('#container', {
 *     pageSize: 20,
 *     maxVisible: 5,
 *     showInfo: true,
 *     onPageChange: (page) => { console.log(page); }
 * });
 * pager.render(totalItems, currentPage);
 *
 * // 단순형 (이전/다음)
 * const simplePager = new Pagination('#container', {
 *     variant: 'simple',
 *     pageSize: 50,
 *     showInfo: true,
 *     onPageChange: (page) => { loadData(page); }
 * });
 * simplePager.render(totalItems, currentPage);
 *
 * ============================================================
 */

class Pagination {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.options = {
            variant: 'numbered',    // 'numbered' | 'simple'
            pageSize: 20,
            maxVisible: 5,
            showInfo: true,
            onPageChange: null,
            ...options
        };

        this.currentPage = 1;
        this.totalItems = 0;
    }

    render(totalItems, currentPage = 1) {
        if (this.options.variant === 'simple') {
            return this._renderSimple(totalItems, currentPage);
        }

        this.totalItems = totalItems;
        this.currentPage = currentPage;

        const totalPages = Math.ceil(totalItems / this.options.pageSize) || 1;

        if (totalPages <= 1) {
            this.container.innerHTML = '';
            return;
        }

        let html = '<div class="pagination">';

        // 이전 버튼
        html += `<button class="pagination-btn" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="15 18 9 12 15 6"/>
            </svg>
        </button>`;

        // 페이지 번호
        const maxVisible = this.options.maxVisible;
        let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
        let endPage = Math.min(totalPages, startPage + maxVisible - 1);

        if (endPage - startPage + 1 < maxVisible) {
            startPage = Math.max(1, endPage - maxVisible + 1);
        }

        if (startPage > 1) {
            html += `<button class="pagination-btn" data-page="1">1</button>`;
            if (startPage > 2) html += `<span class="pagination-ellipsis">...</span>`;
        }

        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="pagination-btn ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += `<span class="pagination-ellipsis">...</span>`;
            html += `<button class="pagination-btn" data-page="${totalPages}">${totalPages}</button>`;
        }

        // 다음 버튼
        html += `<button class="pagination-btn" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="9 18 15 12 9 6"/>
            </svg>
        </button>`;

        // 페이지 정보
        if (this.options.showInfo) {
            const start = (currentPage - 1) * this.options.pageSize + 1;
            const end = Math.min(currentPage * this.options.pageSize, totalItems);
            html += `<span class="pagination-info">${start}-${end} / ${totalItems}</span>`;
        }

        html += '</div>';
        this.container.innerHTML = html;

        // 이벤트 바인딩
        this.container.querySelectorAll('.pagination-btn[data-page]').forEach(btn => {
            btn.addEventListener('click', () => {
                const page = parseInt(btn.dataset.page);
                if (page >= 1 && page <= totalPages && page !== currentPage) {
                    this.goToPage(page);
                }
            });
        });
    }

    _renderSimple(totalItems, currentPage = 1) {
        this.totalItems = totalItems;
        this.currentPage = currentPage;

        const totalPages = Math.ceil(totalItems / this.options.pageSize) || 1;

        let html = '<div class="pagination pagination-simple">';

        if (this.options.showInfo) {
            html += `<span class="pagination-info">총 ${totalItems.toLocaleString()}건</span>`;
        }

        html += '<div class="pagination-nav">';
        html += `<button class="pagination-btn" data-page="${currentPage - 1}" ${currentPage <= 1 ? 'disabled' : ''}>이전</button>`;
        html += `<span class="pagination-current">${currentPage} / ${totalPages}</span>`;
        html += `<button class="pagination-btn" data-page="${currentPage + 1}" ${currentPage >= totalPages ? 'disabled' : ''}>다음</button>`;
        html += '</div></div>';

        this.container.innerHTML = html;

        this.container.querySelectorAll('.pagination-btn[data-page]').forEach(btn => {
            btn.addEventListener('click', () => {
                const page = parseInt(btn.dataset.page);
                if (page >= 1 && page <= totalPages && page !== currentPage) {
                    this.goToPage(page);
                }
            });
        });
    }

    goToPage(page) {
        this.currentPage = page;
        if (this.options.onPageChange) {
            this.options.onPageChange(page);
        }
    }

    getCurrentPage() {
        return this.currentPage;
    }

    getPageSize() {
        return this.options.pageSize;
    }
}


/**
 * 통계 칩 클래스
 *
 * const stats = new StatChips('#container', [
 *     {id: 'total', label: '전체'},
 *     {id: 'active', label: '활성'}
 * ]);
 * stats.update('total', 100);
 * stats.updateAll({total: 100, active: 80});
 */
class StatChips {
    constructor(container, items = []) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.items = items;
        this.elements = {};
        this.render();
    }

    render() {
        let html = '<div class="stat-chips">';
        this.items.forEach(item => {
            html += `<span class="stat-chip">${item.label}<strong id="${item.id}">0</strong></span>`;
        });
        html += '</div>';
        this.container.innerHTML = html;

        this.items.forEach(item => {
            this.elements[item.id] = document.getElementById(item.id);
        });
    }

    update(id, value) {
        if (this.elements[id]) {
            this.elements[id].textContent = value;
        }
    }

    updateAll(data) {
        Object.keys(data).forEach(id => {
            this.update(id, data[id]);
        });
    }
}
