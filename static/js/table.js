/**
 * 5단계 방어 체계 모니터링 시스템 - 테이블 공통 JavaScript
 *
 * CSS: static/css/table.css
 *
 * ============================================================
 * 함수 / 클래스 목록
 * ============================================================
 *
 * [CommonTable 클래스]
 * - new CommonTable(container, options)
 *     : 공통 테이블 생성 (variant 기반 스타일)
 *     옵션:
 *       - variant: 'detail' | 'admin' | 'list'
 *       - columns: [{ key, label, width, sortable, align }]
 *       - resize: true/false (기본 true)
 *       - reorder: true/false (기본 false) — 헤더 드래그로 열 이동
 *       - fixedColumns: ['_no'] — 이동 불가 컬럼 키 배열
 *       - onReorder: (newColumns) => {} — 열 이동 후 콜백
 *       - rowHeight: 행 콘텐츠 높이 px (미지정 시 CSS 기본값)
 *       - padding: 셀 패딩 문자열 (예: '8px 16px', 미지정 시 CSS 기본값)
 *       - onSort: (key, order) => {}
 *       - selectable: true | { multiple: bool, selectAll: bool }
 *           true → { multiple: true, selectAll: true }
 *           { multiple: false } → 라디오 (단일 선택)
 *     메서드:
 *       - render(): thead 생성 + 리사이즈/리오더 적용
 *       - renderBody(rows, renderRow): tbody 업데이트
 *       - getTable(): table 엘리먼트 반환
 *       - getColumns(): 현재 컬럼 순서 반환
 *       - getSelectedIds(): 선택된 행 ID 배열
 *       - getSelectedRows(): 선택된 행 데이터 배열
 *       - clearSelection(): 선택 초기화
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
 *     : 드래그 시 테이블 전체 너비도 함께 확장 (다른 열 영향 없음)
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
// CommonTable 클래스
// ============================================================

class CommonTable {
    constructor(container, options = {}) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;
        this.options = {
            variant: 'detail',
            columns: [],
            resize: true,
            reorder: false,
            fixedColumns: [],
            onReorder: null,
            vlines: false,
            rounded: false,
            bordered: false,
            section: false,
            card: false,
            rowHeight: null,
            padding: null,
            onSort: null,
            showTotalCount: false,
            pageSize: null,
            onPageSizeChange: null,
            selectable: false,
            ...options
        };
        // selectable 정규화: true → { multiple: true, selectAll: true }
        if (this.options.selectable === true) {
            this.options.selectable = { multiple: true, selectAll: true };
        } else if (this.options.selectable && typeof this.options.selectable === 'object') {
            this.options.selectable = {
                multiple: this.options.selectable.multiple !== false,
                selectAll: this.options.selectable.selectAll !== false
            };
        }
        this.multiSort = options.multiSort || false;
        this.sortKey = null;
        this.sortOrder = null;
        this.sortColumns = [];  // 다중 정렬: [{ key, order }] 순서 배열
        this.tableEl = null;
        this.countEl = null;
        this._pageSizeInput = null;
        this._selectedIds = new Set();
    }

    /**
     * thead 생성 + 리사이즈 적용
     * tbody는 빈 상태로 생성 → renderBody()로 채움
     */
    render() {
        const { variant, columns, resize, rowHeight, padding } = this.options;

        const table = document.createElement('table');
        table.className = `ct ct-${variant}${this.options.vlines ? ' ct-vlines' : ''}${this.options.bordered ? ' ct-bordered' : ''}${this.options.rounded ? ' ct-rounded' : ''}`;
        if (rowHeight) table.style.setProperty('--ct-row-height', rowHeight + 'px');
        if (padding) table.style.setProperty('--ct-padding', padding);

        // colgroup — 열 너비 제어 (table-layout: fixed에서 width 지정된 열은 고정, 미지정 열은 나머지 공간 분배)
        const colgroup = document.createElement('colgroup');
        const sel = this.options.selectable;
        if (sel) {
            const selCol = document.createElement('col');
            selCol.style.width = '35px';
            colgroup.appendChild(selCol);
        }
        columns.forEach(col => {
            const colEl = document.createElement('col');
            if (col.width) colEl.style.width = col.width + 'px';
            colgroup.appendChild(colEl);
        });
        table.appendChild(colgroup);

        // thead
        const thead = document.createElement('thead');
        const tr = document.createElement('tr');

        if (sel) {
            const selTh = document.createElement('th');
            selTh.style.textAlign = 'center';
            selTh.classList.add('ct-nc');
            if (sel.multiple && sel.selectAll) {
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.style.cssText = 'width:15px;height:15px;cursor:pointer;';
                cb.addEventListener('change', () => this._toggleSelectAll(cb.checked));
                this._selectAllCb = cb;
                selTh.appendChild(cb);
            }
            tr.appendChild(selTh);
        }

        columns.forEach((col, idx) => {
            const th = document.createElement('th');
            th.textContent = col.label;
            if (col.align) th.style.textAlign = col.align;
            if (col.sortable) {
                th.className = 'sortable';
                th.dataset.sortKey = col.key;
                th.addEventListener('click', () => this._handleSort(col.key, th));
            }
            th.dataset.colIdx = idx;
            tr.appendChild(th);
        });

        thead.appendChild(tr);
        table.appendChild(thead);

        // tbody (빈 상태)
        table.appendChild(document.createElement('tbody'));

        if (this.options.card) this.container.classList.add('card');
        this.container.innerHTML = '';

        var scrollWrap = document.createElement('div');
        scrollWrap.className = 'ct-scroll-wrap';
        scrollWrap.style.overflowX = 'auto';

        if (this.options.section) {
            const sectionEl = document.createElement('div');
            sectionEl.className = 'ct-section';
            sectionEl.appendChild(scrollWrap);
            this.container.appendChild(sectionEl);
            scrollWrap.appendChild(table);
        } else {
            this.container.appendChild(scrollWrap);
            scrollWrap.appendChild(table);
        }
        this.tableEl = table;

        // col width가 th 텍스트보다 좁으면 자동 보정
        const measureEl = document.createElement('span');
        measureEl.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font-size:13px;font-weight:600;';
        document.body.appendChild(measureEl);
        const colEls = colgroup.querySelectorAll('col');
        columns.forEach((col, idx) => {
            if (col.width) {
                measureEl.textContent = col.label;
                const textWidth = measureEl.offsetWidth;
                const sortExtra = col.sortable ? 17 : 0;
                const minWidth = textWidth + 32 + sortExtra;
                if (minWidth > col.width) {
                    colEls[idx].style.width = minWidth + 'px';
                }
            }
        });
        document.body.removeChild(measureEl);

        if (typeof this.options.pageSize === 'number') {
            var toolbar = document.createElement('div');
            toolbar.className = 'ct-toolbar';
            if (this.options.showTotalCount) {
                this.countEl = document.createElement('div');
                this.countEl.className = 'ct-count';
                toolbar.appendChild(this.countEl);
            }
            var right = document.createElement('div');
            right.className = 'ct-toolbar-right';
            var lbl = document.createElement('label');
            lbl.textContent = '건수';
            var psInput = document.createElement('input');
            psInput.type = 'number';
            psInput.className = 'ct-page-size';
            psInput.value = this.options.pageSize;
            psInput.min = 1;
            psInput.max = 200;
            this._pageSizeInput = psInput;
            var self = this;
            var applyPageSize = function() {
                var v = Math.min(Math.max(parseInt(psInput.value) || self.options.pageSize, 1), 200);
                psInput.value = v;
                if (self.options.onPageSizeChange) self.options.onPageSizeChange(v);
            };
            psInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') applyPageSize();
            });
            var psBtn = document.createElement('button');
            psBtn.type = 'button';
            psBtn.className = 'ct-page-size-btn';
            psBtn.textContent = '조회';
            psBtn.addEventListener('click', applyPageSize);
            right.appendChild(lbl);
            right.appendChild(psInput);
            right.appendChild(psBtn);
            toolbar.appendChild(right);
            this.container.insertBefore(toolbar, this.container.firstChild);
        } else if (this.options.showTotalCount) {
            this.countEl = document.createElement('div');
            this.countEl.className = 'ct-count';
            this.countEl.style.cssText = 'padding: 10px 12px; font-size: 13px; color: var(--text-secondary);';
            this.container.appendChild(this.countEl);
        }

        // 외부 countEl 지정 (옵션으로 DOM 요소 또는 셀렉터 전달)
        if (this.options.countEl) {
            this.countEl = typeof this.options.countEl === 'string'
                ? document.querySelector(this.options.countEl)
                : this.options.countEl;
        }

        // 셀 클릭 시 텍스트 선택 (Ctrl+C 복사용)
        // 셀 클릭 → 셀 하이라이트 + 텍스트 선택 (Ctrl+C 복사용)
        let selectedTd = null;
        table.addEventListener('click', (e) => {
            if (e.target.closest('input, textarea, select')) return;
            const td = e.target.closest('td');
            if (!td || td.classList.contains('ct-nc')) return;
            if (selectedTd) selectedTd.classList.remove('ct-selected');
            td.classList.add('ct-selected');
            selectedTd = td;
            const copyText = td.dataset.copyText;
            if (copyText !== undefined) {
                // data-copy-text가 있으면 숨겨진 텍스트 노드로 선택
                let span = td.querySelector('.ct-copy-helper');
                if (!span) {
                    span = document.createElement('span');
                    span.className = 'ct-copy-helper';
                    span.style.cssText = 'position:absolute;left:-9999px;';
                    td.style.position = 'relative';
                    td.appendChild(span);
                }
                span.textContent = copyText;
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(span);
                selection.removeAllRanges();
                selection.addRange(range);
            } else {
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(td);
                selection.removeAllRanges();
                selection.addRange(range);
            }
        });
        document.addEventListener('click', (e) => {
            if (selectedTd && !table.contains(e.target)) {
                selectedTd.classList.remove('ct-selected');
                selectedTd = null;
                window.getSelection().removeAllRanges();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && selectedTd) {
                selectedTd.classList.remove('ct-selected');
                selectedTd = null;
                window.getSelection().removeAllRanges();
            }
        });

        if (resize) enableColumnResize(table);
        if (this.options.reorder) this._enableReorder();

        return this;
    }

    /**
     * tbody 업데이트
     * @param {Array} rows - 데이터 배열
     * @param {Function} renderRow - (item, index) => HTML문자열 또는 tr 엘리먼트
     */
    renderBody(rows, renderRow) {
        const tbody = this.tableEl.querySelector('tbody');
        tbody.innerHTML = '';
        this._selectedIds.clear();
        this._lastRows = rows;
        if (this._selectAllCb) this._selectAllCb.checked = false;
        const sel = this.options.selectable;
        rows.forEach((row, i) => {
            const tr = renderRow(row, i);
            if (sel) {
                const rowId = row.id !== undefined ? row.id : i;
                if (typeof tr === 'string') {
                    const selTd = '<td style="text-align:center;" class="ct-nc"><input type="checkbox" class="ct-row-sel" data-row-id="' + rowId + '" style="width:15px;height:15px;cursor:pointer;"></td>';
                    tbody.insertAdjacentHTML('beforeend', tr.replace(/^<tr/, '<tr data-row-id="' + rowId + '"').replace(/>/, '>' + selTd));
                } else {
                    tr.dataset.rowId = rowId;
                    const selTd = document.createElement('td');
                    selTd.style.textAlign = 'center';
                    selTd.classList.add('ct-nc');
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'ct-row-sel';
                    cb.dataset.rowId = rowId;
                    cb.style.cssText = 'width:15px;height:15px;cursor:pointer;';
                    selTd.appendChild(cb);
                    tr.insertBefore(selTd, tr.firstChild);
                    tbody.appendChild(tr);
                }
            } else {
                if (typeof tr === 'string') {
                    tbody.insertAdjacentHTML('beforeend', tr);
                } else {
                    tbody.appendChild(tr);
                }
            }
        });
        // 체크박스 이벤트 바인딩
        if (sel) {
            tbody.querySelectorAll('.ct-row-sel').forEach(cb => {
                cb.addEventListener('change', () => {
                    const rid = cb.dataset.rowId;
                    if (sel.multiple) {
                        if (cb.checked) this._selectedIds.add(rid);
                        else this._selectedIds.delete(rid);
                        if (this._selectAllCb) {
                            const total = tbody.querySelectorAll('.ct-row-sel').length;
                            this._selectAllCb.checked = this._selectedIds.size === total;
                        }
                    } else {
                        this._selectedIds.clear();
                        tbody.querySelectorAll('.ct-row-sel').forEach(function(other) {
                            if (other !== cb) other.checked = false;
                        });
                        if (cb.checked) this._selectedIds.add(rid);
                    }
                });
            });
        }
        if (this.countEl) {
            if (typeof this.options.countFormat === 'function') {
                this.countEl.innerHTML = this.options.countFormat(rows.length);
            } else {
                this.countEl.innerHTML = '총 <strong>' + rows.length.toLocaleString() + '</strong>건';
            }
        }
    }

    getPageSize() {
        return this._pageSizeInput
            ? Math.min(Math.max(parseInt(this._pageSizeInput.value) || this.options.pageSize, 1), 200)
            : null;
    }

    setPageSize(val) {
        if (this._pageSizeInput) this._pageSizeInput.value = val;
    }

    /**
     * 정렬 상태 외부에서 설정 (API 재호출 후 thead 갱신 없이 상태 반영)
     */
    setSort(key, order) {
        this.sortKey = key;
        this.sortOrder = order;
        if (!this.multiSort) {
            this._updateSortUI();
        }
    }

    /**
     * 다중 정렬 상태 외부에서 설정
     * @param {Array} columns - [{ key, order }]
     */
    setSortColumns(columns) {
        this.sortColumns = (columns || []).slice();
        this._updateSortUI();
    }

    _handleSort(key, thEl) {
        if (this.multiSort) {
            this._handleMultiSort(key);
        } else {
            if (this.sortKey === key) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortKey = key;
                this.sortOrder = 'asc';
            }
            this._updateSortUI();
            if (this.options.onSort) {
                this.options.onSort(this.sortKey, this.sortOrder);
            }
        }
    }

    _handleMultiSort(key) {
        var idx = -1;
        for (var i = 0; i < this.sortColumns.length; i++) {
            if (this.sortColumns[i].key === key) { idx = i; break; }
        }
        if (idx >= 0) {
            if (this.sortColumns[idx].order === 'asc') {
                this.sortColumns[idx].order = 'desc';
            } else {
                this.sortColumns.splice(idx, 1);
            }
        } else {
            this.sortColumns.push({ key: key, order: 'asc' });
        }
        this._updateSortUI();
        if (this.options.onSort) {
            this.options.onSort(this.sortColumns.slice());
        }
    }

    _updateSortUI() {
        if (!this.tableEl) return;
        const ths = this.tableEl.querySelectorAll('th.sortable');
        ths.forEach(th => {
            th.classList.remove('asc', 'desc');
            th.removeAttribute('data-sort-order');
        });
        if (this.multiSort) {
            var showOrder = this.sortColumns.length > 1;
            this.sortColumns.forEach((col, idx) => {
                const th = this.tableEl.querySelector('th[data-sort-key="' + col.key + '"]');
                if (th) {
                    th.classList.add(col.order);
                    if (showOrder) th.setAttribute('data-sort-order', idx + 1);
                }
            });
        } else {
            ths.forEach(th => {
                if (th.dataset.sortKey === this.sortKey) {
                    th.classList.add(this.sortOrder);
                }
            });
        }
    }

    getTable() {
        return this.tableEl;
    }

    getColumns() {
        return this.options.columns.slice();
    }

    /** 선택된 행 ID 배열 반환 */
    getSelectedIds() {
        return Array.from(this._selectedIds);
    }

    /** 선택된 행 데이터 반환 (renderBody에 전달된 rows 기준) */
    getSelectedRows() {
        if (!this._lastRows) return [];
        return this._lastRows.filter((row, i) => {
            const rid = row.id !== undefined ? String(row.id) : String(i);
            return this._selectedIds.has(rid);
        });
    }

    /** 선택 초기화 */
    clearSelection() {
        this._selectedIds.clear();
        if (this._selectAllCb) this._selectAllCb.checked = false;
        if (this.tableEl) {
            this.tableEl.querySelectorAll('.ct-row-sel').forEach(cb => { cb.checked = false; });
        }
    }

    /** 전체 선택/해제 (내부) */
    _toggleSelectAll(checked) {
        const tbody = this.tableEl.querySelector('tbody');
        tbody.querySelectorAll('.ct-row-sel').forEach(cb => {
            cb.checked = checked;
            const rid = cb.dataset.rowId;
            if (checked) this._selectedIds.add(rid);
            else this._selectedIds.delete(rid);
        });
    }

    /**
     * 헤더 드래그로 열 이동
     * fixedColumns에 포함된 열은 드래그 불가
     */
    _enableReorder() {
        const self = this;
        const table = this.tableEl;
        const thead = table.querySelector('thead');
        const ths = thead.querySelectorAll('th');
        const fixed = new Set(this.options.fixedColumns || []);
        let dragSrc = null;

        ths.forEach(th => {
            const colIdx = parseInt(th.dataset.colIdx);
            const colKey = this.options.columns[colIdx]?.key;
            if (fixed.has(colKey)) return;

            th.draggable = true;
            th.classList.add('ct-reorderable');

            th.addEventListener('dragstart', e => {
                dragSrc = th;
                th.classList.add('ct-th-dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            });

            th.addEventListener('dragend', () => {
                th.classList.remove('ct-th-dragging');
                ths.forEach(t => t.classList.remove('ct-th-drag-left', 'ct-th-drag-right'));
                dragSrc = null;
            });

            th.addEventListener('dragover', e => {
                if (!dragSrc || dragSrc === th) return;
                const targetKey = self.options.columns[parseInt(th.dataset.colIdx)]?.key;
                if (fixed.has(targetKey)) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                const rect = th.getBoundingClientRect();
                const midX = rect.left + rect.width / 2;
                th.classList.remove('ct-th-drag-left', 'ct-th-drag-right');
                th.classList.add(e.clientX < midX ? 'ct-th-drag-left' : 'ct-th-drag-right');
            });

            th.addEventListener('dragleave', () => {
                th.classList.remove('ct-th-drag-left', 'ct-th-drag-right');
            });

            th.addEventListener('drop', e => {
                e.preventDefault();
                if (!dragSrc || dragSrc === th) return;

                const fromIdx = parseInt(dragSrc.dataset.colIdx);
                const toIdx = parseInt(th.dataset.colIdx);
                const rect = th.getBoundingClientRect();
                const insertAfter = e.clientX >= rect.left + rect.width / 2;

                // columns 배열 재정렬
                const cols = self.options.columns;
                const moved = cols.splice(fromIdx, 1)[0];
                let newPos = cols.indexOf(cols[toIdx > fromIdx ? toIdx - 1 : toIdx]);
                if (newPos === -1) newPos = toIdx > fromIdx ? toIdx - 1 : toIdx;
                if (insertAfter) newPos++;
                cols.splice(newPos, 0, moved);

                // DOM 재정렬: colgroup, thead, tbody 모든 행
                const colgroup = table.querySelector('colgroup');
                const colEls = Array.from(colgroup.querySelectorAll('col'));
                const movedCol = colEls.splice(fromIdx, 1)[0];
                colEls.splice(newPos, 0, movedCol);
                colgroup.innerHTML = '';
                colEls.forEach(c => colgroup.appendChild(c));

                const headerRow = thead.querySelector('tr');
                const thEls = Array.from(headerRow.querySelectorAll('th'));
                const movedTh = thEls.splice(fromIdx, 1)[0];
                thEls.splice(newPos, 0, movedTh);
                headerRow.innerHTML = '';
                thEls.forEach((t, i) => { t.dataset.colIdx = i; headerRow.appendChild(t); });

                const tbody = table.querySelector('tbody');
                Array.from(tbody.querySelectorAll('tr')).forEach(tr => {
                    const tds = Array.from(tr.children);
                    if (tds.length <= fromIdx) return;
                    const movedTd = tds.splice(fromIdx, 1)[0];
                    tds.splice(newPos, 0, movedTd);
                    tr.innerHTML = '';
                    tds.forEach(td => tr.appendChild(td));
                });

                ths.forEach(t => t.classList.remove('ct-th-drag-left', 'ct-th-drag-right'));

                if (self.options.onReorder) {
                    self.options.onReorder(self.options.columns.slice());
                }
            });
        });
    }
}

// ============================================================
// 페이지네이션
// ============================================================

function enablePagination(tbodySelector, options = {}) {
    const perPage = options.perPage || 25;
    const showInfo = options.showInfo !== undefined ? options.showInfo : true;
    const onRender = options.onRender || null;
    const tbody = typeof tbodySelector === 'string'
        ? document.querySelector(tbodySelector)
        : tbodySelector;

    if (!tbody) return null;

    let currentPage = 1;

    // 페이지네이션 컨테이너 생성
    const paginationEl = document.createElement('div');
    paginationEl.className = 'pagination';
    paginationEl.style.marginTop = '12px';
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

        let html = showInfo ? `<span class="pagination-info">${totalItems}개 중 ${start}-${end}</span>` : '';
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

    const cols = table.querySelector('colgroup')?.querySelectorAll('col');

    ths.forEach((th, idx) => {
        // 리사이즈 핸들 생성
        const handle = document.createElement('div');
        handle.className = 'col-resize-handle';
        th.style.position = 'relative';
        th.appendChild(handle);

        let startX, startWidth, startTableWidth;

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            e.stopPropagation();
            startX = e.pageX;
            startWidth = th.offsetWidth;
            startTableWidth = table.offsetWidth;

            // 드래그 중 시각 표시
            handle.classList.add('active');

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            const diff = e.pageX - startX;
            const newWidth = Math.max(40, startWidth + diff);
            const actualDiff = newWidth - startWidth;
            // colgroup의 해당 col 너비 직접 설정 (다른 열 영향 없음)
            if (cols && cols[idx]) {
                cols[idx].style.width = newWidth + 'px';
            }
            th.style.width = newWidth + 'px';
            th.style.minWidth = newWidth + 'px';
            // 테이블 전체 너비도 열 변화량과 동일하게 조정
            table.style.width = (startTableWidth + actualDiff) + 'px';
        }

        function onMouseUp() {
            handle.classList.remove('active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);

            // mouseup 후 발생하는 click 이벤트가 sortable th의 정렬을 트리거하지 않도록 차단
            th.addEventListener('click', function stopClick(e) {
                e.stopImmediatePropagation();
                th.removeEventListener('click', stopClick, true);
            }, true);
        }
    });
}

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
