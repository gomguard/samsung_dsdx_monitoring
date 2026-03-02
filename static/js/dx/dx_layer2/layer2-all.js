// Layer 2: 형식/NULL 검수 (DX 데이터 품질 모니터링)
let dxData = null;
let currentFocusTable = null;  // 현재 보고 있는 테이블 이름 (날짜 변경 시 유지용)

// ==================== 칼럼 설정 레지스트리 ====================
const DETAIL_COLUMNS = {
    // --- NULL 필드 상세 (flat) ---
    null_retail_fallback: [
        { key: 'null_fields', label: 'NULL 필드', width: 150 },
        { key: 'id', label: 'ID', width: 80 },
        { key: 'item', label: 'Item', width: 200 },
        { key: 'crawl_datetime', label: '수집일', width: 120 },
        { key: 'product_url', label: 'URL', width: 80 },
    ],
    null_youtube: [
        { key: 'null_fields', label: 'NULL 필드', width: 150 },
        { key: 'comment_id', label: 'COMMENT_ID', width: 180 },
        { key: 'video_id', label: 'VIDEO_ID', width: 150 },
        { key: 'crawl_datetime', label: '수집일', width: 120 },
    ],
    null_market: [
        { key: 'null_fields', label: 'NULL 필드', width: 80 },
        { key: 'id', label: 'ID', width: 80 },
        { key: 'item', label: 'Item', width: 200 },
        { key: 'crawl_datetime', label: '수집일', width: 120 },
    ],
    // --- 중복 검증 (rowspan) ---
    dup_youtube_logs: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'keyword', label: 'Keyword', width: 150 },
            { key: 'category', label: 'Category', width: 100 },
            { key: 'reason', label: '중복사유', width: 180 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 80 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_youtube_comments: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'video_id', label: 'Video ID', width: 120 },
            { key: 'comment_id', label: 'Comment ID', width: 140 },
            { key: 'reason', label: '중복사유', width: 150 },
        ],
        detail: [
            { key: 'comment_text_display', label: '댓글 내용', width: 300 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_youtube_videos: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'video_id', label: 'Video ID', width: 120 },
            { key: 'keyword', label: 'Keyword', width: 100 },
            { key: 'reason', label: '중복사유', width: 180 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 80 },
            { key: 'title', label: '제목', width: 200 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_market_trend: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'keyword', label: 'Keyword', width: 150 },
            { key: 'reason', label: '중복사유', width: 180 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 80 },
            { key: 'total_article_number', label: 'Article수', width: 100 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_market_product: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'batch_id', label: 'Batch ID', width: 100 },
            { key: 'samsung_series_name', label: 'Samsung Series', width: 150 },
            { key: 'comp_brand', label: 'Comp Brand', width: 100 },
            { key: 'comp_series_name', label: 'Comp Series', width: 150 },
            { key: 'reason', label: '중복사유', width: 150 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 60 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_market_event: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'batch_id', label: 'Batch ID', width: 100 },
            { key: 'comp_brand', label: 'Comp Brand', width: 100 },
            { key: 'comp_sku_name', label: 'Comp SKU', width: 150 },
            { key: 'reason', label: '중복사유', width: 150 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 60 },
            { key: 'created_at', label: '수집시각', width: 140 },
        ]
    },
    dup_default: {
        group: [
            { key: '_no', label: 'No', width: 50, align: 'center' },
            { key: 'item', label: 'Item', width: 150 },
            { key: 'period', label: '시간대', width: 100 },
            { key: 'reason', label: '중복사유', width: 150 },
        ],
        detail: [
            { key: 'id', label: 'ID', width: 80 },
            { key: 'page_type', label: 'Page Type', width: 100 },
            { key: 'crawl_datetime', label: '수집시각', width: 140 },
            { key: '_rank', label: 'Rank', width: 80 },
            { key: 'product_url', label: 'URL', width: 80 },
        ]
    },
};

// ==================== 상세 뷰 공통 함수 ====================
// 상세 뷰 상태
var detailViewState = {
    table: null,
    filterBar: null,
    pager: null,
    allData: [],
    filteredData: null,
    columns: [],
    type: null,
    tableParam: null,
    sortColumns: [],
    originalData: null
};

function getColumnConfig(type, tableParam) {
    if (type === 'duplicate') {
        var key = 'dup_' + tableParam;
        return DETAIL_COLUMNS[key] || DETAIL_COLUMNS.dup_default;
    }
    // null
    if (tableParam === 'youtube') return DETAIL_COLUMNS.null_youtube;
    if (tableParam.startsWith('market_')) return DETAIL_COLUMNS.null_market;
    return DETAIL_COLUMNS.null_retail_fallback;
}

function getAllColumns(config) {
    if (Array.isArray(config)) return config;
    var cols = [];
    if (config.group) cols = cols.concat(config.group);
    if (config.detail) cols = cols.concat(config.detail);
    if (config.trailing) cols = cols.concat(config.trailing);
    return cols;
}

function flattenRecords(type, records, tableParam) {
    var flat = [];
    var groupNum = 0;
    records.forEach(function(record) {
        var children;
        if (type === 'duplicate') {
            children = record.records || [];
            if (children.length === 0) return;
        } else {
            flat.push(record);
            return;
        }
        groupNum++;
        children.forEach(function(child, childIdx) {
            flat.push(Object.assign({}, child, {
                _parent: record,
                _isGroupFirst: childIdx === 0,
                _isGroupLast: childIdx === children.length - 1,
                _groupSize: children.length,
                _groupNumber: groupNum
            }));
        });
    });
    return flat;
}

function _editableAttr(row, key) {
    if (!isInlineMode()) return '';
    if (!detailViewState.editableCols || !detailViewState.editableCols.has(key)) return '';
    var rowId = row.id || (row._parent && row._parent.id);
    if (!rowId) return '';
    // 다일치 조회 시 조회 날짜 데이터만 수정 가능
    if ((modalState.days || 1) > 1 && detailViewState.crawlDate) {
        var dateCol = (modalState.nullFieldsData && modalState.nullFieldsData.date_column) || 'crawl_datetime';
        var recDate = (row[dateCol] || '').substring(0, 10);
        if (recDate !== detailViewState.crawlDate) return '';
    }
    return ' data-editable="true" data-row-id="' + rowId + '" data-col="' + esc(key) + '"';
}

function getCellHtml(row, col, tableParam) {
    var key = col.key;
    var val;

    // 특수 키 처리
    if (key === '_no') {
        return '<td' + (col.align ? ' style="text-align:' + col.align + ';font-weight:500;"' : '') + '>' + (row._groupNumber || '') + '</td>';
    }
    if (key === '_identifier') {
        val = row._parent ? (row._parent.keyword || row._parent.video_id || row._parent.comment_type || '-') : '-';
        return '<td>' + esc(String(val)) + '</td>';
    }
    if (key === '_rank') {
        val = row.rank !== undefined ? (row.rank || '-') : (row.main_rank || row.bsr_rank || '-');
        return '<td>' + esc(String(val)) + '</td>';
    }

    // _parent에서 값 가져오기 (group 칼럼)
    val = row[key];
    if (val === undefined && row._parent) val = row._parent[key];

    // product_url → 링크 아이콘 + URL 텍스트
    if (key === 'product_url') {
        if (!val) return '<td>-</td>';
        return '<td data-copy-text="' + esc(val) + '" title="' + esc(val) + '">'
            + '<a href="' + esc(val) + '" target="_blank" onclick="event.stopPropagation();" style="color:#2563eb;margin-right:6px;vertical-align:middle;cursor:pointer;">'
            + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
            + '</a>'
            + esc(val)
            + '</td>';
    }

    // null_fields → 배열 join + 하이라이트
    if (key === 'null_fields') {
        var nf = row.null_fields;
        var text = (Array.isArray(nf) ? nf.join(', ') : nf) || '-';
        return '<td class="null-value">' + esc(text) + '</td>';
    }

    // reason 스타일
    if (key === 'reason') {
        return '<td style="color:#dc2626;font-size:12px;">' + esc(String(val || '-')) + '</td>';
    }

    // comment_text_display → word-break
    if (key === 'comment_text_display') {
        return '<td style="white-space:normal;word-break:break-word;">' + esc(String(val || '-')) + '</td>';
    }

    // NULL 필드 하이라이트 (해당 필드가 record의 null_fields에 포함된 경우)
    if (row.null_fields && Array.isArray(row.null_fields) && row.null_fields.includes(key)) {
        var rowId2 = row.id || (row._parent && row._parent.id);
        var nrKey = rowId2 + '_' + key;
        var nr = detailViewState.normalReviews && detailViewState.normalReviews[nrKey];
        if (nr) {
            // 정상 처리된 셀: 회색 + 툴팁
            var nrTip = '정상 처리됨';
            if (nr.reason) nrTip += ' | 이유: ' + nr.reason;
            if (nr.memo) nrTip += ' | 메모: ' + nr.memo;
            if (nr.created_id) nrTip += ' | ' + nr.created_id;
            if (nr.created_at) nrTip += ' (' + nr.created_at + ')';
            return '<td class="cell-normal" data-normal-key="' + esc(nrKey) + '" data-row-id="' + rowId2 + '" data-col="' + esc(key) + '" title="' + esc(nrTip) + '">' + esc(String(val || 'NULL')) + ' <span class="normal-badge">정상</span></td>';
        }
        var editAttr2 = _editableAttr(row, key);
        return '<td class="null-value"' + editAttr2 + ' title="' + esc(String(val || 'NULL')) + '">' + esc(String(val || 'NULL')) + '</td>';
    }

    // 형식 오류 필드 하이라이트 (error_fields에 포함된 경우)
    if (row.error_fields && Array.isArray(row.error_fields) && row.error_fields.includes(key)) {
        var rowId3 = row.id || (row._parent && row._parent.id);
        var nrKey3 = rowId3 + '_' + key;
        var nr3 = detailViewState.normalReviews && detailViewState.normalReviews[nrKey3];
        if (nr3) {
            var nrTip3 = '정상 처리됨';
            if (nr3.reason) nrTip3 += ' | 이유: ' + nr3.reason;
            if (nr3.memo) nrTip3 += ' | 메모: ' + nr3.memo;
            if (nr3.created_id) nrTip3 += ' | ' + nr3.created_id;
            if (nr3.created_at) nrTip3 += ' (' + nr3.created_at + ')';
            return '<td class="cell-normal" data-normal-key="' + esc(nrKey3) + '" data-row-id="' + rowId3 + '" data-col="' + esc(key) + '" title="' + esc(nrTip3) + '">' + esc(String(val || '-')) + ' <span class="normal-badge">정상</span></td>';
        }
        var errDetail = row.error_details && row.error_details[key];
        var errTip = errDetail ? (errDetail.rule + ': ' + errDetail.reason) : '';
        var editAttr3 = _editableAttr(row, key);
        return '<td class="null-value"' + editAttr3 + ' title="' + esc(errTip) + '">' + esc(String(val || '-')) + '</td>';
    }

    var editAttr = _editableAttr(row, key);
    if (val === null || val === undefined || val === '') return '<td' + editAttr + '>-</td>';
    return '<td' + editAttr + ' title="' + esc(String(val)) + '">' + esc(String(val)) + '</td>';
}

function buildDetailContainerHtml(options) {
    var html = '<div class="detail-view-wrapper">';
    if (options.itemQueryHtml) {
        html += '<div id="detail-item-query">' + options.itemQueryHtml + '</div>';
    }
    html += '<div id="detail-filter-bar"></div>';
    html += '<div id="detail-action-bar"></div>';
    html += '<div id="detail-table-area"></div>';
    html += '<div id="detail-pagination"></div>';
    html += '</div>';
    return html;
}

function renderDetailWithTable(options) {
    var config = options.config;
    var data = options.data;
    var tableParam = options.tableParam || '';
    var type = options.type || 'null';
    var selectCols = options.selectCols || null;
    var editableCols = options.editableCols || [];
    var actualTable = options.actualTable || '';
    var crawlDate = options.crawlDate || '';
    var normalReviews = options.normalReviews || {};
    var isRowspan = !Array.isArray(config);
    var defaultCols = getAllColumns(config);

    detailViewState.type = type;
    detailViewState.tableParam = tableParam;
    detailViewState.editableCols = new Set(editableCols);
    detailViewState.normalReviews = normalReviews;
    detailViewState.actualTable = actualTable;
    detailViewState.crawlDate = crawlDate;

    // flat 데이터 생성
    var flatData;
    if (isRowspan) {
        flatData = flattenRecords(type, data, tableParam);
    } else {
        flatData = data;
    }
    detailViewState.allData = flatData;
    detailViewState.originalData = flatData.slice();
    detailViewState.filteredData = null;
    detailViewState.sortColumns = [];

    // 전체 컬럼 목록 구성
    var defaultKeySet = {};
    defaultCols.forEach(function(c) { defaultKeySet[c.key] = c; });

    var allColumns = [];
    var defaultVisibleKeys = [];

    // 기본 표시 컬럼 키 수집
    defaultCols.forEach(function(c) { defaultVisibleKeys.push(c.key); });

    if (isRowspan) {
        // rowspan 모드(중복 검증): group + detail 원래 순서 유지 (헤더와 데이터 셀 순서 일치 필수)
        defaultCols.forEach(function(c) { allColumns.push(c); });
    } else {
        // flat 모드: id → 디폴트 컬럼 순서 → 나머지 asc 정렬
        // 1) id를 맨 앞에
        if (defaultKeySet['id']) {
            allColumns.push(defaultKeySet['id']);
        }

        // 2) 나머지 디폴트 컬럼 (id, null_fields 제외) 정해진 순서대로
        defaultCols.forEach(function(c) {
            if (c.key === 'id' || c.key === 'null_fields') return;
            allColumns.push(c);
        });
    }

    // selectCols(백엔드)에 있지만 defaultCols에 없는 추가 컬럼 → asc 정렬
    if (selectCols && selectCols.length > 0) {
        var extraCols = [];
        selectCols.forEach(function(key) {
            if (key === 'null_fields' || key === '_no') return;
            if (defaultKeySet[key]) return;
            extraCols.push({
                key: key,
                label: key,
                width: 120
            });
        });
        extraCols.sort(function(a, b) { return a.key.localeCompare(b.key); });
        extraCols.forEach(function(c) { allColumns.push(c); });
    }

    // FilterBar (섹션 페이지에서만 표시, 대시보드 모달에서는 숨김)
    if (isInlineMode()) {
        var visibleKeys = defaultVisibleKeys.filter(function(k) { return k !== 'null_fields'; });
        var filterCols = visibleKeys.map(function(key) {
            var col = defaultKeySet[key];
            return { value: key, label: col ? col.label : key };
        });
        var fbOptions = {
            sticky: false,
            padding: '8px 12px',
            controls: [
                { type: 'select', key: 'filterCol', label: '항목', width: 'auto', options: filterCols },
                { type: 'input', key: 'filterVal', placeholder: '검색어 입력...', onEnter: function() { applyDetailFilter(); } }
            ],
            onSearch: function() { applyDetailFilter(); },
            onReset: function() { clearDetailFilter(); },
            columnSelector: {
                columns: allColumns,
                fixed: ['id'],
                defaultVisible: defaultVisibleKeys,
                onUpdate: function() { _rebuildDetailTable(); }
            }
        };
        fbOptions.right = [
            { type: 'button', label: '정렬 초기화', style: 'outline', size: 'fb', onClick: function() { resetDetailSort(); } }
        ];
        detailViewState.filterBar = new FilterBar('#detail-filter-bar', fbOptions).render();
        detailViewState.columns = detailViewState.filterBar.getVisibleColumns();
    } else {
        detailViewState.filterBar = null;
        detailViewState.columns = defaultCols;
    }

    // CommonTable 생성
    _buildDetailTable();

    // 중복 검증: 액션 버튼바
    if (isRowspan && type === 'duplicate') {
        _renderDupActionBar();
    }

    // Pagination
    var pageSize = 15;
    detailViewState.pager = new Pagination('#detail-pagination', {
        pageSize: pageSize,
        showInfo: true,
        padding: '0',
        margin: '0',
        border: 'none',
        onPageChange: function(page) {
            detailRenderPage(page);
        }
    });

    // 첫 페이지 렌더
    detailRenderPage(1);
}

// 컬럼 선택 변경 시 테이블 재생성
function _rebuildDetailTable() {
    if (!detailViewState.filterBar) return;
    detailViewState.columns = detailViewState.filterBar.getVisibleColumns();
    _buildDetailTable();

    // FilterBar select 옵션 갱신 (현재 visible 컬럼만)
    var sel = document.getElementById('filterCol');
    if (sel) {
        sel.innerHTML = '';
        detailViewState.columns.forEach(function(c) {
            if (c.key === 'null_fields') return;
            var opt = document.createElement('option');
            opt.value = c.key;
            opt.textContent = c.label;
            sel.appendChild(opt);
        });
    }

    var currentPage = detailViewState.pager ? detailViewState.pager.getCurrentPage() : 1;
    detailRenderPage(currentPage);
}

function _buildDetailTable() {
    var visibleCols = detailViewState.columns;
    var config = getColumnConfig(detailViewState.type, detailViewState.tableParam);
    var isRowspan = !Array.isArray(config);
    // No 컬럼을 항상 맨 앞에 추가 (컬럼 선택과 무관)
    var isDuplicate = detailViewState.type === 'duplicate';
    var ctColumns = [];
    if (isDuplicate) {
        ctColumns.push({ key: '_chk', label: '', width: 40, sortable: false, align: 'center' });
    }
    ctColumns.push({ key: '_no', label: 'No', width: 50, sortable: false, align: 'center' });
    visibleCols.forEach(function(col) {
        if (col.key === '_no') return;
        ctColumns.push({ key: col.key, label: col.label, width: col.width, sortable: !isRowspan, align: col.align });
    });
    document.getElementById('detail-table-area').innerHTML = '';
    detailViewState.table = new CommonTable('#detail-table-area', {
        variant: 'detail',
        columns: ctColumns,
        vlines: true,
        rounded: true,
        showTotalCount: true,
        padding: '6px 12px',
        reorder: true,
        fixedColumns: ['_no'],
        multiSort: !isRowspan,
        onSort: !isRowspan ? function(sortCols) { handleDetailSort(sortCols); } : undefined,
        onReorder: function(newColumns) {
            // No 컬럼 제외한 순서로 detailViewState.columns 갱신
            var cols = [];
            newColumns.forEach(function(c) {
                if (c.key === '_no') return;
                cols.push(c);
            });
            detailViewState.columns = cols;
            // FilterBar 컬럼 선택 드롭다운 순서 동기화
            if (detailViewState.filterBar && detailViewState.filterBar.reorderColumns) {
                detailViewState.filterBar.reorderColumns(cols.map(function(c) { return c.key; }));
            }
            // 항목 드롭다운 갱신
            var sel = document.getElementById('filterCol');
            if (sel) {
                sel.innerHTML = '';
                cols.forEach(function(c) {
                    if (c.key === 'null_fields') return;
                    var opt = document.createElement('option');
                    opt.value = c.key;
                    opt.textContent = c.label;
                    sel.appendChild(opt);
                });
            }
        }
    });
    detailViewState.table.render();
    if (isDuplicate) _injectDupCheckboxHeader();

    // 정렬 상태 복원
    if (!isRowspan && detailViewState.sortColumns.length > 0) {
        detailViewState.table.setSortColumns(detailViewState.sortColumns.map(function(s) {
            return { key: s.key, order: s.direction };
        }));
    }

    // 인라인 편집 (섹션 페이지, editable 셀만)
    // - 클릭: 셀 선택 (Ctrl+V 붙여넣기 가능)
    // - 더블클릭: 직접 입력 모드
    if (isInlineMode() && detailViewState.editableCols && detailViewState.editableCols.size > 0) {
        detailViewState.pendingEdits = {};
        detailViewState.selectedCell = null;

        var tableEl = detailViewState.table.getTable();

        // 클릭: 셀 선택 (editable 셀) 또는 null/normal 셀 액션 바
        tableEl.addEventListener('click', function(e) {
            var td = e.target.closest('td[data-editable]');
            var nullTd = !td ? e.target.closest('td.null-value, td.cell-normal') : null;
            var prev = tableEl.querySelector('.cell-selected');
            if (prev) prev.classList.remove('cell-selected');
            _hideNullReviewBar();
            if (td) {
                td.classList.add('cell-selected');
                detailViewState.selectedCell = td;
                // null-value이면서 아직 수정하지 않은 셀만 정상 처리 바 표시
                if (td.classList.contains('null-value') && !td.classList.contains('cell-pending')) {
                    _showNullReviewBar(td, 'normal');
                }
            } else if (nullTd) {
                detailViewState.selectedCell = null;
                if (nullTd.classList.contains('cell-normal')) {
                    _showNullReviewBar(nullTd, 'revert');
                }
            } else {
                detailViewState.selectedCell = null;
            }
        });

        // 테이블 외부 클릭 시 선택 해제
        document.addEventListener('click', function(e) {
            if (!e.target.closest('#detail-table-area table') && !e.target.closest('#null-review-bar')) {
                var sel = tableEl.querySelector('.cell-selected');
                if (sel) sel.classList.remove('cell-selected');
                detailViewState.selectedCell = null;
                _hideNullReviewBar();
            }
        });

        // Ctrl+V 붙여넣기
        document.addEventListener('paste', function(e) {
            var td = detailViewState.selectedCell;
            if (!td || !td.dataset.editable || document.querySelector('.cell-edit-overlay')) return;
            e.preventDefault();
            var pastedText = (e.clipboardData || window.clipboardData).getData('text').trim();
            _applyEdit(td, pastedText);
        });

        // 더블클릭: 직접 입력 모드
        tableEl.addEventListener('dblclick', function(e) {
            var td = e.target.closest('td[data-editable]');
            if (!td || document.querySelector('.cell-edit-overlay')) return;

            e.preventDefault();
            e.stopPropagation();

            var oldText = td.textContent.trim();
            if (oldText === '-') oldText = '';

            var rect = td.getBoundingClientRect();
            var input = document.createElement('input');
            input.type = 'text';
            input.className = 'cell-edit-overlay';
            input.value = oldText;
            input.style.cssText = 'position:fixed;z-index:9999;'
                + 'left:' + rect.left + 'px;top:' + rect.top + 'px;'
                + 'width:' + rect.width + 'px;height:' + rect.height + 'px;';
            document.body.appendChild(input);
            setTimeout(function() { input.focus(); input.select(); }, 0);

            var committed = false;
            function commit() {
                if (committed) return;
                committed = true;
                var newVal = input.value.trim();
                input.remove();
                if (newVal === oldText) return;
                _applyEdit(td, newVal);
            }

            input.addEventListener('keydown', function(ev) {
                if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
                if (ev.key === 'Escape') { committed = true; input.remove(); }
            });
            input.addEventListener('blur', commit);
        });
    }
}

function _applyEdit(td, newVal) {
    var rowId = td.dataset.rowId;
    var colName = td.dataset.col;
    var oldText = td.textContent.trim();
    if (oldText === '-') oldText = '';
    if (newVal === oldText) return;
    _hideNullReviewBar();
    td.textContent = newVal || '-';
    td.classList.remove('null-value');
    td.classList.add('cell-pending');
    var editKey = rowId + '_' + colName;
    var prev = detailViewState.pendingEdits[editKey];
    detailViewState.pendingEdits[editKey] = {
        table_name: detailViewState.actualTable,
        row_id: parseInt(rowId),
        column_name: colName,
        new_value: newVal,
        _oldValue: prev ? prev._oldValue : oldText,
        crawl_date: detailViewState.crawlDate || '',
        td: td
    };
    _updateDetailData(rowId, colName, newVal);
    _updateSaveButton();
}

function _updateSaveButton() {
    var countEl = document.querySelector('#detail-table-area .ct-count');
    if (!countEl) return;
    var wrap = document.getElementById('detail-edit-actions');
    var count = Object.keys(detailViewState.pendingEdits || {}).length;
    if (count === 0) {
        if (wrap) wrap.remove();
        return;
    }
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.id = 'detail-edit-actions';
        wrap.className = 'detail-edit-actions';
        var infoSpan = document.createElement('span');
        infoSpan.id = 'edit-actions-info';
        infoSpan.className = 'edit-actions-info';
        var btnGroup = document.createElement('div');
        btnGroup.style.cssText = 'display:flex;gap:8px;';
        var btnCancel = document.createElement('button');
        btnCancel.className = 'btn-cancel-edits';
        btnCancel.textContent = '취소';
        btnCancel.addEventListener('click', _cancelAllEdits);
        var btnSave = document.createElement('button');
        btnSave.id = 'btn-save-edits';
        btnSave.className = 'btn-save-edits';
        btnSave.addEventListener('click', _saveAllEdits);
        btnGroup.appendChild(btnCancel);
        btnGroup.appendChild(btnSave);
        wrap.appendChild(infoSpan);
        wrap.appendChild(btnGroup);
        var tableEl = document.querySelector('#detail-table-area table');
        if (tableEl) {
            tableEl.parentNode.insertBefore(wrap, tableEl);
        } else {
            countEl.parentNode.insertBefore(wrap, countEl);
        }
    }
    document.getElementById('edit-actions-info').textContent = count + '건 변경됨';
    document.getElementById('btn-save-edits').textContent = '저장';
}

function _cancelAllEdits() {
    var edits = detailViewState.pendingEdits;
    if (!edits) return;
    Object.keys(edits).forEach(function(k) {
        var edit = edits[k];
        if (edit.td) {
            edit.td.classList.remove('cell-pending');
            // 원래 값 복원
            var origVal = edit._oldValue;
            edit.td.textContent = (origVal === null || origVal === undefined || origVal === '') ? '-' : origVal;
            _updateDetailData(edit.row_id, edit.column_name, origVal);
        }
    });
    detailViewState.pendingEdits = {};
    _updateSaveButton();
}

function _saveAllEdits() {
    var edits = detailViewState.pendingEdits;
    if (!edits) return;
    var keys = Object.keys(edits);
    if (keys.length === 0) return;

    _showMemoDialog(function(memo) {
        _doSaveEdits(memo);
    }, '수정 메모', '수정 사유 입력 (선택사항)');
}

function _doSaveEdits(memo) {
    var edits = detailViewState.pendingEdits;
    if (!edits) return;
    var keys = Object.keys(edits);
    if (keys.length === 0) return;

    var btn = document.getElementById('btn-save-edits');
    if (btn) { btn.disabled = true; btn.textContent = '저장 중...'; }

    var requests = keys.map(function(k) {
        var edit = edits[k];
        return fetch('/dx/layer2/api/update-cell/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                table_name: edit.table_name,
                row_id: edit.row_id,
                column_name: edit.column_name,
                new_value: edit.new_value,
                crawl_date: edit.crawl_date,
                correction_type: detailViewState.type || 'null',
                memo: memo || ''
            })
        }).then(function(r) { return r.json(); }).then(function(res) {
            return { key: k, success: res.success, error: res.error };
        }).catch(function() {
            return { key: k, success: false, error: '네트워크 오류' };
        });
    });

    Promise.all(requests).then(function(results) {
        var successCount = 0;
        var failCount = 0;
        results.forEach(function(r) {
            var edit = edits[r.key];
            if (r.success) {
                successCount++;
                if (edit.td) {
                    edit.td.classList.remove('cell-pending');
                    edit.td.classList.add('cell-saved');
                    setTimeout(function() { edit.td.classList.remove('cell-saved'); }, 1500);
                }
                delete edits[r.key];
            } else {
                failCount++;
            }
        });
        if (successCount > 0) showToast(successCount + '건 저장 완료', 'success');
        if (failCount > 0) showToast(failCount + '건 저장 실패', 'error');
        _updateSaveButton();
    });
}

function _updateDetailData(rowId, colName, newVal) {
    var id = parseInt(rowId);
    if (detailViewState.allData) {
        detailViewState.allData.forEach(function(row) {
            if (row.id === id || (row._parent && row._parent.id === id)) {
                var target = row[colName] !== undefined ? row : (row._parent || row);
                target[colName] = newVal === '' ? null : newVal;
            }
        });
    }
}

// ==================== NULL 정상 처리 ====================
function _showNullReviewBar(td, mode) {
    _hideNullReviewBar();
    var bar = document.createElement('div');
    bar.id = 'null-review-bar';
    bar.className = 'null-review-bar';
    var colName = td.dataset.col || '';
    var rowId = td.dataset.rowId || '';
    var errLabel = detailViewState.type === 'format' ? '형식 오류' : 'NULL 오류';
    var infoText = mode === 'revert'
        ? (colName + ' (ID: ' + rowId + ') — 정상 처리됨')
        : (colName + ' (ID: ' + rowId + ') — ' + errLabel);
    var info = document.createElement('span');
    info.className = 'null-review-info';
    info.textContent = infoText;
    var btn = document.createElement('button');
    btn.className = mode === 'revert' ? 'btn-null-revert' : 'btn-null-normal';
    btn.textContent = mode === 'revert' ? '정상 취소' : '정상 처리';
    btn.addEventListener('click', function() {
        if (mode === 'revert') {
            _submitNullReview(td, 'reverted', '', '');
        } else {
            _showReviewDialog(function(reason, memo) {
                _submitNullReview(td, 'normal', memo, reason);
            });
        }
    });
    bar.appendChild(info);
    bar.appendChild(btn);
    var tableEl = document.querySelector('#detail-table-area table');
    if (tableEl) tableEl.parentNode.insertBefore(bar, tableEl);
}

function _hideNullReviewBar() {
    var bar = document.getElementById('null-review-bar');
    if (bar) bar.remove();
}

// 정상 처리 다이얼로그 (이유 선택 필수 + 메모 선택)
function _showReviewDialog(callback) {
    var overlay = document.createElement('div');
    overlay.className = 'memo-dialog-overlay';
    overlay.innerHTML = '<div class="memo-dialog">'
        + '<div class="memo-dialog-title">정상 처리</div>'
        + '<div class="memo-dialog-field"><label class="memo-dialog-label">이유 <span style="color:#dc2626;">*</span></label>'
        + '<select class="memo-dialog-select" id="review-reason-select"><option value="">불러오는 중...</option></select></div>'
        + '<div class="memo-dialog-field"><label class="memo-dialog-label">메모</label>'
        + '<textarea class="memo-dialog-input" placeholder="메모 입력 (선택사항)" rows="3"></textarea></div>'
        + '<div class="memo-dialog-buttons">'
        + '<button class="memo-dialog-cancel">취소</button>'
        + '<button class="memo-dialog-confirm">확인</button>'
        + '</div></div>';
    document.body.appendChild(overlay);
    setTimeout(function() { overlay.classList.add('show'); }, 10);

    // 이유 목록 조회
    var checkType = (detailViewState.type === 'null') ? 'null_check' : (detailViewState.type + '_check');
    fetch('/dx/layer2/api/review-reasons/?check_type=' + encodeURIComponent(checkType))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            var sel = document.getElementById('review-reason-select');
            if (!sel) return;
            var reasons = res.reasons || [];
            if (reasons.length === 0) {
                // 사유 목록이 비어있으면 select 영역 숨김 (메모만 사용)
                var reasonField = sel.closest('.memo-dialog-field');
                if (reasonField) reasonField.style.display = 'none';
            } else {
                sel.innerHTML = '<option value="">-- 선택 --</option>';
                reasons.forEach(function(r) {
                    var opt = document.createElement('option');
                    opt.value = r.text;
                    opt.textContent = r.text;
                    sel.appendChild(opt);
                });
            }
        })
        .catch(function() {
            var sel = document.getElementById('review-reason-select');
            if (sel) sel.innerHTML = '<option value="">로딩 실패</option>';
        });

    var textarea = overlay.querySelector('.memo-dialog-input');
    function closeDlg() {
        overlay.classList.remove('show');
        setTimeout(function() { overlay.remove(); }, 200);
    }
    overlay.querySelector('.memo-dialog-cancel').addEventListener('click', closeDlg);
    overlay.querySelector('.memo-dialog-confirm').addEventListener('click', function() {
        var selEl = document.getElementById('review-reason-select');
        var reasonField = selEl ? selEl.closest('.memo-dialog-field') : null;
        var reasonHidden = reasonField && reasonField.style.display === 'none';
        var reason = reasonHidden ? '' : (selEl ? selEl.value : '');
        var memo = textarea.value.trim();
        if (!reasonHidden && !reason) { showToast('이유를 선택해주세요', 'error'); return; }
        closeDlg();
        callback(reason, memo);
    });
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeDlg();
    });
}

// 수정 저장용 메모 다이얼로그 (이유 없음, 메모 선택)
function _showMemoDialog(callback, title, placeholder) {
    var dlgTitle = title || '수정 메모';
    var dlgPlaceholder = placeholder || '메모 입력 (선택사항)';
    var overlay = document.createElement('div');
    overlay.className = 'memo-dialog-overlay';
    overlay.innerHTML = '<div class="memo-dialog">'
        + '<div class="memo-dialog-title">' + dlgTitle + '</div>'
        + '<textarea class="memo-dialog-input" placeholder="' + dlgPlaceholder + '" rows="3"></textarea>'
        + '<div class="memo-dialog-buttons">'
        + '<button class="memo-dialog-cancel">취소</button>'
        + '<button class="memo-dialog-confirm">확인</button>'
        + '</div></div>';
    document.body.appendChild(overlay);
    setTimeout(function() { overlay.classList.add('show'); }, 10);
    var textarea = overlay.querySelector('.memo-dialog-input');
    textarea.focus();
    function closeDlg() {
        overlay.classList.remove('show');
        setTimeout(function() { overlay.remove(); }, 200);
    }
    overlay.querySelector('.memo-dialog-cancel').addEventListener('click', closeDlg);
    overlay.querySelector('.memo-dialog-confirm').addEventListener('click', function() {
        var memo = textarea.value.trim();
        closeDlg();
        callback(memo);
    });
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeDlg();
    });
}

function _submitNullReview(td, status, memo, reason) {
    var rowId = td.dataset.rowId || (td.dataset.normalKey && td.dataset.normalKey.split('_')[0]);
    var colName = td.dataset.col || (td.dataset.normalKey && td.dataset.normalKey.split('_').slice(1).join('_'));
    if (!rowId || !colName) return;

    fetch('/dx/layer2/api/null-review/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({
            table_name: detailViewState.actualTable,
            record_id: parseInt(rowId),
            column_name: colName,
            status: status,
            memo: memo || '',
            reason: reason || '',
            crawl_date: detailViewState.crawlDate || '',
            correction_type: detailViewState.type === 'format' ? 'format' : 'null'
        })
    }).then(function(r) { return r.json(); })
    .then(function(res) {
        if (res.success) {
            _hideNullReviewBar();
            if (status === 'normal') {
                // 정상 처리 → normalReviews에 추가 + 셀 스타일 변경
                var nrKey = rowId + '_' + colName;
                if (!detailViewState.normalReviews) detailViewState.normalReviews = {};
                detailViewState.normalReviews[nrKey] = { memo: memo, reason: '', created_id: '', created_at: '' };
                td.className = 'cell-normal';
                td.dataset.normalKey = nrKey;
                td.removeAttribute('data-editable');
                var badge = td.querySelector('.normal-badge');
                if (!badge) {
                    var span = document.createElement('span');
                    span.className = 'normal-badge';
                    span.textContent = '정상';
                    td.appendChild(span);
                }
                var tip = '정상 처리됨';
                if (memo) tip += ' | 메모: ' + memo;
                td.title = tip;
                showToast('정상 처리 완료', 'success');
            } else {
                // 정상 취소 → normalReviews에서 제거 + 셀 스타일 복원
                var nrKey2 = rowId + '_' + colName;
                if (detailViewState.normalReviews) delete detailViewState.normalReviews[nrKey2];
                td.className = 'null-value';
                td.removeAttribute('data-normal-key');
                var badge2 = td.querySelector('.normal-badge');
                if (badge2) badge2.remove();
                td.title = td.textContent.trim();
                // editable 복원
                var fakeRow = { id: parseInt(rowId), null_fields: [colName] };
                if (detailViewState.type === 'format') fakeRow.error_fields = [colName];
                var editAttr = _editableAttr(fakeRow, colName);
                if (editAttr) {
                    td.setAttribute('data-editable', 'true');
                    td.setAttribute('data-row-id', rowId);
                    td.setAttribute('data-col', colName);
                }
                showToast('정상 처리 취소됨', 'success');
            }
        } else {
            showToast(res.error || '처리 실패', 'error');
        }
    }).catch(function() {
        showToast('네트워크 오류', 'error');
    });
}

function handleDetailSort(sortCols) {
    detailViewState.sortColumns = sortCols.map(function(s) {
        return { key: s.key, direction: s.order };
    });

    if (detailViewState.sortColumns.length === 0) {
        detailViewState.allData = detailViewState.originalData.slice();
    } else {
        var cols = detailViewState.sortColumns;
        detailViewState.allData.sort(function(a, b) {
            for (var i = 0; i < cols.length; i++) {
                var key = cols[i].key;
                var dir = cols[i].direction;
                var valA = a[key], valB = b[key];
                var aIsNull = (valA === null || valA === undefined || valA === '');
                var bIsNull = (valB === null || valB === undefined || valB === '');
                if (aIsNull && bIsNull) continue;
                if (aIsNull) return 1;
                if (bIsNull) return -1;
                var numA = parseFloat(valA), numB = parseFloat(valB);
                if (!isNaN(numA) && !isNaN(numB)) {
                    var diff = dir === 'asc' ? numA - numB : numB - numA;
                    if (diff !== 0) return diff;
                    continue;
                }
                var strA = String(valA).toLowerCase(), strB = String(valB).toLowerCase();
                var cmp = dir === 'asc' ? strA.localeCompare(strB) : strB.localeCompare(strA);
                if (cmp !== 0) return cmp;
            }
            return 0;
        });
    }

    if (detailViewState.filteredData) applyDetailFilter();
    detailRenderPage(1);
}

function resetDetailSort() {
    detailViewState.sortColumns = [];
    detailViewState.allData = detailViewState.originalData.slice();
    if (detailViewState.table) detailViewState.table.setSortColumns([]);
    if (detailViewState.filteredData) applyDetailFilter();
    detailRenderPage(1);
}

function detailRenderPage(page) {
    var source = detailViewState.filteredData || detailViewState.allData;
    var config = getColumnConfig(detailViewState.type, detailViewState.tableParam);
    var isRowspan = !Array.isArray(config);
    var tableParam = detailViewState.tableParam;
    var visibleCols = detailViewState.columns;
    var pageSize = detailViewState.pager ? detailViewState.pager.getPageSize() : 20;

    // rowspan인 경우 그룹 단위로 페이징
    var pageData, totalItems, startIdx;
    if (isRowspan) {
        var groups = [];
        var curGroup = [];
        source.forEach(function(row) {
            if (row._isGroupFirst && curGroup.length > 0) {
                groups.push(curGroup);
                curGroup = [];
            }
            curGroup.push(row);
        });
        if (curGroup.length > 0) groups.push(curGroup);

        totalItems = groups.length;
        var startGroup = (page - 1) * pageSize;
        var endGroup = Math.min(startGroup + pageSize, groups.length);
        pageData = [];
        startIdx = startGroup;
        for (var g = startGroup; g < endGroup; g++) {
            pageData = pageData.concat(groups[g]);
        }
    } else {
        totalItems = source.length;
        var start = (page - 1) * pageSize;
        startIdx = start;
        var end = Math.min(start + pageSize, source.length);
        pageData = source.slice(start, end);
    }

    // renderBody
    var rowNum = startIdx;
    var isDup = detailViewState.type === 'duplicate';
    detailViewState.table.renderBody(pageData, function(row) {
        if (isRowspan) {
            var tr = '<tr>';
            // 중복 검증: 체크박스 (매 행, rowspan 없음)
            if (isDup) {
                tr += '<td style="text-align:center"><input type="checkbox" class="dup-check" data-id="' + row.id + '"' +
                      (row._isGroupLast ? ' data-group-last="1"' : '') + '></td>';
            }
            if (row._isGroupFirst) {
                config.group.forEach(function(col) {
                    tr += '<td rowspan="' + row._groupSize + '"' +
                          (col.align ? ' style="text-align:' + col.align + ';font-weight:500;"' : '') + '>' +
                          getCellHtml(row, col, tableParam).replace(/^<td[^>]*>/, '').replace(/<\/td>$/, '') + '</td>';
                });
            }
            config.detail.forEach(function(col) {
                tr += getCellHtml(row, col, tableParam);
            });
            if (row._isGroupFirst && config.trailing) {
                config.trailing.forEach(function(col) {
                    tr += '<td rowspan="' + row._groupSize + '">' +
                          getCellHtml(row, col, tableParam).replace(/^<td[^>]*>/, '').replace(/<\/td>$/, '') + '</td>';
                });
            }
            return tr + '</tr>';
        } else {
            rowNum++;
            var tr = '<tr>';
            // No 컬럼 (항상 맨 앞)
            tr += '<td style="text-align:center;font-weight:500;">' + rowNum + '</td>';
            visibleCols.forEach(function(col) {
                tr += getCellHtml(row, col, tableParam);
            });
            return tr + '</tr>';
        }
    });

    // Pagination
    detailViewState.pager.render(totalItems, page);

    // 건수 (CommonTable의 ct-count를 전체 건수로 덮어쓰기)
    var countEl = document.querySelector('#detail-table-area .ct-count');
    if (countEl) {
        var suffix = detailViewState.filteredData ? ' (필터 적용)' : '';
        countEl.innerHTML = '총 <strong>' + totalItems.toLocaleString() + '</strong>건' + suffix;
    }
}

function applyDetailFilter() {
    if (!detailViewState.filterBar) return;
    var colKey = detailViewState.filterBar.getValue('filterCol');
    var keyword = (detailViewState.filterBar.getValue('filterVal') || '').trim().toLowerCase();
    var allCols = detailViewState.columns;
    var config = getColumnConfig(detailViewState.type, detailViewState.tableParam);
    var isRowspan = !Array.isArray(config);
    var col = null;
    for (var i = 0; i < allCols.length; i++) {
        if (allCols[i].key === colKey) { col = allCols[i]; break; }
    }
    if (!col) return;

    var source = detailViewState.allData;
    if (!keyword) {
        detailViewState.filteredData = null;
    } else if (isRowspan) {
        // 그룹 단위 필터: 그룹 내 어느 행이든 매칭 시 전체 그룹 포함
        var groups = [];
        var curGroup = [];
        source.forEach(function(row) {
            if (row._isGroupFirst && curGroup.length > 0) {
                groups.push(curGroup);
                curGroup = [];
            }
            curGroup.push(row);
        });
        if (curGroup.length > 0) groups.push(curGroup);

        var filtered = [];
        groups.forEach(function(group) {
            var match = group.some(function(row) {
                var val = row[col.key];
                if (val === undefined && row._parent) val = row._parent[col.key];
                if (col.key === '_no') val = String(row._groupNumber || '');
                if (col.key === '_identifier') val = row._parent ? (row._parent.keyword || row._parent.video_id || '') : '';
                if (col.key === '_rank') val = row.rank || row.main_rank || row.bsr_rank || '';
                if (col.key === 'null_fields' && Array.isArray(row.null_fields)) val = row.null_fields.join(', ');
                return val !== null && val !== undefined && String(val).toLowerCase().indexOf(keyword) !== -1;
            });
            if (match) filtered = filtered.concat(group);
        });
        detailViewState.filteredData = filtered;
    } else {
        detailViewState.filteredData = source.filter(function(row) {
            var val = row[col.key];
            if (col.key === 'null_fields' && Array.isArray(row.null_fields)) val = row.null_fields.join(', ');
            return val !== null && val !== undefined && String(val).toLowerCase().indexOf(keyword) !== -1;
        });
    }

    detailRenderPage(1);
}

function clearDetailFilter() {
    detailViewState.filteredData = null;
    detailRenderPage(1);
}


// ViewStack — 섹션 페이지에서 모달 대신 인라인 콘텐츠 교체
const ViewStack = {
    stack: [],
    getContainer() { return document.getElementById('dx-validation-container'); },
    push(html) {
        const c = this.getContainer();
        if (!c) return;
        this.stack.push({ html: c.innerHTML, scrollTop: window.scrollY });
        c.innerHTML = html;
        window.scrollTo(0, 0);
        this._updateBackBtn();
    },
    pop() {
        if (this.stack.length === 0) return false;
        const s = this.stack.pop();
        const c = this.getContainer();
        if (c) { c.innerHTML = s.html; window.scrollTo(0, s.scrollTop); }
        this._updateBackBtn();
        return true;
    },
    depth() { return this.stack.length; },
    _updateBackBtn() {
        var el = document.getElementById('viewstack-back-container');
        if (el) el.style.display = this.stack.length > 0 ? '' : 'none';
        var fb = document.getElementById('filter-bar-container');
        if (fb) fb.style.display = this.stack.length > 1 ? 'none' : '';
    }
};

function isInlineMode() {
    const s = (window.LAYER2 && window.LAYER2.section) || 'dashboard';
    return s !== 'dashboard';
}

function getDetailBody() {
    return document.getElementById('detail-body') || document.getElementById('modal-body');
}

function getDetailSubtitle() {
    return document.getElementById('detail-subtitle') || (function() {
        var body = AppModal.getBody('l2-detail');
        return body ? body.querySelector('#modal-subtitle') : null;
    })();
}

document.addEventListener('DOMContentLoaded', function() {
    initFilterBar();
    checkBackupStatus();
    fetchDXStats();
});

async function checkBackupStatus() {
    const date = getSelectedDate();
    if (!date) return;
    try {
        const res = await fetch(`/dx/layer1/api/backup-status/?date=${date}`);
        const data = await res.json();
        if (!data.success || data.pending_count === 0) return;

        if (!data.has_backup) {
            const goBackup = await showConfirm(`${date} 미백업 ${data.pending_count}건 (TV: ${data.tv_count}, HHP: ${data.hhp_count})\n백업 후 검수를 진행해주세요.`, 'warning', { okText: 'Layer 1 이동', cancelText: '계속 조회' });
            if (goBackup) window.location.href = '/dx/layer1/';
        } else {
            const goBackup = await showConfirm(`추가 수집 데이터 ${data.pending_count}건 미백업 (TV: ${data.tv_count}, HHP: ${data.hhp_count})\n백업 후 검수를 진행해주세요.`, 'warning', { okText: 'Layer 1 이동', cancelText: '계속 조회' });
            if (goBackup) window.location.href = '/dx/layer1/';
        }
    } catch (e) { /* 백업 상태 조회 실패 시 무시 */ }
}

// 로컬 날짜를 YYYY-MM-DD 형식으로 변환
function formatLocalDate(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function handleSearch() {
    checkBackupStatus();
    dxData = null;
    ViewStack.stack = [];
    ViewStack._updateBackBtn();
    document.getElementById('dx-validation-container').innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <p>데이터 로딩 중...</p>
        </div>`;
    fetchDXStats();
}


// ==================== DX ====================
function fetchDXStats() {
    const date = getSelectedDate();

    fetch(`/dx/layer2/api/stats/?date=${date}`)
        .then(response => response.json())
        .then(data => {
            dxData = data;
            renderDXSummary(data);
            renderDXValidationTypes(data);
            updateCurrentInfo(data.date);
        })
        .catch(error => {
            console.error('DX Error:', error);
            document.getElementById('dx-validation-container').innerHTML =
                '<div class="loading"><p style="color: var(--color-critical);">DX 데이터 로딩 실패</p></div>';
        });
}

function renderDXSummary(data) {
    const el = document.getElementById('dx-totalIssues');
    if (!el) return;

    const summary = data.summary;

    el.textContent = summary.total_issues.toLocaleString();
    el.className = `value ${summary.overall_status.toLowerCase()}`;

    document.getElementById('dx-nullIssues').textContent = summary.null_issues.toLocaleString();
    document.getElementById('dx-nullIssues').className = `value ${getStatusClass(summary.null_issues)}`;

    document.getElementById('dx-formatIssues').textContent = summary.format_issues.toLocaleString();
    document.getElementById('dx-formatIssues').className = `value ${getStatusClass(summary.format_issues)}`;

    document.getElementById('dx-duplicateIssues').textContent = summary.duplicate_issues.toLocaleString();
    document.getElementById('dx-duplicateIssues').className = `value ${getStatusClass(summary.duplicate_issues)}`;
}

function renderDXValidationTypes(data) {
    const container = document.getElementById('dx-validation-container');

    // 섹션별 필터링
    const section = (window.LAYER2 && window.LAYER2.section) || 'dashboard';
    const typeMap = { null_validation: 'null', format_validation: 'format', anomaly_validation: 'duplicate' };
    if (typeMap[section] && data.validation_types) {
        data.validation_types = data.validation_types.filter(v => v.type === typeMap[section]);
    }

    if (!data.validation_types || data.validation_types.length === 0) {
        container.innerHTML = '<div class="loading"><p>검증 데이터 없음</p></div>';
        return;
    }

    let html = '';

    if (isInlineMode()) {
        // 섹션 페이지: validation 헤더 없이 테이블 목록만 직접 표시
        // 테이블 클릭 → 인라인 상세 전환
        const vType = data.validation_types[0];
        if (vType && vType.tables) {
            vType.tables.forEach((table, tIdx) => {
                const issueCount = table.total_issues || 0;
                html += `
                    <div class="table-item clickable-table" onclick="showTableDetail(${tIdx})">
                        <div class="table-header">
                            <div class="table-info">
                                <span class="table-name">${table.table_name}</span>
                                <span style="font-size: 12px; color: var(--text-secondary);">
                                    (${(table.total_records || table.total_checked || 0).toLocaleString()}건 검사)
                                </span>
                            </div>
                            <div class="table-stats">
                                <span class="table-count ${table.status.toLowerCase()}">${issueCount.toLocaleString()}건</span>
                                <span class="status-badge ${table.status.toLowerCase()}">${table.status}</span>
                                <span class="toggle-icon">▶</span>
                            </div>
                        </div>
                    </div>
                `;
            });
        }
        // focus 결정: currentFocusTable > URL focus > 첫 번째 테이블
        var focusTarget = currentFocusTable;
        if (!focusTarget) {
            const focus = new URLSearchParams(window.location.search).get('focus');
            if (focus) {
                focusTarget = decodeURIComponent(focus);
            }
        }
        // focus 없으면 첫 번째 테이블
        if (!focusTarget && vType && vType.tables && vType.tables.length > 0) {
            focusTarget = vType.tables[0].table_name;
        }

        if (focusTarget && vType) {
            const idx = vType.tables.findIndex(t => t.table_name === focusTarget);
            if (idx >= 0) {
                // 목록 HTML은 ViewStack에만 저장 (뒤로가기용)
                ViewStack.stack = [{ html: html, scrollTop: 0 }];
                ViewStack._updateBackBtn();
                const table = vType.tables[idx];
                currentFocusTable = table.table_name;
                let detailHtml = `
                    <div class="inline-detail-view">
                        <div class="inline-detail-header">
                            <div>
                                <div class="inline-detail-title">${table.table_name}</div>
                                <div class="inline-detail-subtitle">${(table.total_records || table.total_checked || 0).toLocaleString()}건 검사 | ${table.total_issues}건 오류</div>
                            </div>
                        </div>
                        <div class="inline-detail-body">
                            ${renderDXTableDetail(vType, table)}
                        </div>
                    </div>`;
                container.innerHTML = detailHtml;
            } else {
                container.innerHTML = html;
            }
        } else {
            container.innerHTML = html;
        }
    } else {
        // 대시보드: 기존 validation-section + toggle 구조
        data.validation_types.forEach((vType, vIdx) => {
            html += `
                <div class="validation-section">
                    <div class="validation-header" onclick="toggleValidation(${vIdx})">
                        <div class="validation-title">
                            <span class="validation-icon">${vType.icon}</span>
                            <div>
                                <div class="validation-name">${vType.type_name}</div>
                                <div class="validation-name-en">${vType.type_name_en}</div>
                            </div>
                        </div>
                        <div class="validation-stats">
                            <span class="validation-count ${vType.status.toLowerCase()}">${vType.total_issues.toLocaleString()}건</span>
                            <span class="status-badge ${vType.status.toLowerCase()}">${vType.status}</span>
                            <span class="toggle-icon" id="toggle-dx-v-${vIdx}">▶</span>
                        </div>
                    </div>
                    <div class="tables-container" id="dx-tables-${vIdx}">
                        ${renderDXTables(vType, vIdx)}
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }
}

// 섹션 페이지: 테이블 클릭 → 리테일러 카드를 인라인으로 표시
function showTableDetail(tableIdx) {
    if (!dxData || !dxData.validation_types) return;
    const vType = dxData.validation_types[0];
    if (!vType || !vType.tables || !vType.tables[tableIdx]) return;
    const table = vType.tables[tableIdx];
    currentFocusTable = table.table_name;
    // URL에 focus 파라미터 반영 (새로고침 시 현재 메뉴 유지)
    const url = new URL(window.location);
    url.searchParams.set('focus', table.table_name);
    history.replaceState(null, '', url);

    let html = `
        <div class="inline-detail-view">
            <div class="inline-detail-header">
                <div>
                    <div class="inline-detail-title">${table.table_name}</div>
                    <div class="inline-detail-subtitle">${(table.total_records || table.total_checked || 0).toLocaleString()}건 검사 | ${table.total_issues}건 오류</div>
                </div>
            </div>
            <div class="inline-detail-body">
    `;

    html += renderDXTableDetail(vType, table);

    html += '</div></div>';
    ViewStack.push(html);
}

function renderDXTables(vType, vIdx) {
    if (!vType.tables || vType.tables.length === 0) {
        return '<p style="padding: 20px; color: var(--text-secondary);">테이블 데이터 없음</p>';
    }

    let html = '';

    vType.tables.forEach((table, tIdx) => {
        html += `
            <div class="table-item">
                <div class="table-header" onclick="toggleTable(${vIdx}, ${tIdx})">
                    <div class="table-info">
                        <span class="table-name">${table.table_name}</span>
                        <span style="font-size: 12px; color: var(--text-secondary);">
                            (${(table.total_records || table.total_checked || 0).toLocaleString()}건 검사)
                        </span>
                    </div>
                    <div class="table-stats">
                        <span class="table-count ${table.status.toLowerCase()}">${table.total_issues.toLocaleString()}건</span>
                        <span class="status-badge ${table.status.toLowerCase()}">${table.status}</span>
                        <span class="toggle-icon" id="toggle-dx-t-${vIdx}-${tIdx}">▶</span>
                    </div>
                </div>
                <div class="detail-container" id="dx-detail-${vIdx}-${tIdx}">
                    ${renderDXTableDetail(vType, table)}
                </div>
            </div>
        `;
    });

    return html;
}

function renderDXTableDetail(vType, table) {
    let html = '';
    const tableName = table.table_name;

    // NULL 검증 - 리테일러별 상세
    if (vType.type === 'null' && table.retailers) {
        const retailerCount = table.retailers.length;
        const gridCols = retailerCount <= 2 ? retailerCount : 3;
        html += `<div class="retailer-grid" style="grid-template-columns: repeat(${gridCols}, 1fr)">`;
        table.retailers.forEach(retailer => {
            const hasIssue = (retailer.records_with_null || 0) > 0;
            const totalCount = retailer.total || 0;
            const nullCount = retailer.records_with_null || 0;

            html += `
                <div class="retailer-card ${(retailer.status || 'ok').toLowerCase()}">
                    <div class="retailer-card-main"
                         onclick="openDetailModal('null', '${tableName}', '${retailer.retailer}', ${nullCount})"
                         ${!hasIssue ? 'style="cursor: default;"' : 'style="cursor: pointer;"'}>
                        <div class="retailer-header">
                            <span class="retailer-name">${retailer.retailer}</span>
                            <span class="retailer-issue-count ${(retailer.status || 'ok').toLowerCase()}">${nullCount}건</span>
                        </div>
                        <div class="retailer-detail">
                            총 ${totalCount.toLocaleString()}건 중 필수값 NULL 레코드
                        </div>
                        <div class="retailer-fields">
                            ${renderNullFieldsDetail(retailer.fields_detail)}
                        </div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }

    // 형식 검증 - 리테일러별
    if (vType.type === 'format' && table.retailers) {
        const retailerCount = table.retailers.length;
        const gridCols = retailerCount <= 2 ? retailerCount : 3;
        html += `<div class="retailer-grid" style="grid-template-columns: repeat(${gridCols}, 1fr)">`;
        table.retailers.forEach(retailer => {
            const hasIssue = (retailer.issue_count || 0) > 0;
            const totalCount = retailer.total || 0;
            const issueCount = retailer.issue_count || 0;
            html += `
                <div class="retailer-card ${(retailer.status || 'ok').toLowerCase()}">
                    <div class="retailer-header">
                        <span class="retailer-name">${retailer.retailer}</span>
                        <span class="retailer-issue-count ${(retailer.status || 'ok').toLowerCase()}">${issueCount}건</span>
                    </div>
                    <div class="retailer-detail">
                        총 ${totalCount.toLocaleString()}건 중 형식 오류 레코드
                    </div>
                    <div class="retailer-actions">
                        <button class="btn-rule" onclick="event.stopPropagation(); openRuleModal('${tableName}', '${retailer.retailer}')">검증규칙</button>
                        ${hasIssue ? `<button class="btn-detail" onclick="event.stopPropagation(); openDetailModal('format', '${tableName}', '${retailer.retailer}', ${issueCount})">상세보기</button>` : ''}
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }

    // 중복 검증 - 리테일러별 중복
    if (vType.type === 'duplicate' && table.retailers) {
        const isYouTube = table.table === 'youtube';
        const isMarket = table.table === 'market';
        const retailerCount = table.retailers.length;
        const gridCols = retailerCount <= 2 ? retailerCount : 3;
        html += `<div class="retailer-grid" style="grid-template-columns: repeat(${gridCols}, 1fr)">`;
        table.retailers.forEach(retailer => {
            const dupGroups = retailer.duplicate_groups || 0;
            const hasIssue = dupGroups > 0;
            let detailTableName = tableName;
            if (isYouTube) {
                if (retailer.retailer === 'Logs') detailTableName = 'YouTube Logs';
                else if (retailer.retailer === 'Videos') detailTableName = 'YouTube Videos';
                else detailTableName = 'YouTube Comments';
            }
            let detailText = '중복 그룹 수';
            if (isYouTube && retailer.retailer === 'Logs') {
                detailText = 'keyword + category 중복';
            } else if (isYouTube && retailer.retailer === 'Videos') {
                detailText = 'video_id + keyword 중복';
            } else if (isYouTube && retailer.retailer === 'Comments') {
                detailText = 'video_id + comment_id 중복';
            } else if (isMarket && retailer.retailer === 'Trend') {
                detailText = 'keyword 중복';
            } else if (isMarket && retailer.retailer === 'Product') {
                detailText = 'batch_id + samsung_series + comp_brand + comp_series 중복';
            } else if (isMarket && retailer.retailer === 'Event') {
                detailText = 'batch_id + comp_brand + comp_sku 중복';
            }
            html += `
                <div class="retailer-card ${(retailer.status || 'ok').toLowerCase()}"
                     onclick="openDetailModal('duplicate', '${detailTableName}', '${retailer.retailer}', ${dupGroups})"
                     ${!hasIssue ? 'style="cursor: default;"' : ''}>
                    <div class="retailer-header">
                        <span class="retailer-name">${retailer.retailer}</span>
                        <span class="retailer-issue-count ${(retailer.status || 'ok').toLowerCase()}">${dupGroups}건</span>
                    </div>
                    <div class="retailer-detail">${detailText}</div>
                </div>
            `;
        });
        html += '</div>';
    }

    if (!html) {
        html = '<p style="padding: 20px; color: var(--text-secondary);">상세 데이터 없음</p>';
    }

    return html;
}

// ==================== 공통 함수 ====================
function getStatusClass(count) {
    if (count === 0) return 'ok';
    if (count <= 10) return 'warning';
    return 'critical';
}

function renderNullFieldsDetail(fieldsDetail) {
    if (!fieldsDetail) return '';
    return Object.entries(fieldsDetail).map(([field, count]) => {
        const safeCount = count || 0;
        const hasIssue = safeCount > 0;
        return `<span class="field-badge ${hasIssue ? 'has-issue' : 'ok'}">${field}: ${safeCount}</span>`;
    }).join('');
}

function toggleValidation(vIdx) {
    const container = document.getElementById(`dx-tables-${vIdx}`);
    const icon = document.getElementById(`toggle-dx-v-${vIdx}`);

    if (container.classList.contains('show')) {
        container.classList.remove('show');
        icon.classList.remove('expanded');
    } else {
        container.classList.add('show');
        icon.classList.add('expanded');
    }
}

function toggleTable(vIdx, tIdx) {
    const container = document.getElementById(`dx-detail-${vIdx}-${tIdx}`);
    const icon = document.getElementById(`toggle-dx-t-${vIdx}-${tIdx}`);

    if (container.classList.contains('show')) {
        container.classList.remove('show');
        icon.classList.remove('expanded');
    } else {
        container.classList.add('show');
        icon.classList.add('expanded');
    }
}

function updateCurrentInfo(date) {
    const el = document.getElementById('current-info');
    if (!el) return;

    const today = new Date().toISOString().split('T')[0];
    const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];

    let badgeClass = 'past';
    let badgeText = '';
    if (date === today) {
        badgeClass = 'today';
        badgeText = 'TODAY';
    } else if (date === yesterday) {
        badgeClass = 'yesterday';
        badgeText = 'D-1';
    } else {
        const diffDays = Math.floor((new Date(today) - new Date(date)) / 86400000);
        badgeText = `D-${diffDays}`;
    }
    el.innerHTML = `<strong>${date}</strong> DX 검증 현황 <span class="date-badge ${badgeClass}">${badgeText}</span>`;
}

// ==================== 모달 함수 ====================
let modalState = {
    type: null,
    tableName: null,
    tableParam: null,
    retailer: null,
    count: 0,
    currentPage: 1,
    totalPages: 1,
    totalGroups: 0,
    nullFieldsData: null,
    selectedField: null
};

function openDetailModal(type, tableName, retailer, count, page = 1) {
    if (count === 0) { showToast('조회된 데이터가 없습니다.', 'info'); return; }

    const typeNames = { 'null': 'NULL 검증', 'format': '형식 검증', 'duplicate': '중복 검증' };
    const titleText = `${retailer} - ${typeNames[type]} 오류`;
    const subtitleText = `${tableName} | ${count}건의 오류 데이터`;

    const date = getSelectedDate();
    const tableParam = tableName === 'YouTube' ? 'youtube' :
                       tableName === 'YouTube Logs' ? 'youtube_logs' :
                       tableName === 'YouTube Comments' ? 'youtube_comments' :
                       tableName === 'YouTube Videos' ? 'youtube_videos' :
                       tableName === 'TV Retail' ? 'tv_retail' :
                       tableName === 'HHP Retail' ? 'hhp_retail' :
                       tableName === 'Market' ? 'market' :
                       tableName.toLowerCase().replace(' ', '_');

    if (isInlineMode()) {
        // 섹션 페이지: ViewStack 인라인 교체
        var _d = new Date(date + 'T00:00:00');
        var _w = ['일','월','화','수','목','금','토'][_d.getDay()];
        var dateLabel = date + '(' + _w + ')';
        ViewStack.push(`
            <div class="inline-detail-view">
                <div class="inline-detail-header">
                    <div>
                        <div class="inline-detail-title">${titleText}</div>
                        <div class="inline-detail-subtitle" id="detail-subtitle">${subtitleText}</div>
                    </div>
                    <div style="display:flex;align-items:center;"><div class="inline-detail-date">${dateLabel}</div></div>
                </div>
                <div id="detail-body"><div class="modal-loading">데이터 로딩 중...</div></div>
            </div>
        `);
    } else {
        // 대시보드: AppModal
        AppModal.setTitle('l2-detail', titleText);
        AppModal.setBody('l2-detail', '<div id="modal-subtitle" style="font-size:13px;color:var(--text-secondary);margin:-8px 0 16px;">' + subtitleText + '</div><div id="modal-body"><div class="modal-loading">데이터 로딩 중...</div></div>');
        AppModal.open('l2-detail');
    }

    modalState = { type, tableName, tableParam, retailer, count, currentPage: page, totalPages: 1, totalGroups: 0, nullFieldsData: null, selectedField: null, days: 1 };

    let apiUrl;
    if (type === 'null') {
        apiUrl = `/dx/layer2/api/null-detail/?table=${tableParam}&retailer=${retailer}&date=${date}`;
    } else if (type === 'format') {
        apiUrl = `/dx/layer2/api/format-detail/?table=${tableParam}&retailer=${retailer}&date=${date}`;
    } else if (type === 'duplicate') {
        apiUrl = `/dx/layer2/api/anomaly-detail/?table=${tableParam}&retailer=${retailer}&date=${date}&page=${page}&page_size=50`;
    } else {
        apiUrl = `/dx/layer2/api/detail/?type=${type}&table=${tableParam}&retailer=${retailer}&date=${date}`;
    }

    fetch(apiUrl)
        .then(response => response.json())
        .then(data => {
            // 중복 검증: 메타데이터가 data.results 안에 있음
            var dupResults = (type === 'duplicate' && data.results) ? data.results : null;
            if (dupResults && dupResults.total_pages) {
                modalState.totalPages = dupResults.total_pages;
                modalState.totalGroups = dupResults.total_groups;
                modalState.currentPage = dupResults.page || 1;
            } else if (data.total_pages) {
                modalState.totalPages = data.total_pages;
                modalState.totalGroups = data.total_groups;
                modalState.currentPage = data.page || 1;
            }

            // 실제 반환 건수로 subtitle 업데이트
            var actualRecords = data.records || (dupResults ? dupResults.duplicates : null) || data.results || [];
            var actualCount = type === 'duplicate' ? (modalState.totalGroups || actualRecords.length) : actualRecords.length;
            var subtitle = getDetailSubtitle();
            if (subtitle) subtitle.textContent = tableName + ' | ' + actualCount + '건의 오류 데이터';

            // (중복 검증 액션 버튼은 테이블 위 action-bar에서 렌더)

            if (type === 'null') {
                modalState.nullFieldsData = data;
                renderNullFieldSummary(data, tableParam);
            } else if (type === 'format') {
                modalState.formatFieldsData = data;
                renderFormatFieldSummary(data, tableParam);
            } else {
                renderDetailTable(type, data, tableParam);
            }
        })
        .catch(error => {
            console.error('Detail Error:', error);
            const body = getDetailBody();
            if (body) body.innerHTML = '<div class="modal-loading" style="color: var(--color-critical);">데이터 로딩 실패</div>';
        });
}

// NULL 필드별 요약 표시
function renderNullFieldSummary(data, tableParam) {
    const body = getDetailBody();
    const records = data.records || data.results || [];
    const date = data.date || getSelectedDate();

    const fieldCounts = {};
    records.forEach(record => {
        const nullFields = record.null_fields || [];
        nullFields.forEach(field => {
            fieldCounts[field] = (fieldCounts[field] || 0) + 1;
        });
    });

    modalState.nullFieldsData = data;
    modalState.selectedField = null;

    let html = '';

    if (!isInlineMode()) {
        html += `<div class="modal-toolbar">
            <div class="modal-date-picker">
                <label>조회 날짜:</label>
                <input type="date" id="null-modal-date" value="${date}"
                    onchange="reloadNullData(this.value)">
            </div>
        </div>`;
    }

    const sortedFields = Object.entries(fieldCounts).sort((a, b) => b[1] - a[1]);

    if (sortedFields.length === 0) {
        html += '<p style="text-align: center; color: var(--text-secondary);">NULL 오류 데이터가 없습니다.</p>';
    } else {
        html += '<div class="null-field-summary-container">';
        sortedFields.forEach(([field, count]) => {
            html += `
                <div class="null-field-card" onclick="showNullFieldDetail('${field}')">
                    <div class="null-field-card-name">${field}</div>
                    <div class="null-field-card-count">${count}건</div>
                </div>
            `;
        });
        html += '</div>';
    }

    body.innerHTML = html;
}

// NULL 필드별 상세 데이터 표시
function showNullFieldDetail(fieldName, pushStack = true) {
    const body = getDetailBody();
    const data = modalState.nullFieldsData;
    const records = data.records || data.results || [];
    const displayConfig = data.display_config || {};
    const queryConfig = data.query_config || {};
    const dateColumn = data.date_column || 'crawl_datetime';
    const tableParam = modalState.tableParam;
    const date = data.date || getSelectedDate();
    const isRetail = tableParam === 'tv_retail' || tableParam === 'hhp_retail';
    const currentDays = modalState.days || 1;

    var filteredRecords;
    if (currentDays > 1 && isRetail) {
        // days > 1: 조회 날짜에 해당 필드 null인 item 추출 → 해당 item 전체 레코드 표시
        var targetDateStr = date;
        var errorItems = new Set();
        records.forEach(function(record) {
            var recDate = (record[dateColumn] || '').substring(0, 10);
            if (recDate === targetDateStr && (record.null_fields || []).includes(fieldName)) {
                if (record.item) errorItems.add(record.item);
            }
        });
        if (errorItems.size > 0) {
            filteredRecords = records.filter(function(record) { return errorItems.has(record.item); });
        } else {
            filteredRecords = records.filter(function(record) { return (record.null_fields || []).includes(fieldName); });
        }
    } else {
        filteredRecords = records.filter(record => {
            const nullFields = record.null_fields || [];
            return nullFields.includes(fieldName);
        });
    }

    modalState.selectedField = fieldName;
    const fieldConfig = displayConfig[fieldName] || {};
    const selectColumns = fieldConfig.select_columns || [];
    const columnHeaders = fieldConfig.column_headers || {};
    const queryColumns = queryConfig[fieldName] || [];

    // 칼럼 설정: displayConfig가 있으면 동적 생성, 없으면 기본 config 사용
    var columns;
    if (selectColumns.length > 0) {
        columns = selectColumns.map(function(col) {
            return { key: col, label: columnHeaders[col] || col, width: 120 };
        });
    } else {
        columns = getColumnConfig('null', tableParam);
    }

    // Item/쿼리 HTML (대시보드 모달에서만 표시)
    var itemQueryHtml = '';
    if (!isInlineMode()) {
        itemQueryHtml += `<div class="modal-toolbar">
            <button class="btn-back" onclick="backToNullFieldSummary()">← 뒤로가기</button>
            <div class="modal-date-picker">
                <label>조회 날짜:</label>
                <input type="date" id="null-modal-date" value="${date}"
                    onchange="reloadNullData(this.value)">
            </div>
        </div>`;
        itemQueryHtml += `<h4 style="margin-bottom: 12px; font-size: 15px;">${fieldName} NULL 오류 (${filteredRecords.length}건)</h4>`;
    }

    if (filteredRecords.length === 0) {
        var emptyHtml = itemQueryHtml + '<p>해당 필드의 NULL 오류 데이터가 없습니다.</p>';
        if (isInlineMode()) {
            var _de = new Date(date + 'T00:00:00');
            var _we = ['일','월','화','수','목','금','토'][_de.getDay()];
            var wrapper = `<div class="inline-detail-view">
                <div class="inline-detail-header"><div>
                    <div class="inline-detail-title">${fieldName} NULL 오류 (0건)</div>
                    <div class="inline-detail-subtitle" id="detail-subtitle">${modalState.tableName} | ${modalState.retailer}</div>
                </div><div class="inline-detail-date">${date}(${_we})</div></div>
                <div id="detail-body">${emptyHtml}</div>
            </div>`;
            if (pushStack) ViewStack.push(wrapper); else { var c = ViewStack.getContainer(); if (c) c.innerHTML = wrapper; }
        } else {
            body.innerHTML = emptyHtml;
        }
        return;
    }

    // Item/쿼리 섹션 생성 (retail만)
    if (isRetail) {
        const items = [...new Set(filteredRecords.map(r => r.item).filter(Boolean))].sort();
        const ids = filteredRecords.map(r => r.id).filter(Boolean);

        if (isInlineMode()) {
            // 섹션 페이지: item/ID 목록만 토글로 표시 (쿼리 없음)
            var listLabel = items.length > 0 ? 'Item 목록 (' + items.length + '개)' : ids.length > 0 ? 'ID 목록 (' + ids.length + '개)' : '';
            var listContent = items.length > 0 ? items.join(', ') : ids.join(', ');
            if (listLabel) {
                itemQueryHtml += `<div class="item-toggle-section">
                    <div class="item-toggle-header" onclick="var c=this.nextElementSibling;var h=c.style.display==='none';c.style.display=h?'':'none';this.querySelector('.toggle-arrow').textContent=h?'▾':'▸';">
                        <span class="toggle-arrow">▸</span> ${listLabel}
                    </div>
                    <div class="item-toggle-content" style="display:none;">
                        <div class="item-copy-header"><span class="item-copy-title">${listLabel}</span><button class="btn-copy" onclick="event.stopPropagation();copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                        <div class="item-copy-content">${listContent}</div>
                    </div>
                </div>`;
            }
        } else {
            // 대시보드 모달: item 목록 + 쿼리 표시
            const tblName = tableParam === 'tv_retail' ? 'tv_retail_com' : 'hhp_retail_com';
            const retailerName = modalState.retailer || '';
            const queryCols = queryColumns.length > 0 ? queryColumns.join(', ') : '*';

            if (items.length > 0) {
                const inClause = items.map(item => `'${item}'`).join(', ');
                const query3Days = `SELECT ${queryCols}\nFROM ${tblName}\nWHERE account_name = '${retailerName}'\n  AND item IN (${inClause})\n  AND DATE(${dateColumn}::timestamp) >= DATE('${date}') - INTERVAL '2 days'\n  AND DATE(${dateColumn}::timestamp) <= DATE('${date}')\nORDER BY item, ${dateColumn} ASC;`;
                itemQueryHtml += `<div class="item-query-section">
                    <div class="item-list-box">
                        <div class="item-copy-header"><span class="item-copy-title">Item 목록 (${items.length}개)</span><button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                        <div class="item-copy-content">${items.join(', ')}</div>
                    </div>
                    <div class="query-box">
                        <div class="item-copy-header"><span class="item-copy-title">3일치 조회 쿼리 (${date} 기준)</span><button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                        <pre class="query-content">${query3Days}</pre>
                    </div>
                </div>`;
            } else if (ids.length > 0) {
                const queryById = `SELECT ${queryCols}\nFROM ${tblName}\nWHERE id IN (${ids.join(', ')});`;
                itemQueryHtml += `<div class="item-query-section">
                    <div class="item-list-box">
                        <div class="item-copy-header"><span class="item-copy-title">ID 목록 (${ids.length}개)</span><button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                        <div class="item-copy-content">${ids.join(', ')}</div>
                    </div>
                    <div class="query-box">
                        <div class="item-copy-header"><span class="item-copy-title">ID 기반 조회 쿼리</span><button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                        <pre class="query-content">${queryById}</pre>
                    </div>
                </div>`;
            }
        }
    }

    // 컨테이너 HTML 생성
    var containerHtml = buildDetailContainerHtml({ itemQueryHtml: itemQueryHtml });

    if (isInlineMode()) {
        var _dn = new Date(date + 'T00:00:00');
        var _wn = ['일','월','화','수','목','금','토'][_dn.getDay()];
        const fieldTitle = currentDays > 1
            ? `${fieldName} NULL 오류 항목 (${filteredRecords.length}건 / ${currentDays}일치)`
            : `${fieldName} NULL 오류 (${filteredRecords.length}건)`;
        const fieldSubtitle = `${modalState.tableName} | ${modalState.retailer}`;
        var daysInputHtml = isRetail ? `<div style="display:flex;align-items:center;gap:6px;margin-right:12px;">
            <label style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">일수:</label>
            <input type="number" id="detail-days" value="${currentDays}" min="1" max="30"
                style="width:50px;padding:3px 6px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;font-size:12px;text-align:center;"
                onkeydown="if(event.key==='Enter')reloadNullDays()">
            <button onclick="reloadNullDays()" style="padding:3px 10px;font-size:12px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;background:var(--page-color,#0d9488);color:#fff;cursor:pointer;white-space:nowrap;">조회</button>
        </div>` : '';
        const wrapper = `<div class="inline-detail-view">
            <div class="inline-detail-header"><div>
                <div class="inline-detail-title">${fieldTitle}</div>
                <div class="inline-detail-subtitle" id="detail-subtitle">${fieldSubtitle}</div>
            </div><div style="display:flex;align-items:center;">${daysInputHtml}<div class="inline-detail-date">${date}(${_wn})</div></div></div>
            <div id="detail-body">${containerHtml}</div>
        </div>`;
        if (pushStack) ViewStack.push(wrapper); else { var c = ViewStack.getContainer(); if (c) c.innerHTML = wrapper; }
    } else {
        body.innerHTML = containerHtml;
    }

    // CommonTable + FilterBar + Pagination 렌더
    renderDetailWithTable({
        config: columns,
        data: filteredRecords,
        tableParam: tableParam,
        type: 'null',
        selectCols: data.select_cols || null,
        editableCols: data.editable_cols || [],
        actualTable: data.actual_table || '',
        crawlDate: date,
        normalReviews: data.normal_reviews || {}
    });
}

// 클립보드 복사 함수 (HTTPS/HTTP 모두 지원)
function copyToClipboard(element) {
    const text = element.textContent;
    const btn = element.previousElementSibling.querySelector('.btn-copy');

    function showSuccess() {
        if (btn) {
            const originalText = btn.textContent;
            btn.textContent = '복사됨!';
            btn.style.background = '#22c55e';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.style.background = '';
            }, 1500);
        }
    }

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(showSuccess).catch(err => {
            console.error('복사 실패:', err);
            fallbackCopy(text, showSuccess);
        });
    } else {
        fallbackCopy(text, showSuccess);
    }
}

function fallbackCopy(text, onSuccess) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.top = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        onSuccess();
    } catch (err) {
        console.error('복사 실패:', err);
        alert('복사에 실패했습니다.');
    }
    document.body.removeChild(textArea);
}

function backToNullFieldSummary() {
    if (isInlineMode()) {
        ViewStack.pop();
        return;
    }
    const data = modalState.nullFieldsData;
    const tableParam = modalState.tableParam;
    renderNullFieldSummary(data, tableParam);
}

// ==================== 형식 검증: 필드별 요약 → 상세 (null 패턴) ====================
function renderFormatFieldSummary(data, tableParam) {
    const body = getDetailBody();
    const records = data.records || data.results || [];
    const date = data.date || getSelectedDate();

    const fieldCounts = {};
    records.forEach(record => {
        const errorFields = record.error_fields || [];
        errorFields.forEach(field => {
            fieldCounts[field] = (fieldCounts[field] || 0) + 1;
        });
    });

    modalState.formatFieldsData = data;
    modalState.selectedField = null;

    let html = '';

    if (!isInlineMode()) {
        html += `<div class="modal-toolbar">
            <div class="modal-date-picker">
                <label>조회 날짜:</label>
                <input type="date" id="fmt-modal-date" value="${date}"
                    onchange="reloadFormatData(this.value)">
            </div>
        </div>`;
    }

    const sortedFields = Object.entries(fieldCounts).sort((a, b) => b[1] - a[1]);

    if (sortedFields.length === 0) {
        html += '<p style="text-align: center; color: var(--text-secondary);">형식 오류 데이터가 없습니다.</p>';
    } else {
        html += '<div class="null-field-summary-container">';
        sortedFields.forEach(([field, count]) => {
            html += `
                <div class="null-field-card" onclick="showFormatFieldDetail('${field}')">
                    <div class="null-field-card-name">${field}</div>
                    <div class="null-field-card-count">${count}건</div>
                </div>
            `;
        });
        html += '</div>';
    }

    body.innerHTML = html;
}

function showFormatFieldDetail(fieldName, pushStack = true) {
    const body = getDetailBody();
    const data = modalState.formatFieldsData;
    const records = data.records || data.results || [];
    const tableParam = modalState.tableParam;
    const date = data.date || getSelectedDate();
    const isRetail = tableParam === 'tv_retail' || tableParam === 'hhp_retail';
    const currentDays = modalState.days || 1;

    var filteredRecords;
    if (currentDays > 1 && isRetail) {
        // days > 1: 조회 날짜에 해당 필드 오류인 item 추출 → 해당 item 전체 레코드 표시
        var targetDateStr = date;
        var errorItems = new Set();
        records.forEach(function(record) {
            var recDate = (record.crawl_datetime || '').substring(0, 10);
            if (recDate === targetDateStr && (record.error_fields || []).includes(fieldName)) {
                if (record.item) errorItems.add(record.item);
            }
        });
        if (errorItems.size > 0) {
            filteredRecords = records.filter(function(record) { return errorItems.has(record.item); });
        } else {
            filteredRecords = records.filter(function(record) { return (record.error_fields || []).includes(fieldName); });
        }
    } else {
        filteredRecords = records.filter(record => {
            return (record.error_fields || []).includes(fieldName);
        });
    }

    modalState.selectedField = fieldName;

    // 각 레코드에 위배사유 컬럼 추가
    filteredRecords.forEach(function(r) {
        var ed = r.error_details && r.error_details[fieldName];
        r._error_reason = ed ? (ed.rule + ': ' + ed.reason) : '';
    });

    // 칼럼 설정: 리테일러는 디폴트 5개 + 위배사유, 나머지는 전체 컬럼 + 위배사유
    var columnNames = data.column_names || [];
    var reasonCol = { key: '_error_reason', label: '위배사유', width: 200 };
    var columns;
    var selectCols = [];
    if (isRetail && columnNames.length > 0) {
        var defaultKeys = ['id', 'item', 'crawl_datetime', fieldName, 'product_url'];
        var _seen = {};
        columns = [];
        defaultKeys.forEach(function(k) {
            if (_seen[k]) return;
            _seen[k] = true;
            columns.push({ key: k, label: k === 'product_url' ? 'URL' : k, width: k === 'id' ? 80 : 120 });
        });
        columns.push(reasonCol);
        selectCols = columnNames;
    } else if (columnNames.length > 0) {
        columns = columnNames.map(function(col) {
            return { key: col, label: col === 'product_url' ? 'URL' : col, width: col === 'id' ? 80 : 120 };
        });
        columns.push(reasonCol);
    } else {
        columns = [
            { key: 'id', label: 'ID', width: 80 },
            { key: 'item', label: 'Item', width: 150 },
            { key: 'crawl_datetime', label: '수집일', width: 120 },
            reasonCol
        ];
    }

    // Item 목록 HTML (섹션 페이지에서)
    var itemQueryHtml = '';
    if (!isInlineMode()) {
        itemQueryHtml += `<div class="modal-toolbar">
            <button class="btn-back" onclick="backToFormatFieldSummary()">← 뒤로가기</button>
            <div class="modal-date-picker">
                <label>조회 날짜:</label>
                <input type="date" id="fmt-modal-date" value="${date}"
                    onchange="reloadFormatData(this.value)">
            </div>
        </div>`;
        itemQueryHtml += `<h4 style="margin-bottom: 12px; font-size: 15px;">${fieldName} 형식 오류 (${filteredRecords.length}건)</h4>`;
    }

    if (filteredRecords.length === 0) {
        var emptyHtml = itemQueryHtml + '<p>해당 필드의 형식 오류 데이터가 없습니다.</p>';
        if (isInlineMode()) {
            var _de = new Date(date + 'T00:00:00');
            var _we = ['일','월','화','수','목','금','토'][_de.getDay()];
            var wrapper = `<div class="inline-detail-view">
                <div class="inline-detail-header"><div>
                    <div class="inline-detail-title">${fieldName} 형식 오류 (0건)</div>
                    <div class="inline-detail-subtitle" id="detail-subtitle">${modalState.tableName} | ${modalState.retailer}</div>
                </div><div class="inline-detail-date">${date}(${_we})</div></div>
                <div id="detail-body">${emptyHtml}</div>
            </div>`;
            if (pushStack) ViewStack.push(wrapper); else { var c = ViewStack.getContainer(); if (c) c.innerHTML = wrapper; }
        } else {
            body.innerHTML = emptyHtml;
        }
        return;
    }

    // Item/쿼리 섹션 (retail만)
    if (isRetail) {
        const items = [...new Set(filteredRecords.map(r => r.item).filter(Boolean))].sort();
        if (isInlineMode() && items.length > 0) {
            itemQueryHtml += `<div class="item-toggle-section">
                <div class="item-toggle-header" onclick="var c=this.nextElementSibling;var h=c.style.display==='none';c.style.display=h?'':'none';this.querySelector('.toggle-arrow').textContent=h?'▾':'▸';">
                    <span class="toggle-arrow">▸</span> Item 목록 (${items.length}개)
                </div>
                <div class="item-toggle-content" style="display:none;">
                    <div class="item-copy-header"><span class="item-copy-title">Item 목록 (${items.length}개)</span><button class="btn-copy" onclick="event.stopPropagation();copyToClipboard(this.parentElement.nextElementSibling)">복사</button></div>
                    <div class="item-copy-content">${items.join(', ')}</div>
                </div>
            </div>`;
        }
    }

    // 컨테이너 HTML 생성
    var containerHtml = buildDetailContainerHtml({ itemQueryHtml: itemQueryHtml });

    if (isInlineMode()) {
        var _dn = new Date(date + 'T00:00:00');
        var _wn = ['일','월','화','수','목','금','토'][_dn.getDay()];
        const fieldTitle = currentDays > 1
            ? `${fieldName} 형식 오류 항목 (${filteredRecords.length}건 / ${currentDays}일치)`
            : `${fieldName} 형식 오류 (${filteredRecords.length}건)`;
        const fieldSubtitle = `${modalState.tableName} | ${modalState.retailer}`;
        var daysInputHtml = isRetail ? `<div style="display:flex;align-items:center;gap:6px;margin-right:12px;">
            <label style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">일수:</label>
            <input type="number" id="fmt-detail-days" value="${currentDays}" min="1" max="30"
                style="width:50px;padding:3px 6px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;font-size:12px;text-align:center;"
                onkeydown="if(event.key==='Enter')reloadFormatDays()">
            <button onclick="reloadFormatDays()" style="padding:3px 10px;font-size:12px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;background:var(--page-color,#0d9488);color:#fff;cursor:pointer;white-space:nowrap;">조회</button>
        </div>` : '';
        const wrapper = `<div class="inline-detail-view">
            <div class="inline-detail-header"><div>
                <div class="inline-detail-title">${fieldTitle}</div>
                <div class="inline-detail-subtitle" id="detail-subtitle">${fieldSubtitle}</div>
            </div><div style="display:flex;align-items:center;">${daysInputHtml}<div class="inline-detail-date">${date}(${_wn})</div></div></div>
            <div id="detail-body">${containerHtml}</div>
        </div>`;
        if (pushStack) ViewStack.push(wrapper); else { var c = ViewStack.getContainer(); if (c) c.innerHTML = wrapper; }
    } else {
        body.innerHTML = containerHtml;
    }

    // CommonTable + FilterBar + Pagination 렌더
    renderDetailWithTable({
        config: columns,
        selectCols: selectCols,
        data: filteredRecords,
        tableParam: tableParam,
        type: 'format',
        editableCols: data.editable_cols || [],
        actualTable: data.actual_table || '',
        crawlDate: date,
        normalReviews: data.normal_reviews || {}
    });
}

function backToFormatFieldSummary() {
    if (isInlineMode()) {
        ViewStack.pop();
        return;
    }
    const data = modalState.formatFieldsData;
    const tableParam = modalState.tableParam;
    renderFormatFieldSummary(data, tableParam);
}

async function reloadFormatData(date) {
    const body = getDetailBody();
    body.innerHTML = '<div class="modal-loading">데이터를 불러오는 중...</div>';

    const { tableParam, retailer, selectedField } = modalState;

    try {
        const days = modalState.days || 1;
        const response = await fetch(`/dx/layer2/api/format-detail/?table=${tableParam}&retailer=${retailer}&date=${date}&days=${days}`);
        const data = await response.json();

        modalState.formatFieldsData = data;

        const records = data.records || data.results || [];
        var subtitle = getDetailSubtitle();
        if (subtitle) subtitle.textContent = `${modalState.tableName} | ${records.length}건의 오류 데이터`;

        if (selectedField) {
            showFormatFieldDetail(selectedField, false);
        } else {
            renderFormatFieldSummary(data, tableParam);
        }
    } catch (error) {
        console.error('Error:', error);
        body.innerHTML = '<div class="modal-loading" style="color: var(--color-critical);">데이터 로드 실패</div>';
    }
}

async function reloadNullData(date) {
    const body = getDetailBody();
    body.innerHTML = '<div class="modal-loading">데이터를 불러오는 중...</div>';

    const { tableParam, retailer, selectedField } = modalState;

    try {
        const days = modalState.days || 1;
        const response = await fetch(`/dx/layer2/api/null-detail/?table=${tableParam}&retailer=${retailer}&date=${date}&days=${days}`);
        const data = await response.json();

        modalState.nullFieldsData = data;

        const records = data.records || data.results || [];
        getDetailSubtitle().textContent = `${modalState.tableName} | ${records.length}건의 오류 데이터`;

        if (selectedField) {
            showNullFieldDetail(selectedField, false);
        } else {
            renderNullFieldSummary(data, tableParam);
        }
    } catch (error) {
        console.error('Error:', error);
        body.innerHTML = '<div class="modal-loading" style="color: var(--color-critical);">데이터 로드 실패</div>';
    }
}

function reloadNullDays() {
    var daysInput = document.getElementById('detail-days') || document.getElementById('null-modal-days');
    var days = parseInt(daysInput && daysInput.value) || 1;
    if (days < 1) days = 1;
    modalState.days = days;

    var date;
    var dateInput = document.getElementById('null-modal-date');
    date = dateInput ? dateInput.value : getSelectedDate();

    reloadNullData(date);
}

function reloadFormatDays() {
    var daysInput = document.getElementById('fmt-detail-days');
    var days = parseInt(daysInput && daysInput.value) || 1;
    if (days < 1) days = 1;
    modalState.days = days;

    var date;
    var dateInput = document.getElementById('fmt-modal-date');
    date = dateInput ? dateInput.value : getSelectedDate();

    reloadFormatData(date);
}

function goToPage(page) {
    if (page < 1 || page > modalState.totalPages) return;
    openDetailModal(modalState.type, modalState.tableName, modalState.retailer, modalState.count, page);
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = date.getHours();
    const ampm = hours < 12 ? '오전' : '오후';

    return `${year}-${month}-${day} ${ampm}`;
}

function formatDateOnly(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

// ========== 중복 정리 (체크박스 방식) ==========

// 중복 검증 액션 버튼바 (테이블 위)
function _renderDupActionBar() {
    var el = document.getElementById('detail-action-bar');
    if (!el) return;
    new FilterBar('#detail-action-bar', {
        sticky: false,
        padding: '4px 0',
        controls: [],
        right: [
            { type: 'button', label: '최신 제외 전체 선택', style: 'outline', size: 'fb', onClick: function() { _selectExceptLatest(); } },
            { type: 'button', label: '선택 해제', style: 'outline', size: 'fb', onClick: function() { _clearDupChecks(); } },
            { type: 'button', label: '선택 삭제', style: 'danger', size: 'fb', onClick: function() { _doDuplicateCleanup(); } }
        ]
    }).render();
    var fbEl = document.querySelector('#detail-action-bar .fb');
    if (fbEl) {
        fbEl.style.background = 'none';
        fbEl.style.border = 'none';
        fbEl.style.boxShadow = 'none';
        fbEl.style.marginBottom = '8px';
    }
}

// 헤더 체크박스 주입 (전체선택/해제)
function _injectDupCheckboxHeader() {
    var headerCells = document.querySelectorAll('#detail-table-area th');
    for (var i = 0; i < headerCells.length; i++) {
        var th = headerCells[i];
        if (th.textContent.trim() === '' && th.style.width) {
            th.innerHTML = '<input type="checkbox" class="dup-check-all" title="전체 선택/해제">';
            th.querySelector('.dup-check-all').addEventListener('change', function() {
                var checks = document.querySelectorAll('.dup-check');
                var checked = this.checked;
                checks.forEach(function(cb) { cb.checked = checked; });
            });
            break;
        }
    }
}

// 최신 제외 전체 선택 (각 그룹의 마지막 레코드 = 최신 제외)
function _selectExceptLatest() {
    var checks = document.querySelectorAll('.dup-check');
    checks.forEach(function(cb) {
        cb.checked = !cb.hasAttribute('data-group-last');
    });
    // 헤더 체크박스 상태 동기화
    var allCheck = document.querySelector('.dup-check-all');
    if (allCheck) {
        var total = checks.length;
        var checked = document.querySelectorAll('.dup-check:checked').length;
        allCheck.checked = total > 0 && checked === total;
    }
}

// 선택 해제
function _clearDupChecks() {
    document.querySelectorAll('.dup-check').forEach(function(cb) { cb.checked = false; });
    var allCheck = document.querySelector('.dup-check-all');
    if (allCheck) allCheck.checked = false;
}

// 선택 삭제 실행
function _doDuplicateCleanup() {
    var checked = document.querySelectorAll('.dup-check:checked');
    if (checked.length === 0) {
        showToast('삭제할 항목을 선택해주세요.', 'info');
        return;
    }

    var ids = [];
    checked.forEach(function(cb) { ids.push(parseInt(cb.getAttribute('data-id'))); });
    var table = modalState.tableParam;
    var date = getSelectedDate();

    showConfirm(ids.length + '건 삭제하시겠습니까?')
        .then(function(ok) {
            if (!ok) return;
            fetch('/dx/layer2/api/duplicate-cleanup/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ table: table, ids: ids, date: date })
            })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.success) {
                    showToast(res.deleted_count + '건 삭제 완료', 'success');
                    openDetailModal('duplicate', modalState.tableName, modalState.retailer, modalState.count, 1);
                } else {
                    showToast(res.error || '삭제 실패', 'error');
                }
            })
            .catch(function(err) { showToast('요청 오류: ' + err.message, 'error'); });
        });
}

function renderDetailTable(type, data, tableParam) {
    const body = getDetailBody();

    let records;
    if (type === 'duplicate') {
        records = data.results?.duplicates || [];
    } else {
        records = data.records || data.results || [];
    }

    if (records.length === 0) {
        body.innerHTML = '<div class="modal-loading">데이터가 없습니다.</div>';
        return;
    }

    // NULL 타입: 칼럼 동적 생성 (column_names가 있을 경우)
    var config;
    if (type === 'null') {
        var columnNames = data.column_names || [];
        if (columnNames.length > 0) {
            config = [
                { key: 'id', label: 'ID', width: 60 },
                { key: 'null_fields', label: 'NULL 필드', width: 150 },
            ];
            columnNames.forEach(function(col) {
                config.push({ key: col, label: col === 'product_url' ? 'URL' : col, width: 120 });
            });
        } else {
            config = getColumnConfig('null', tableParam);
        }
    } else {
        config = getColumnConfig(type, tableParam);
    }

    // 서버 사이드 페이징 (중복) — 서버에서 받은 데이터 그대로 표시
    var isServerPaging = type === 'duplicate' && modalState.totalPages > 1;

    // 컨테이너 HTML 생성
    var containerHtml = buildDetailContainerHtml({});
    body.innerHTML = containerHtml;

    // 렌더링
    if (isServerPaging) {
        // 서버 사이드 페이징: 전체 데이터를 한 번에 표시, 서버 페이지네이션 별도 표시
        var allCols = getAllColumns(config);
        var ctColumns = [{ key: '_chk', label: '', width: 40, sortable: false, align: 'center' }];
        allCols.forEach(function(col) {
            ctColumns.push({ key: col.key, label: col.label, width: col.width, sortable: false, align: col.align });
        });

        detailViewState.type = type;
        detailViewState.tableParam = tableParam;
        detailViewState.columns = allCols;
        detailViewState.editableCols = new Set(data.editable_cols || []);
        detailViewState.actualTable = data.actual_table || '';
        detailViewState.crawlDate = data.date || '';

        var flatData = flattenRecords(type, records, tableParam);
        detailViewState.allData = flatData;

        detailViewState.table = new CommonTable('#detail-table-area', {
            variant: 'detail', columns: ctColumns, vlines: true, rounded: true, showTotalCount: true, padding: '10px 12px'
        });
        detailViewState.table.render();

        // 전체 렌더 (서버에서 이미 페이징됨)
        detailViewState.table.renderBody(flatData, function(row) {
            var tr = '<tr>';
            // 체크박스 (매 행, rowspan 없음)
            tr += '<td style="text-align:center"><input type="checkbox" class="dup-check" data-id="' + row.id + '"' +
                  (row._isGroupLast ? ' data-group-last="1"' : '') + '></td>';
            if (row._isGroupFirst) {
                config.group.forEach(function(col) {
                    var inner = getCellHtml(row, col, tableParam).replace(/^<td[^>]*>/, '').replace(/<\/td>$/, '');
                    tr += '<td rowspan="' + row._groupSize + '"' +
                          (col.align ? ' style="text-align:' + col.align + ';font-weight:500;"' : '') + '>' + inner + '</td>';
                });
            }
            config.detail.forEach(function(col) {
                tr += getCellHtml(row, col, tableParam);
            });
            if (row._isGroupFirst && config.trailing) {
                config.trailing.forEach(function(col) {
                    var inner = getCellHtml(row, col, tableParam).replace(/^<td[^>]*>/, '').replace(/<\/td>$/, '');
                    tr += '<td rowspan="' + row._groupSize + '">' + inner + '</td>';
                });
            }
            return tr + '</tr>';
        });
        _injectDupCheckboxHeader();
        _renderDupActionBar();

        // 서버 사이드 페이지네이션
        var pagerEl = document.getElementById('detail-pagination');
        if (pagerEl) {
            var sp = new Pagination(pagerEl, {
                variant: 'simple',
                pageSize: 50,
                showInfo: true,
                onPageChange: function(page) { goToPage(page); }
            });
            sp.render(modalState.totalGroups, modalState.currentPage);
        }

        // 건수 (CommonTable의 ct-count를 전체 건수로 덮어쓰기)
        var countEl = document.querySelector('#detail-table-area .ct-count');
        if (countEl) countEl.innerHTML = '총 <strong>' + modalState.totalGroups.toLocaleString() + '</strong>개 중복 그룹';

        // FilterBar (섹션 페이지에서만 표시)
        if (isInlineMode()) {
            var filterCols = allCols.map(function(c, i) { return { value: String(i), label: c.label }; });
            var serverCols = data.select_cols || null;
            // id → 디폴트 컬럼 순서 → 나머지 asc 정렬
            var defaultKeySet = {};
            allCols.forEach(function(c) { defaultKeySet[c.key] = c; });
            var selectorColumns = [];
            if (defaultKeySet['id']) selectorColumns.push(defaultKeySet['id']);
            allCols.forEach(function(c) {
                if (c.key === 'id' || c.key === 'null_fields') return;
                selectorColumns.push(c);
            });
            if (serverCols && typeof serverCols === 'object' && !Array.isArray(serverCols)) {
                var colKeys = (serverCols.group || []).concat(serverCols.record || []);
                var extraCols = [];
                colKeys.forEach(function(k) {
                    if (!defaultKeySet[k]) {
                        extraCols.push({ key: k, label: k, width: 120 });
                    }
                });
                extraCols.sort(function(a, b) { return a.key.localeCompare(b.key); });
                extraCols.forEach(function(c) { selectorColumns.push(c); });
            }
            var defaultVisibleKeys = allCols.map(function(c) { return c.key; });
            detailViewState.filterBar = new FilterBar('#detail-filter-bar', {
                sticky: false, padding: '8px 12px',
                controls: [
                    { type: 'select', key: 'filterCol', label: '항목', width: 'auto', options: filterCols },
                    { type: 'input', key: 'filterVal', placeholder: '검색어 입력...', onEnter: function() { applyDetailFilter(); } }
                ],
                onSearch: function() { applyDetailFilter(); },
                onReset: function() { clearDetailFilter(); },
                columnSelector: {
                    columns: selectorColumns,
                    fixed: ['id'],
                    defaultVisible: defaultVisibleKeys,
                    onUpdate: function() { /* 서버 페이징에서는 컬럼 변경 시 재렌더 불필요 */ }
                }
            }).render();
        }
    } else {
        // 클라이언트 사이드 페이징 (NULL, 형식, 중복 소량)
        var selectCols = data.select_cols || null;
        // 중복: {group: [...], record: [...]} → flat 배열로 변환
        if (selectCols && typeof selectCols === 'object' && !Array.isArray(selectCols)) {
            selectCols = (selectCols.group || []).concat(selectCols.record || []);
        }
        renderDetailWithTable({
            config: config,
            data: records,
            tableParam: tableParam,
            type: type,
            selectCols: selectCols,
            editableCols: data.editable_cols || [],
            actualTable: data.actual_table || '',
            crawlDate: data.date || '',
            normalReviews: data.normal_reviews || {}
        });
    }
}

function closeModal() {
    AppModal.close('l2-detail');
}

// 검증규칙 모달
async function openRuleModal(tableName, retailer) {
    AppModal.setTitle('l2-rule', `${retailer} - 형식 검증 규칙`);
    AppModal.setBody('l2-rule', '<div style="text-align: center; padding: 20px;">로딩 중...</div>');
    AppModal.open('l2-rule');
    const body = AppModal.getBody('l2-rule');

    const tableNameMap = {
        'TV Retail': 'tv_retail_com',
        'HHP Retail': 'hhp_retail_com',
        'YouTube': 'youtube_videos',
        'Market': 'market_trend'
    };

    const marketRetailerMap = {
        'Trend': 'market_trend',
        'Comp Product': 'market_comp_product',
        'Comp Event': 'market_comp_event',
        'Forecast': 'openai_forecast_results'
    };

    let dbTableName = tableNameMap[tableName] || 'tv_retail_com';
    if (tableName === 'Market' && marketRetailerMap[retailer]) {
        dbTableName = marketRetailerMap[retailer];
    }

    try {
        const response = await fetch(`/layer2/api/format-rules/?table=${dbTableName}&retailer=${retailer}`);
        const data = await response.json();
        const rules = data.rules || [];

        let html = '<table class="rule-table"><thead><tr>';
        html += '<th>필드명</th><th>검증 규칙</th><th>허용 패턴/값</th>';
        html += '</tr></thead><tbody>';

        if (rules.length === 0) {
            html += '<tr><td colspan="3" style="text-align: center;">등록된 규칙이 없습니다.</td></tr>';
        } else {
            rules.forEach(rule => {
                html += `<tr>
                    <td class="rule-field">${rule.field}</td>
                    <td>${rule.description}</td>
                    <td><span class="rule-pattern">${rule.pattern}</span></td>
                </tr>`;
            });
        }

        html += '</tbody></table>';
        body.innerHTML = html;
    } catch (error) {
        console.error('형식 검증 규칙 로드 실패:', error);
        body.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">규칙 로드 실패</div>';
    }
}

function closeRuleModal() {
    AppModal.close('l2-rule');
}

// ==================== 사이드바 ====================
function onSubitemClick(parentSection, tableName) {
    const section = (window.LAYER2 && window.LAYER2.section) || 'dashboard';
    const date = getSelectedDate();
    const dateParam = date ? `?date=${date}` : '';

    if (section !== parentSection) {
        const sectionUrls = {
            null_validation: 'null',
            format_validation: 'format',
            anomaly_validation: 'anomaly'
        };
        const path = sectionUrls[parentSection] || '';
        const sep = dateParam ? '&' : '?';
        window.location.href = `/dx/layer2/${path}/${dateParam}${sep}focus=${encodeURIComponent(tableName)}`;
        return;
    }

    // 같은 섹션: ViewStack으로 해당 테이블 상세 표시
    showTableDetailByName(tableName);

    // 사이드바 active 갱신
    document.querySelectorAll('.sidebar-subitem').forEach(function(el) {
        el.classList.toggle('active', el.textContent.trim() === tableName);
    });
}

function scrollToTable(tableName) {
    const tableItems = document.querySelectorAll('.table-item');
    for (const tableEl of tableItems) {
        const nameEl = tableEl.querySelector('.table-name');
        if (nameEl && nameEl.textContent.trim() === tableName) {
            // 상위 validation-section 펼침
            const vSection = tableEl.closest('.validation-section');
            if (vSection) {
                const tablesContainer = vSection.querySelector('.tables-container');
                const vIcon = vSection.querySelector('.toggle-icon');
                if (tablesContainer && !tablesContainer.classList.contains('show')) {
                    tablesContainer.classList.add('show');
                    if (vIcon) vIcon.classList.add('expanded');
                }
            }
            // 테이블 상세 펼침
            const detail = tableEl.querySelector('.detail-container');
            const tIcon = tableEl.querySelector('.toggle-icon');
            if (detail && !detail.classList.contains('show')) {
                detail.classList.add('show');
                if (tIcon) tIcon.classList.add('expanded');
            }
            tableEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            tableEl.style.outline = '2px solid var(--layer-color)';
            setTimeout(() => { tableEl.style.outline = ''; }, 2000);
            return;
        }
    }
}

// 이름으로 테이블 상세 열기 (사이드바 서브아이템 클릭)
function showTableDetailByName(tableName) {
    if (!dxData || !dxData.validation_types || !dxData.validation_types[0]) return;
    const tables = dxData.validation_types[0].tables || [];
    const idx = tables.findIndex(t => t.table_name === tableName);
    if (idx >= 0) {
        // ViewStack 초기화 후 열기
        while (ViewStack.depth() > 0) ViewStack.pop();
        showTableDetail(idx);
    }
}

function handleFocusParam() {
    var target = currentFocusTable;
    if (!target) {
        const focus = new URLSearchParams(window.location.search).get('focus');
        if (focus) target = decodeURIComponent(focus);
    }

    if (target) {
        if (isInlineMode()) {
            showTableDetailByName(target);
        } else {
            scrollToTable(target);
        }
    }
}
