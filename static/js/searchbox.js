/**
 * 조회박스 공통 컴포넌트
 *
 * 파일 위치: static/js/searchbox.js
 * 스타일: static/css/common.css
 *
 * ============================================================
 * 사용법
 * ============================================================
 *
 * const search = new SearchBox('#container', {
 *     fieldLabel: '키워드',
 *     fields: [{value: 'id', label: 'ID'}, {value: 'name', label: '이름'}],
 *     fieldDefault: 1,            // 1=전체, 2=선택(placeholder), 3=공백
 *     statusLabel: '활성여부',
 *     statusOptions: [{value: 'active', label: '활성'}, {value: 'inactive', label: '비활성'}],
 *     statusDefault: 1,           // 1=전체, 2=선택(placeholder), 3=공백
 *     onSearch: (filters) => { console.log(filters); },
 *     onReset: () => { console.log('reset'); }
 * });
 *
 * fieldDefault / statusDefault 옵션:
 *   1 = "전체" (드롭다운 목록에 포함, value='')
 *   2 = "선택" (플레이스홀더만, 드롭다운 목록에 안 나옴)
 *   3 = 공백   (플레이스홀더도 공백, 드롭다운 목록에 안 나옴)
 *
 * ============================================================
 */

class SearchBox {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.options = {
            fieldLabel: '',
            fields: [],
            fieldDefault: 1,
            showStatus: true,
            statusLabel: '',
            statusOptions: [
                {value: 'active', label: '활성'},
                {value: 'inactive', label: '비활성'}
            ],
            statusDefault: 1,
            placeholder: '검색어 입력...',
            onSearch: null,
            onReset: null,
            ...options
        };

        this.elements = {};
        this.render();
        this.bindEvents();
    }

    _buildDefaultOption(type) {
        if (type === 1) {
            return '<option value="">전체</option>';
        } else if (type === 2) {
            return '<option value="" disabled selected hidden>선택</option>';
        } else if (type === 3) {
            return '<option value="" disabled selected hidden></option>';
        }
        return '';
    }

    render() {
        let fieldHtml = '';
        if (this.options.fields.length > 0) {
            const defaultOpt = this._buildDefaultOption(this.options.fieldDefault);
            const fieldOpts = this.options.fields.map(f =>
                `<option value="${f.value}">${f.label}</option>`
            ).join('');

            fieldHtml = `
                ${this.options.fieldLabel ? `<span class="search-box-label">${this.options.fieldLabel}</span>` : ''}
                <select class="search-box-select" data-role="field">
                    ${defaultOpt}${fieldOpts}
                </select>
            `;
        }

        let statusHtml = '';
        if (this.options.showStatus) {
            const defaultOpt = this._buildDefaultOption(this.options.statusDefault);
            const statusOpts = this.options.statusOptions.map(s =>
                `<option value="${s.value}">${s.label}</option>`
            ).join('');

            statusHtml = `
                ${this.options.statusLabel ? `<span class="search-box-label">${this.options.statusLabel}</span>` : ''}
                <select class="search-box-select" data-role="status">
                    ${defaultOpt}${statusOpts}
                </select>
            `;
        }

        const html = `
            <div class="search-box">
                ${fieldHtml}
                <input type="text" class="search-box-input" data-role="keyword" placeholder="${this.options.placeholder}">
                ${statusHtml}
                <button class="search-box-btn search-box-btn-search" data-role="search">조회</button>
                <button class="search-box-btn search-box-btn-reset" data-role="reset">해제</button>
            </div>
        `;
        this.container.innerHTML = html;

        this.elements.field = this.container.querySelector('[data-role="field"]');
        this.elements.keyword = this.container.querySelector('[data-role="keyword"]');
        this.elements.status = this.container.querySelector('[data-role="status"]');
        this.elements.searchBtn = this.container.querySelector('[data-role="search"]');
        this.elements.resetBtn = this.container.querySelector('[data-role="reset"]');
    }

    bindEvents() {
        this.elements.searchBtn?.addEventListener('click', () => this.search());
        this.elements.resetBtn?.addEventListener('click', () => this.reset());
        this.elements.keyword?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.search();
        });
    }

    getFilters() {
        return {
            field: this.elements.field?.value || '',
            keyword: this.elements.keyword?.value?.trim() || '',
            status: this.elements.status?.value || ''
        };
    }

    search() {
        const filters = this.getFilters();
        if (this.options.onSearch) {
            this.options.onSearch(filters);
        }
    }

    reset() {
        if (this.elements.field) this.elements.field.selectedIndex = 0;
        if (this.elements.keyword) this.elements.keyword.value = '';
        if (this.elements.status) this.elements.status.selectedIndex = 0;

        if (this.options.onReset) {
            this.options.onReset();
        }
    }

    setField(value) {
        if (this.elements.field) this.elements.field.value = value;
    }

    setKeyword(value) {
        if (this.elements.keyword) this.elements.keyword.value = value;
    }

    setStatus(value) {
        if (this.elements.status) this.elements.status.value = value;
    }
}
