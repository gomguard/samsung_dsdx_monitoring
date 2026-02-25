/**
 * RawDataView — Layer1 상세 데이터 뷰 공통 클래스
 *
 * 의존: CommonTable (table.js), Pagination (pagination.js), FilterBar (filter-bar.js)
 *       esc() (security.js), DEFAULT_COL_WIDTH (base_layer1.html), getSelectedDate() (base_layer1.html)
 *
 * ============================================================
 * 사용법
 * ============================================================
 *
 * var rawView = new RawDataView({
 *     apiUrl: '/layer1/api/retailer-raw-data/',
 *     backUrl: '/layer1/retail/',
 *     title: function(params) { return params.category + ' Retail - ' + params.retailer; },
 *     urlParams: ['category', 'retailer', 'period'],
 *     extraControls: [],     // FilterBar 추가 컨트롤 (optional)
 *     onInit: null            // URL 파라미터 커스텀 처리 (optional)
 * });
 *
 * // loadSectionData 내에서:
 * if (rawView.checkUrlAndShow()) return;
 *
 * ============================================================
 */

class RawDataView {
    constructor(options) {
        this.apiUrl = options.apiUrl;
        this.backUrl = options.backUrl;
        this.titleFn = options.title;
        this.urlParams = options.urlParams || [];
        this.extraControls = options.extraControls || [];
        this.onInit = options.onInit || null;

        this.state = {
            data: [],
            columns: [],
            sortColumn: null,
            sortDirection: null,
            originalData: [],
            filteredData: null,
            hiddenColumns: new Set(),
            columnOrder: []
        };
        this.table = null;
        this.filterBar = null;
        this.pager = null;
        this.params = {};
        this.PAGE_SIZE = 15;
        this._dragItem = null;
    }

    // ── URL 파라미터 확인 → 상세 뷰 자동 진입 ──────────────

    checkUrlAndShow() {
        var urlSearchParams = new URLSearchParams(window.location.search);

        // onInit: 커스텀 핸들러 (market_demand의 missing view 등)
        if (this.onInit && this.onInit(urlSearchParams)) return true;

        // 첫 번째 urlParam이 있으면 상세 뷰 진입
        if (!this.urlParams.length) return false;
        var firstVal = urlSearchParams.get(this.urlParams[0]);
        if (!firstVal) return false;

        var params = {};
        for (var i = 0; i < this.urlParams.length; i++) {
            var key = this.urlParams[i];
            var val = urlSearchParams.get(key);
            if (val) params[key] = val;
        }

        this.show(params);
        return true;
    }

    // ── 상세 뷰 표시 ──────────────────────────────────────

    show(params) {
        this.params = params;

        document.getElementById('filter-bar-container').style.display = 'none';
        document.getElementById('summary-view').style.display = 'none';
        document.getElementById('raw-data-view').style.display = '';

        document.getElementById('raw-data-title').textContent = this.titleFn(params);

        // 상태 초기화
        this.state = {
            data: [],
            columns: [],
            sortColumn: null,
            sortDirection: null,
            originalData: [],
            filteredData: null,
            hiddenColumns: new Set(),
            columnOrder: []
        };
        this.table = null;
        this.filterBar = null;
        this.pager = null;
        document.getElementById('rawDataPagination').innerHTML = '';
        document.getElementById('raw-data-filter-bar').innerHTML = '';

        this.load();
    }

    // ── API 호출 + 데이터 로드 ─────────────────────────────

    load() {
        var self = this;
        var currentDate = getSelectedDate();

        var wrapperEl = document.getElementById('rawDataTableWrapper');
        var countEl = document.getElementById('rawDataCount');
        wrapperEl.innerHTML = '<div class="raw-data-loading"><div class="raw-data-loading-spinner"></div>데이터를 불러오는 중...</div>';

        // URL 구성
        var url = this.apiUrl + '?date=' + encodeURIComponent(currentDate);
        for (var key in this.params) {
            url += '&' + key + '=' + encodeURIComponent(this.params[key]);
        }

        fetch(url)
            .then(function(response) { return response.json(); })
            .then(function(result) {
                if (result.error) {
                    wrapperEl.innerHTML = '<div class="raw-data-empty">오류: ' + esc(result.error) + '</div>';
                    return;
                }

                if (!result.data || result.data.length === 0) {
                    countEl.innerHTML = '총 <strong>0</strong>건';
                    wrapperEl.innerHTML = '<div class="raw-data-empty">데이터가 없습니다.</div>';
                    self.initFilterBar();
                    return;
                }

                self.state.columns = result.columns;
                self.state.columnOrder = [];
                for (var ci = 1; ci < result.columns.length; ci++) self.state.columnOrder.push(ci);
                self.state.data = result.data.slice().sort(function(a, b) {
                    return a[0] - b[0];
                });
                self.state.originalData = self.state.data.slice();
                self.state.sortColumn = 0;
                self.state.sortDirection = 'asc';

                countEl.innerHTML = '총 <strong>' + esc(String(result.total_count)) + '</strong>건' + (result.total_count > 500 ? ' (최대 500건 표시)' : '');

                self.initFilterBar();
                self.renderTable();
            })
            .catch(function(error) {
                wrapperEl.innerHTML = '<div class="raw-data-empty">데이터를 불러오는데 실패했습니다.</div>';
                console.error('Error:', error);
            });
    }

    // ── 테이블 렌더링 ──────────────────────────────────────

    renderTable() {
        var self = this;
        var columns = [
            { key: '_no', label: 'No.', width: 50, sortable: false, align: 'center' },
            { key: '0', label: this.state.columns[0], width: DEFAULT_COL_WIDTH, sortable: true }
        ];
        for (var oi = 0; oi < this.state.columnOrder.length; oi++) {
            var idx = this.state.columnOrder[oi];
            columns.push({
                key: String(idx),
                label: this.state.columns[idx],
                width: DEFAULT_COL_WIDTH,
                sortable: true
            });
        }

        this.table = new CommonTable('#rawDataTableWrapper', {
            variant: 'detail',
            columns: columns,
            vlines: true,
            padding: '10px 12px',
            onSort: function(key, order) {
                self.handleSort(parseInt(key));
            }
        });
        this.table.render();
        this.enableHeaderDrag();

        if (this.state.sortColumn !== null) {
            this.table.setSort(String(this.state.sortColumn), this.state.sortDirection);
        }

        this.pager = new Pagination('#rawDataPagination', {
            pageSize: this.PAGE_SIZE,
            showInfo: true,
            padding: '0',
            margin: '0',
            border: 'none',
            onPageChange: function(page) {
                self.renderPage(page);
            }
        });

        this.renderPage(1);
    }

    renderPage(page) {
        if (!this.table) return;
        var source = this.state.filteredData || this.state.data;
        var start = (page - 1) * this.PAGE_SIZE;
        var end = Math.min(start + this.PAGE_SIZE, source.length);
        var rows = source.slice(start, end);
        var state = this.state;

        this.table.renderBody(rows, function(row, i) {
            var v;
            var parts = ['<tr><td style="text-align:center">' + (start + i + 1) + '</td>'];
            v = row[0];
            parts.push('<td>' + ((v === null || v === undefined) ? '' : esc(String(v))) + '</td>');
            for (var oi = 0; oi < state.columnOrder.length; oi++) {
                var idx = state.columnOrder[oi];
                v = row[idx];
                parts.push('<td>' + ((v === null || v === undefined) ? '' : esc(String(v))) + '</td>');
            }
            parts.push('</tr>');
            return parts.join('');
        });

        this.pager.render(source.length, page);

        if (this.state.hiddenColumns.size > 0) this.applyColumnVisibility();
    }

    // ── 정렬 ──────────────────────────────────────────────

    handleSort(colIndex) {
        if (this.state.sortColumn === colIndex) {
            if (this.state.sortDirection === 'asc') {
                this.state.sortDirection = 'desc';
            } else {
                this.state.sortColumn = null;
                this.state.sortDirection = null;
                this.state.data = this.state.originalData.slice();
                this.table.setSort(null, null);
                if (this.state.filteredData) this.applyFilter();
                this.renderPage(1);
                return;
            }
        } else {
            this.state.sortColumn = colIndex;
            this.state.sortDirection = 'asc';
        }

        var dir = this.state.sortDirection;
        this.state.data.sort(function(a, b) {
            var valA = a[colIndex], valB = b[colIndex];
            var aIsNull = (valA === null || valA === undefined || valA === '');
            var bIsNull = (valB === null || valB === undefined || valB === '');
            if (aIsNull && bIsNull) return 0;
            if (aIsNull) return 1;
            if (bIsNull) return -1;
            var numA = parseFloat(valA), numB = parseFloat(valB);
            if (!isNaN(numA) && !isNaN(numB)) return dir === 'asc' ? numA - numB : numB - numA;
            var strA = String(valA).toLowerCase(), strB = String(valB).toLowerCase();
            return dir === 'asc' ? strA.localeCompare(strB) : strB.localeCompare(strA);
        });

        this.table.setSort(String(colIndex), dir);
        if (this.state.filteredData) this.applyFilter();
        this.renderPage(1);
    }

    resetSort() {
        this.state.sortColumn = null;
        this.state.sortDirection = null;
        this.state.data = this.state.originalData.slice();
        if (this.table) this.table.setSort(null, null);
        if (this.state.filteredData) this.applyFilter();
        this.renderPage(1);
    }

    // ── 필터 ──────────────────────────────────────────────

    initFilterBar() {
        var self = this;

        var controls = typeof this.extraControls === 'function'
            ? this.extraControls(this.params)
            : this.extraControls.slice();

        controls.unshift({
            type: 'custom',
            html: '<span style="font-size: 16px; font-weight: 600; color: var(--page-color); white-space: nowrap; padding-right: 10px; margin-right: 2px; border-right: 2px solid var(--text-secondary);">' + esc(getSelectedDate()) + '</span>'
        });

        if (this.state.columns.length > 0) {
            controls.push({
                type: 'select',
                key: 'filterCol',
                label: '항목',
                width: 'auto',
                options: this.state.columns.map(function(col, i) {
                    return { value: String(i), label: col };
                })
            });
            controls.push({
                type: 'input',
                key: 'filterVal',
                label: '검색어',
                placeholder: '값 입력...',
                onEnter: function() { self.applyFilter(); self.renderPage(1); }
            });
        }

        this.filterBar = new FilterBar('#raw-data-filter-bar', {
            sticky: true,
            controls: controls,
            onSearch: controls.length > 0 ? function() { self.applyFilter(); self.renderPage(1); } : undefined,
            onReset: controls.length > 0 ? function() { self.clearFilter(); } : undefined,
            right: this.state.columns.length > 0 ? [
                { type: 'button', label: '컬럼 선택', style: 'outline', size: 'fb', onClick: function() { self.toggleColumnDropdown(); } },
                { type: 'button', label: '정렬 초기화', style: 'outline', size: 'fb', onClick: function() { self.resetSort(); } }
            ] : []
        }).render();
    }

    applyFilter() {
        if (!this.filterBar) return;
        var colIdx = parseInt(this.filterBar.getValue('filterCol'));
        var keyword = (this.filterBar.getValue('filterVal') || '').trim().toLowerCase();

        this.state.filteredData = this.state.data.filter(function(row) {
            var val = row[colIdx];
            if (!keyword) {
                return val === null || val === undefined || val === '';
            }
            if (val === null || val === undefined || val === '') return false;
            return String(val).toLowerCase().indexOf(keyword) !== -1;
        });

        var countEl = document.getElementById('rawDataCount');
        countEl.innerHTML = '총 <strong>' + this.state.filteredData.length + '</strong>건 (필터 적용)';

        this.renderPage(1);
    }

    clearFilter() {
        this.state.filteredData = null;

        var countEl = document.getElementById('rawDataCount');
        var total = this.state.data.length;
        countEl.innerHTML = '총 <strong>' + total + '</strong>건';

        this.renderPage(1);
    }

    // ── 컬럼 선택 / 순서 변경 ──────────────────────────────

    toggleColumnDropdown() {
        var self = this;
        var existing = document.getElementById('columnDropdown');
        if (existing) {
            existing.remove();
            document.removeEventListener('click', this._closeDropdownBound);
            return;
        }

        var btn = document.querySelector('#raw-data-filter-bar .fb-right .app-btn');
        if (!btn) return;

        var dropdown = document.createElement('div');
        dropdown.id = 'columnDropdown';
        dropdown.className = 'column-dropdown';
        dropdown.addEventListener('click', function(e) { e.stopPropagation(); });

        // 전체 선택/해제
        var actionsDiv = document.createElement('div');
        actionsDiv.className = 'column-dropdown-actions';
        var btnAll = document.createElement('button');
        btnAll.className = 'app-btn app-btn-sm app-btn-outline';
        btnAll.textContent = '전체 선택';
        btnAll.addEventListener('click', function() { self.setAllColumns(true); });
        var btnNone = document.createElement('button');
        btnNone.className = 'app-btn app-btn-sm app-btn-outline';
        btnNone.textContent = '전체 해제';
        btnNone.addEventListener('click', function() { self.setAllColumns(false); });
        actionsDiv.appendChild(btnAll);
        actionsDiv.appendChild(btnNone);
        dropdown.appendChild(actionsDiv);

        // 컬럼 목록
        var listDiv = document.createElement('div');
        listDiv.className = 'column-dropdown-list';

        for (var oi = 0; oi < this.state.columnOrder.length; oi++) {
            (function(colIdx) {
                var item = document.createElement('div');
                item.className = 'column-dropdown-item';
                item.dataset.colIdx = colIdx;

                var handle = document.createElement('span');
                handle.className = 'drag-handle';
                handle.draggable = true;
                handle.textContent = '⠿';

                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !self.state.hiddenColumns.has(colIdx);
                cb.addEventListener('change', function() {
                    self.toggleColumn(colIdx, this.checked);
                });

                var label = document.createElement('span');
                label.textContent = self.state.columns[colIdx];

                item.appendChild(handle);
                item.appendChild(cb);
                item.appendChild(label);
                listDiv.appendChild(item);
            })(this.state.columnOrder[oi]);
        }

        dropdown.appendChild(listDiv);
        btn.style.position = 'relative';
        btn.appendChild(dropdown);

        this._initDropdownDrag(listDiv);

        this._closeDropdownBound = function(e) {
            var dd = document.getElementById('columnDropdown');
            if (dd && !dd.contains(e.target)) {
                dd.remove();
                document.removeEventListener('click', self._closeDropdownBound);
            }
        };
        setTimeout(function() {
            document.addEventListener('click', self._closeDropdownBound);
        }, 0);
    }

    toggleColumn(colIndex, visible) {
        if (visible) {
            this.state.hiddenColumns.delete(colIndex);
        } else {
            this.state.hiddenColumns.add(colIndex);
        }
        this.applyColumnVisibility();
    }

    setAllColumns(visible) {
        this.state.hiddenColumns.clear();
        if (!visible) {
            for (var oi = 0; oi < this.state.columnOrder.length; oi++) {
                this.state.hiddenColumns.add(this.state.columnOrder[oi]);
            }
        }
        var checkboxes = document.querySelectorAll('#columnDropdown input[type="checkbox"]');
        checkboxes.forEach(function(cb) { cb.checked = visible; });
        this.applyColumnVisibility();
    }

    applyColumnVisibility() {
        var table = this.table ? this.table.getTable() : null;
        if (!table) return;

        var cols = table.querySelectorAll('colgroup col');
        var ths = table.querySelectorAll('thead th');

        for (var oi = 0; oi < this.state.columnOrder.length; oi++) {
            var colIdx = this.state.columnOrder[oi];
            var domIdx = oi + 2;
            var hidden = this.state.hiddenColumns.has(colIdx);
            if (cols[domIdx]) cols[domIdx].style.display = hidden ? 'none' : '';
            if (ths[domIdx]) ths[domIdx].style.display = hidden ? 'none' : '';
        }

        var rows = table.querySelectorAll('tbody tr');
        var state = this.state;
        rows.forEach(function(row) {
            var tds = row.querySelectorAll('td');
            for (var oi = 0; oi < state.columnOrder.length; oi++) {
                var colIdx = state.columnOrder[oi];
                var domIdx = oi + 2;
                if (tds[domIdx]) {
                    tds[domIdx].style.display = state.hiddenColumns.has(colIdx) ? 'none' : '';
                }
            }
        });
    }

    // ── 드래그 앤 드롭 ─────────────────────────────────────

    _initDropdownDrag(listEl) {
        var self = this;
        var items = listEl.querySelectorAll('.column-dropdown-item');

        items.forEach(function(item) {
            var handle = item.querySelector('.drag-handle');

            handle.addEventListener('dragstart', function(e) {
                self._dragItem = item;
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            });

            handle.addEventListener('dragend', function() {
                item.classList.remove('dragging');
                listEl.querySelectorAll('.drag-over').forEach(function(el) { el.classList.remove('drag-over'); });
                self._dragItem = null;
            });

            item.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (self._dragItem && self._dragItem !== item) {
                    listEl.querySelectorAll('.drag-over').forEach(function(el) { el.classList.remove('drag-over'); });
                    item.classList.add('drag-over');
                }
            });

            item.addEventListener('dragleave', function() {
                item.classList.remove('drag-over');
            });

            item.addEventListener('drop', function(e) {
                e.preventDefault();
                item.classList.remove('drag-over');
                if (!self._dragItem || self._dragItem === item) return;
                var fromIdx = parseInt(self._dragItem.dataset.colIdx);
                var toIdx = parseInt(item.dataset.colIdx);
                self._reorderColumn(fromIdx, toIdx);
            });
        });
    }

    enableHeaderDrag() {
        var self = this;
        if (!this.table || !this.table.tableEl) return;
        var thead = this.table.tableEl.querySelector('thead');
        var ths = thead.querySelectorAll('th');
        var _headerDragSrc = null;

        for (var i = 2; i < ths.length; i++) {
            (function(th) {
                th.draggable = true;

                th.addEventListener('dragstart', function(e) {
                    _headerDragSrc = th;
                    th.classList.add('th-dragging');
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', th.dataset.sortKey);
                });

                th.addEventListener('dragend', function() {
                    th.classList.remove('th-dragging');
                    ths.forEach(function(t) { t.classList.remove('th-drag-left', 'th-drag-right'); });
                    _headerDragSrc = null;
                });

                th.addEventListener('dragover', function(e) {
                    if (!_headerDragSrc || _headerDragSrc === th) return;
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    var rect = th.getBoundingClientRect();
                    var midX = rect.left + rect.width / 2;
                    th.classList.remove('th-drag-left', 'th-drag-right');
                    th.classList.add(e.clientX < midX ? 'th-drag-left' : 'th-drag-right');
                });

                th.addEventListener('dragleave', function() {
                    th.classList.remove('th-drag-left', 'th-drag-right');
                });

                th.addEventListener('drop', function(e) {
                    e.preventDefault();
                    if (!_headerDragSrc || _headerDragSrc === th) return;

                    var fromColIdx = parseInt(_headerDragSrc.dataset.sortKey);
                    var toColIdx = parseInt(th.dataset.sortKey);
                    var rect = th.getBoundingClientRect();
                    var insertAfter = e.clientX >= rect.left + rect.width / 2;

                    var order = self.state.columnOrder;
                    var fromPos = order.indexOf(fromColIdx);
                    order.splice(fromPos, 1);
                    var toPos = order.indexOf(toColIdx);
                    if (insertAfter) toPos++;
                    order.splice(toPos, 0, fromColIdx);

                    var currentPage = self.pager ? self.pager.getCurrentPage() : 1;
                    self.renderTable();
                    self.renderPage(currentPage);

                    var dropdown = document.getElementById('columnDropdown');
                    if (dropdown) {
                        dropdown.remove();
                        document.removeEventListener('click', self._closeDropdownBound);
                        self.toggleColumnDropdown();
                    }
                });
            })(ths[i]);
        }
    }

    _reorderColumn(fromColIdx, toColIdx) {
        var order = this.state.columnOrder;
        var fromPos = order.indexOf(fromColIdx);
        var toPos = order.indexOf(toColIdx);
        if (fromPos === -1 || toPos === -1) return;

        order.splice(fromPos, 1);
        order.splice(toPos, 0, fromColIdx);

        this.renderTable();

        var existing = document.getElementById('columnDropdown');
        if (existing) {
            existing.remove();
            document.removeEventListener('click', this._closeDropdownBound);
            this.toggleColumnDropdown();
        }
    }
}
