// Layer 2: 형식/NULL 검수 (DX 데이터 품질 모니터링)
let dxData = null;
let currentFocusTable = null;  // 현재 보고 있는 테이블 이름 (날짜 변경 시 유지용)

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
    return document.getElementById('detail-subtitle') || document.getElementById('modal-subtitle');
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

    if (isInlineMode()) {
        // 섹션 페이지: ViewStack 인라인 교체
        ViewStack.push(`
            <div class="inline-detail-view">
                <div class="inline-detail-header">
                    <div>
                        <div class="inline-detail-title">${titleText}</div>
                        <div class="inline-detail-subtitle" id="detail-subtitle">${subtitleText}</div>
                    </div>
                </div>
                <div id="detail-body"><div class="modal-loading">데이터 로딩 중...</div></div>
            </div>
        `);
    } else {
        // 대시보드: 모달
        const modal = document.getElementById('detail-modal');
        document.getElementById('modal-title').textContent = titleText;
        document.getElementById('modal-subtitle').textContent = subtitleText;
        document.getElementById('modal-body').innerHTML = '<div class="modal-loading">데이터 로딩 중...</div>';
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    const date = getSelectedDate();
    const tableParam = tableName === 'YouTube' ? 'youtube' :
                       tableName === 'YouTube Logs' ? 'youtube_logs' :
                       tableName === 'YouTube Comments' ? 'youtube_comments' :
                       tableName === 'YouTube Videos' ? 'youtube_videos' :
                       tableName === 'TV Retail' ? 'tv_retail' :
                       tableName === 'HHP Retail' ? 'hhp_retail' :
                       tableName === 'Market' ? 'market' :
                       tableName.toLowerCase().replace(' ', '_');

    modalState = { type, tableName, tableParam, retailer, count, currentPage: page, totalPages: 1, totalGroups: 0, nullFieldsData: null, selectedField: null };

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
            if (data.total_pages) {
                modalState.totalPages = data.total_pages;
                modalState.totalGroups = data.total_groups;
                modalState.currentPage = data.page || 1;
            }

            if (type === 'null') {
                modalState.nullFieldsData = data;
                renderNullFieldSummary(data, tableParam);
            } else {
                renderModalTable(type, data, tableParam);
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

    const filteredRecords = records.filter(record => {
        const nullFields = record.null_fields || [];
        return nullFields.includes(fieldName);
    });

    modalState.selectedField = fieldName;

    const isRetail = tableParam === 'tv_retail' || tableParam === 'hhp_retail';

    const fieldConfig = displayConfig[fieldName] || {};
    const selectColumns = fieldConfig.select_columns || [];
    const columnHeaders = fieldConfig.column_headers || {};

    const queryColumns = queryConfig[fieldName] || [];

    const columnWidths = {};

    columnWidths['NULL 필드'] = calcTextWidth('NULL 필드');

    filteredRecords.forEach(record => {
        const nullFieldsVal = record.null_fields?.join(', ') || '-';
        columnWidths['NULL 필드'] = Math.max(columnWidths['NULL 필드'], calcTextWidth(nullFieldsVal));

        selectColumns.forEach(col => {
            const headerName = columnHeaders[col] || col;
            if (!columnWidths[headerName]) {
                columnWidths[headerName] = calcTextWidth(headerName);
            }
            let val = record[col];
            if (col === 'product_url') {
                columnWidths[headerName] = Math.max(columnWidths[headerName], calcTextWidth('바로가기'));
            } else {
                if ((col.includes('_at') || col.includes('datetime')) && val) {
                    val = isRetail ? formatDateTime(val) : formatDateOnly(val);
                }
                columnWidths[headerName] = Math.max(columnWidths[headerName], calcTextWidth(String(val || '-')));
            }
        });
    });

    let html = '';

    if (!isInlineMode()) {
        html += `<div class="modal-toolbar">
            <button class="btn-back" onclick="backToNullFieldSummary()">← 뒤로가기</button>
            <div class="modal-date-picker">
                <label>조회 날짜:</label>
                <input type="date" id="null-modal-date" value="${date}"
                    onchange="reloadNullData(this.value)">
            </div>
        </div>`;
        html += `<h4 style="margin-bottom: 12px; font-size: 15px;">${fieldName} NULL 오류 (${filteredRecords.length}건)</h4>`;
    }

    if (filteredRecords.length === 0) {
        html += '<p>해당 필드의 NULL 오류 데이터가 없습니다.</p>';
    } else {
        const items = [...new Set(filteredRecords.map(r => r.item).filter(Boolean))].sort();
        const ids = filteredRecords.map(r => r.id).filter(Boolean);

        if (isRetail) {
            const tblName = tableParam === 'tv_retail' ? 'tv_retail_com' : 'hhp_retail_com';
            const retailerName = modalState.retailer || '';
            const queryCols = queryColumns.length > 0 ? queryColumns.join(', ') : '*';

            if (items.length > 0) {
                const inClause = items.map(item => `'${item}'`).join(', ');
                const itemListDisplay = items.join(', ');

                const query3Days = `SELECT ${queryCols}
FROM ${tblName}
WHERE account_name = '${retailerName}'
  AND item IN (${inClause})
  AND DATE(${dateColumn}::timestamp) >= DATE('${date}') - INTERVAL '2 days'
  AND DATE(${dateColumn}::timestamp) <= DATE('${date}')
ORDER BY item, ${dateColumn} ASC;`;

                html += `
                    <div class="item-query-section">
                        <div class="item-list-box">
                            <div class="item-copy-header">
                                <span class="item-copy-title">Item 목록 (${items.length}개)</span>
                                <button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button>
                            </div>
                            <div class="item-copy-content">${itemListDisplay}</div>
                        </div>
                        <div class="query-box">
                            <div class="item-copy-header">
                                <span class="item-copy-title">3일치 조회 쿼리 (${date} 기준)</span>
                                <button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button>
                            </div>
                            <pre class="query-content">${query3Days}</pre>
                        </div>
                    </div>
                `;
            } else if (ids.length > 0) {
                const idInClause = ids.join(', ');
                const idListDisplay = ids.join(', ');

                const queryById = `SELECT ${queryCols}
FROM ${tblName}
WHERE id IN (${idInClause});`;

                html += `
                    <div class="item-query-section">
                        <div class="item-list-box">
                            <div class="item-copy-header">
                                <span class="item-copy-title">ID 목록 (${ids.length}개)</span>
                                <button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button>
                            </div>
                            <div class="item-copy-content">${idListDisplay}</div>
                        </div>
                        <div class="query-box">
                            <div class="item-copy-header">
                                <span class="item-copy-title">ID 기반 조회 쿼리</span>
                                <button class="btn-copy" onclick="copyToClipboard(this.parentElement.nextElementSibling)">복사</button>
                            </div>
                            <pre class="query-content">${queryById}</pre>
                        </div>
                    </div>
                `;
            }
        }

        html += '<div class="modal-table-wrapper"><table class="modal-table"><thead><tr>';

        if (selectColumns.length > 0) {
            selectColumns.forEach(col => {
                const headerName = columnHeaders[col] || col;
                const colWidth = columnWidths[headerName] || 100;
                html += `<th style="width: ${colWidth}px;">${headerName}<div class="resize-handle"></div></th>`;
            });
        } else {
            html += `<th style="width: ${columnWidths['NULL 필드']}px;">NULL 필드<div class="resize-handle"></div></th>`;
            html += '<th style="width: 80px;">ID<div class="resize-handle"></div></th>';
            html += '<th style="width: 200px;">Item<div class="resize-handle"></div></th>';
            html += '<th style="width: 120px;">수집일<div class="resize-handle"></div></th>';
            html += '<th style="width: 80px;">URL<div class="resize-handle"></div></th>';
        }

        html += '</tr></thead><tbody>';

        filteredRecords.forEach(record => {
            html += '<tr>';

            if (selectColumns.length > 0) {
                selectColumns.forEach(col => {
                    let val = record[col];
                    if (col === 'product_url') {
                        const urlLink = val
                            ? `<a href="${val}" target="_blank" style="color: #2563eb;">바로가기</a>`
                            : '-';
                        html += `<td>${urlLink}</td>`;
                    } else {
                        if ((col.includes('_at') || col.includes('datetime')) && val) {
                            val = isRetail ? formatDateTime(val) : formatDateOnly(val);
                        }
                        const isNull = record.null_fields?.includes(col);
                        if (isNull) {
                            html += `<td class="null-value" title="${val || 'NULL'}">${val || 'NULL'}</td>`;
                        } else {
                            html += `<td title="${val || '-'}">${val || '-'}</td>`;
                        }
                    }
                });
            } else {
                const collectedAt = record.crawl_datetime || record.collected_at;
                const urlLink = record.product_url
                    ? `<a href="${record.product_url}" target="_blank" style="color: #2563eb;">바로가기</a>`
                    : '-';
                html += `<td class="null-value">${record.null_fields?.join(', ') || '-'}</td>`;
                html += `<td>${record.id || '-'}</td>`;
                html += `<td>${record.item || '-'}</td>`;
                html += `<td>${formatDateTime(collectedAt)}</td>`;
                html += `<td>${urlLink}</td>`;
            }

            html += '</tr>';
        });

        html += '</tbody></table></div>';
    }

    if (isInlineMode()) {
        const fieldTitle = `${fieldName} NULL 오류 (${filteredRecords.length}건)`;
        const fieldSubtitle = `${modalState.tableName} | ${modalState.retailer}`;
        const wrapper = `
            <div class="inline-detail-view">
                <div class="inline-detail-header">
                    <div>
                        <div class="inline-detail-title">${fieldTitle}</div>
                        <div class="inline-detail-subtitle" id="detail-subtitle">${fieldSubtitle}</div>
                    </div>
                </div>
                <div id="detail-body">${html}</div>
            </div>
        `;
        if (pushStack) {
            ViewStack.push(wrapper);
        } else {
            const container = ViewStack.getContainer();
            if (container) container.innerHTML = wrapper;
        }
    } else {
        body.innerHTML = html;
    }
    initColumnResize();
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

function calcTextWidth(text) {
    if (!text) return 60;
    const str = String(text);
    const padding = 32;
    const minWidth = 60;
    const maxWidth = 300;

    let width = 0;
    for (const char of str) {
        if (/[가-힣]/.test(char)) {
            width += 14;
        } else if (/[A-Z]/.test(char)) {
            width += 10;
        } else if (char === '_') {
            width += 7;
        } else {
            width += 8;
        }
    }
    width += padding;

    return Math.max(minWidth, Math.min(maxWidth, width));
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

async function reloadNullData(date) {
    const body = getDetailBody();
    body.innerHTML = '<div class="modal-loading">데이터를 불러오는 중...</div>';

    const { tableParam, retailer, selectedField } = modalState;

    try {
        const response = await fetch(`/dx/layer2/api/null-detail/?table=${tableParam}&retailer=${retailer}&date=${date}`);
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

function calcColumnWidth(colName) {
    const padding = 40;
    const minWidth = 80;
    const maxWidth = 250;

    let width = 0;
    for (const char of colName) {
        if (/[가-힣]/.test(char)) {
            width += 16;
        } else if (/[A-Z]/.test(char)) {
            width += 12;
        } else if (char === '_') {
            width += 8;
        } else {
            width += 10;
        }
    }
    width += padding;

    return Math.max(minWidth, Math.min(maxWidth, width));
}

function renderModalTable(type, data, tableParam) {
    const body = getDetailBody();
    const retailer = modalState.retailer;

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

    let html = '<div class="modal-table-wrapper"><table class="modal-table"><thead><tr>';

    const columnNames = data.column_names || [];

    if (type === 'null') {
        if (columnNames.length > 0) {
            html += '<th style="width: 60px;">ID<div class="resize-handle"></div></th>';
            html += `<th style="width: ${calcColumnWidth('NULL 필드')}px;">NULL 필드<div class="resize-handle"></div></th>`;
            columnNames.forEach(col => {
                const headerName = col === 'product_url' ? 'URL' : col;
                const colWidth = calcColumnWidth(headerName);
                html += `<th style="width: ${colWidth}px;">${headerName}<div class="resize-handle"></div></th>`;
            });
        } else if (tableParam === 'youtube') {
            html += '<th style="width: 25%;">NULL 필드<div class="resize-handle"></div></th><th style="width: 30%;">COMMENT_ID<div class="resize-handle"></div></th><th style="width: 25%;">VIDEO_ID<div class="resize-handle"></div></th><th style="width: 20%;">수집일<div class="resize-handle"></div></th>';
        } else if (tableParam.startsWith('market_')) {
            html += '<th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 150px;">NULL 필드<div class="resize-handle"></div></th><th style="width: 200px;">Item<div class="resize-handle"></div></th><th style="width: 120px;">수집일<div class="resize-handle"></div></th>';
        } else {
            html += '<th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 150px;">NULL 필드<div class="resize-handle"></div></th><th style="width: 200px;">Item<div class="resize-handle"></div></th><th style="width: 120px;">수집일<div class="resize-handle"></div></th><th style="width: 80px;">URL<div class="resize-handle"></div></th>';
        }
    } else if (type === 'format') {
        if (tableParam === 'youtube') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 120px;">식별자<div class="resize-handle"></div></th><th style="width: 120px;">오류 필드<div class="resize-handle"></div></th><th style="width: 150px;">오류 값<div class="resize-handle"></div></th><th style="width: 120px;">규칙<div class="resize-handle"></div></th><th style="min-width: 150px;">위배 사유<div class="resize-handle"></div></th>';
        } else {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 150px;">Item<div class="resize-handle"></div></th><th style="width: 120px;">오류 필드<div class="resize-handle"></div></th><th style="width: 150px;">오류 값<div class="resize-handle"></div></th><th style="width: 120px;">규칙<div class="resize-handle"></div></th><th style="min-width: 150px;">위배 사유<div class="resize-handle"></div></th><th style="width: 120px;">수집일<div class="resize-handle"></div></th><th style="width: 80px;">URL<div class="resize-handle"></div></th>';
        }
    } else if (type === 'duplicate') {
        if (tableParam === 'youtube_logs') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 150px;">Keyword<div class="resize-handle"></div></th><th style="width: 100px;">Category<div class="resize-handle"></div></th><th style="width: 180px;">중복사유<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else if (tableParam === 'youtube_comments') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 120px;">Video ID<div class="resize-handle"></div></th><th style="width: 140px;">Comment ID<div class="resize-handle"></div></th><th style="width: 150px;">중복사유<div class="resize-handle"></div></th><th style="min-width: 300px;">댓글 내용<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else if (tableParam === 'youtube_videos') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 120px;">Video ID<div class="resize-handle"></div></th><th style="width: 100px;">Keyword<div class="resize-handle"></div></th><th style="width: 180px;">중복사유<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="min-width: 200px;">제목<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else if (tableParam === 'market_trend') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 150px;">Keyword<div class="resize-handle"></div></th><th style="width: 180px;">중복사유<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 100px;">Article수<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else if (tableParam === 'market_product') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 100px;">Batch ID<div class="resize-handle"></div></th><th style="width: 150px;">Samsung Series<div class="resize-handle"></div></th><th style="width: 100px;">Comp Brand<div class="resize-handle"></div></th><th style="width: 150px;">Comp Series<div class="resize-handle"></div></th><th style="width: 150px;">중복사유<div class="resize-handle"></div></th><th style="width: 60px;">ID<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else if (tableParam === 'market_event') {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 100px;">Batch ID<div class="resize-handle"></div></th><th style="width: 100px;">Comp Brand<div class="resize-handle"></div></th><th style="width: 150px;">Comp SKU<div class="resize-handle"></div></th><th style="width: 150px;">중복사유<div class="resize-handle"></div></th><th style="width: 60px;">ID<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th>';
        } else {
            html += '<th style="width: 50px;">No<div class="resize-handle"></div></th><th style="width: 150px;">Item<div class="resize-handle"></div></th><th style="width: 100px;">시간대<div class="resize-handle"></div></th><th style="width: 150px;">중복사유<div class="resize-handle"></div></th><th style="width: 80px;">ID<div class="resize-handle"></div></th><th style="width: 100px;">Page Type<div class="resize-handle"></div></th><th style="width: 140px;">수집시각<div class="resize-handle"></div></th><th style="width: 80px;">Rank<div class="resize-handle"></div></th><th style="width: 80px;">URL<div class="resize-handle"></div></th>';
        }
    }

    html += '</tr></thead><tbody>';

    let rowNumber = 0;
    records.forEach((record, recordIdx) => {
        if (type === 'null') {
            html += '<tr>';
            const collectedAt = record.crawl_datetime || record.collected_at;

            if (columnNames.length > 0) {
                html += `<td>${record.id || '-'}</td>`;
                html += `<td class="null-value">${record.null_fields?.join(', ') || '-'}</td>`;
                const isRetail = tableParam === 'tv_retail' || tableParam === 'hhp_retail';
                columnNames.forEach(col => {
                    let val = record[col];
                    if (col === 'product_url') {
                        const urlLink = val
                            ? `<a href="${val}" target="_blank" style="color: #2563eb;">바로가기</a>`
                            : '-';
                        html += `<td>${urlLink}</td>`;
                    } else {
                        if ((col.includes('_at') || col.includes('datetime')) && val) {
                            val = isRetail ? formatDateTime(val) : formatDateOnly(val);
                        }
                        const isNull = record.null_fields?.includes(col);
                        if (isNull) {
                            html += `<td class="null-value" title="${val || 'NULL'}">${val || 'NULL'}</td>`;
                        } else {
                            html += `<td title="${val || '-'}">${val || '-'}</td>`;
                        }
                    }
                });
            } else if (tableParam === 'youtube') {
                html += `
                    <td class="null-value">${record.null_fields?.join(', ') || '-'}</td>
                    <td title="${record.comment_id || '-'}">${record.comment_id || '-'}</td>
                    <td title="${record.video_id || '-'}">${record.video_id || '-'}</td>
                    <td>${formatDateOnly(collectedAt)}</td>
                `;
            } else if (tableParam.startsWith('market_')) {
                html += `
                    <td>${record.id || '-'}</td>
                    <td class="null-value">${record.null_fields?.join(', ') || '-'}</td>
                    <td>${record.item || '-'}</td>
                    <td>${formatDateTime(collectedAt)}</td>
                `;
            } else {
                const urlLink = record.product_url
                    ? `<a href="${record.product_url}" target="_blank" style="color: #2563eb;">바로가기</a>`
                    : '-';
                html += `
                    <td>${record.id || '-'}</td>
                    <td class="null-value">${record.null_fields?.join(', ') || '-'}</td>
                    <td>${record.item || '-'}</td>
                    <td>${formatDateTime(collectedAt)}</td>
                    <td>${urlLink}</td>
                `;
            }
            html += '</tr>';
        } else if (type === 'format') {
            const errors = record.errors || [];
            if (errors.length === 0) return;

            rowNumber++;
            const rowspan = errors.length;

            errors.forEach((err, errIdx) => {
                html += '<tr>';

                if (tableParam === 'youtube') {
                    const identifier = record.keyword || record.video_id || record.comment_type || '-';
                    if (errIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.id}</td>
                            <td rowspan="${rowspan}">${identifier}</td>
                        `;
                    }
                    html += `
                        <td class="null-value">${err.field || '-'}</td>
                        <td>${err.value || '-'}</td>
                        <td>${err.rule || '-'}</td>
                        <td>${err.reason || '-'}</td>
                    `;
                } else {
                    const urlLink = record.product_url
                        ? `<a href="${record.product_url}" target="_blank" style="color: #2563eb;">바로가기</a>`
                        : '-';
                    const collectedAt = record.crawl_datetime || record.collected_at;
                    if (errIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.id}</td>
                            <td rowspan="${rowspan}">${record.item || '-'}</td>
                        `;
                    }
                    html += `
                        <td class="null-value">${err.field || '-'}</td>
                        <td>${err.value || '-'}</td>
                        <td>${err.rule || '-'}</td>
                        <td>${err.reason || '-'}</td>
                    `;
                    if (errIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}">${formatDateTime(collectedAt)}</td>
                            <td rowspan="${rowspan}">${urlLink}</td>
                        `;
                    }
                }

                html += '</tr>';
            });
        } else if (type === 'duplicate') {
            rowNumber++;
            const dupRecords = record.records || [];
            const rowspan = dupRecords.length;

            dupRecords.forEach((rec, recIdx) => {
                html += '<tr>';

                if (tableParam === 'youtube_logs') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.keyword || '-'}</td>
                            <td rowspan="${rowspan}">${record.category || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else if (tableParam === 'youtube_comments') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}" title="${record.video_id || ''}">${record.video_id || '-'}</td>
                            <td rowspan="${rowspan}" title="${record.comment_id || ''}">${record.comment_id || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td style="white-space: normal; word-break: break-word;">${rec.comment_text_display || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else if (tableParam === 'youtube_videos') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.video_id || '-'}</td>
                            <td rowspan="${rowspan}">${record.keyword || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${rec.title || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else if (tableParam === 'market_trend') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.keyword || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${rec.total_article_number || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else if (tableParam === 'market_product') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.batch_id || '-'}</td>
                            <td rowspan="${rowspan}">${record.samsung_series_name || '-'}</td>
                            <td rowspan="${rowspan}">${record.comp_brand || '-'}</td>
                            <td rowspan="${rowspan}">${record.comp_series_name || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else if (tableParam === 'market_event') {
                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.batch_id || '-'}</td>
                            <td rowspan="${rowspan}">${record.comp_brand || '-'}</td>
                            <td rowspan="${rowspan}">${record.comp_sku_name || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${formatDateTime(rec.created_at)}</td>
                    `;
                } else {
                    const urlLink = rec.product_url
                        ? `<a href="${rec.product_url}" target="_blank" style="color: #2563eb;">바로가기</a>`
                        : '-';
                    const rank = rec.rank !== undefined ? (rec.rank || '-') : (rec.main_rank || rec.bsr_rank || '-');

                    if (recIdx === 0) {
                        html += `
                            <td rowspan="${rowspan}" style="text-align: center; font-weight: 500;">${rowNumber}</td>
                            <td rowspan="${rowspan}">${record.item || '-'}</td>
                            <td rowspan="${rowspan}">${record.period || '-'}</td>
                            <td rowspan="${rowspan}" style="color: #dc2626; font-size: 12px;">${record.reason || '-'}</td>
                        `;
                    }
                    html += `
                        <td>${rec.id || '-'}</td>
                        <td>${rec.page_type || '-'}</td>
                        <td>${formatDateTime(rec.crawl_datetime)}</td>
                        <td>${rank}</td>
                        <td>${urlLink}</td>
                    `;
                }
                html += '</tr>';
            });
        }
    });

    html += '</tbody></table></div>';

    // 페이지네이션
    if (modalState.totalPages > 1) {
        const { currentPage, totalPages, totalGroups } = modalState;
        html += `
            <div class="modal-pagination">
                <div class="pagination-info">
                    총 ${totalGroups.toLocaleString()}개 중복 그룹 중 ${records.length}개 표시 (${currentPage}/${totalPages} 페이지)
                </div>
                <div class="pagination-buttons">
                    <button class="pagination-btn" onclick="goToPage(1)" ${currentPage === 1 ? 'disabled' : ''}>«</button>
                    <button class="pagination-btn" onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>‹</button>
                    <span class="pagination-current">${currentPage} / ${totalPages}</span>
                    <button class="pagination-btn" onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>›</button>
                    <button class="pagination-btn" onclick="goToPage(${totalPages})" ${currentPage === totalPages ? 'disabled' : ''}>»</button>
                </div>
            </div>
        `;
    } else {
        const total = data.total || records.length;
        if (total > records.length) {
            html += `<p style="margin-top: 16px; color: var(--text-secondary); font-size: 13px;">
                총 ${total.toLocaleString()}건 중 ${records.length}건 표시
            </p>`;
        }
    }

    body.innerHTML = html;
    initColumnResize();
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;

    const modal = document.getElementById('detail-modal');
    modal.classList.remove('show');
    document.body.style.overflow = '';
}

// 검증규칙 모달
async function openRuleModal(tableName, retailer) {
    const modal = document.getElementById('rule-modal');
    const title = document.getElementById('rule-modal-title');
    const subtitle = document.getElementById('rule-modal-subtitle');
    const body = document.getElementById('rule-modal-body');

    title.textContent = `${retailer} - 형식 검증 규칙`;
    subtitle.textContent = `${tableName} | 필드별 검증 규칙`;

    body.innerHTML = '<div style="text-align: center; padding: 20px;">로딩 중...</div>';
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';

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

function closeRuleModal(event) {
    if (event && event.target !== event.currentTarget) return;

    const modal = document.getElementById('rule-modal');
    modal.classList.remove('show');
    document.body.style.overflow = '';
}

// ESC 키로 모달 닫기
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
        closeRuleModal();
    }
});

// 열 크기 조정 기능
function initColumnResize() {
    const table = document.querySelector('.modal-table');
    if (!table) return;

    const wrapper = table.closest('.modal-table-wrapper');
    const headers = table.querySelectorAll('th');
    const minColWidth = 80;

    const wrapperWidth = wrapper.offsetWidth;
    table.style.width = wrapperWidth + 'px';

    headers.forEach(th => {
        const width = th.offsetWidth;
        th.style.width = width + 'px';
    });

    headers.forEach((th, index) => {
        const handle = th.querySelector('.resize-handle');
        if (!handle) return;

        let startX, startWidth, tableStartWidth;

        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            startX = e.pageX;
            startWidth = th.offsetWidth;
            tableStartWidth = table.offsetWidth;

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            const diff = e.pageX - startX;
            const newWidth = Math.max(minColWidth, startWidth + diff);
            const widthDiff = newWidth - startWidth;

            th.style.width = newWidth + 'px';

            const newTableWidth = tableStartWidth + widthDiff;
            table.style.width = Math.max(wrapperWidth, newTableWidth) + 'px';
        }

        function onMouseUp() {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
    });
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
        if (ViewStack.depth() > 0) ViewStack.pop();
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
