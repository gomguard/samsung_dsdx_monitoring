let currentTable = 'tv';
let currentPage = 1;
let PAGE_SIZE = 50;
let dxFilterBar = null;
let dataTable = null;
let pager = null;

const FIELD_LABELS = {
    'is_product': '제품여부',
    'is_checked': '확인완료'
};

function formatValue(field, val) {
    if (field === 'is_product') {
        return val === 'True' ? '<span class="value-badge true-val">제품</span>' : '<span class="value-badge false-val">비제품</span>';
    }
    if (field === 'is_checked') {
        return val === 'True' ? '<span class="value-badge true-val">확인완료</span>' : '<span class="value-badge false-val">미확인</span>';
    }
    return window.esc ? esc(val || '') : (val || '-');
}

document.addEventListener('DOMContentLoaded', function() {
    // 날짜 기본값: 오늘
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    const todayStr = `${yyyy}-${mm}-${dd}`;

    dxFilterBar = new FilterBar('#dxFilterBar', {
        sticky: false,
        padding: '12px 20px',
        marginBottom: '0',
        controls: [
            { type: 'date', key: 'filterDate', default: todayStr },
            { type: 'input', key: 'filterItem', placeholder: 'item 검색...', onEnter: () => loadData(1) },
            { type: 'select', key: 'filterField', options: [
                { value: '', label: '변경 필드 (전체)' },
                { value: 'is_product', label: '제품여부' },
                { value: 'is_checked', label: '확인완료' }
            ]},
            { type: 'select', key: 'filterAccount', options: [
                { value: '', label: '리테일러 (전체)' },
                { value: 'Amazon', label: 'Amazon' },
                { value: 'Bestbuy', label: 'Bestbuy' },
                { value: 'Walmart', label: 'Walmart' }
            ]},
            { type: 'button', label: '조회', style: 'primary', onClick: () => loadData(1) },
            { type: 'button', label: '해제', style: 'cancel', onClick: () => resetFilter() }
        ]
    }).render();

    dataTable = new CommonTable('#tableContainer', {
        variant: 'list',
        showTotalCount: true,
        pageSize: PAGE_SIZE,
        onPageSizeChange: function(newSize) {
            PAGE_SIZE = newSize;
            pager.options.pageSize = newSize;
            loadData(1);
        },
        columns: [
            { key: 'no', label: 'No.', width: 60, align: 'center' },
            { key: 'item', label: 'item' },
            { key: 'account_name', label: '리테일러', width: 120 },
            { key: 'field_name', label: '변경 필드', width: 120 },
            { key: 'old_value', label: '이전 값', width: 100 },
            { key: 'new_value', label: '변경 값', width: 100 },
            { key: 'changed_id', label: '수정자', width: 100 },
            { key: 'changed_at', label: '수정일시', width: 150 }
        ]
    }).render();

    pager = new Pagination('#paginationContainer', {
        pageSize: PAGE_SIZE,
        maxVisible: 7,
        showInfo: false,
        margin: '0',
        padding: '0',
        border: 'none',
        onPageChange: function(page) {
            loadData(page);
        }
    });

    loadData(1);
});

function switchTab(table) {
    if (table !== 'tv') return;
    currentTable = table;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.table === table);
    });
    
    // 테이블 다시 등록, 컬럼 크기나 속성 초기화를 위해
    dataTable = new CommonTable('#tableContainer', {
        variant: 'list',
        showTotalCount: true,
        pageSize: PAGE_SIZE,
        onPageSizeChange: function(newSize) {
            PAGE_SIZE = newSize;
            pager.options.pageSize = newSize;
            loadData(1);
        },
        columns: [
            { key: 'no', label: 'No.', width: 60, align: 'center' },
            { key: 'item', label: 'item' },
            { key: 'account_name', label: '리테일러', width: 120 },
            { key: 'field_name', label: '변경 필드', width: 120 },
            { key: 'old_value', label: '이전 값', width: 100 },
            { key: 'new_value', label: '변경 값', width: 100 },
            { key: 'changed_id', label: '수정자', width: 100 },
            { key: 'changed_at', label: '수정일시', width: 150 }
        ]
    }).render();

    resetFilter();
}

async function loadData(page) {
    if (!page) page = currentPage;
    currentPage = page;

    if (window.showLoading) showLoading('#tableContainer');

    const date = dxFilterBar.getValue('filterDate') || '';
    const item = dxFilterBar.getValue('filterItem') || '';
    const field = dxFilterBar.getValue('filterField') || '';
    const account = dxFilterBar.getValue('filterAccount') || '';

    const params = new URLSearchParams({
        table: currentTable,
        page: page,
        page_size: PAGE_SIZE,
    });
    if (date) params.append('date', date);
    if (item) params.append('item', item);
    if (field) params.append('field', field);
    if (account) params.append('account_name', account);

    try {
        const res = await fetch(`/dx/data/api/item-master/history/?${params}`);
        const data = await res.json();

        if (window.hideLoading) hideLoading();

        if (data.error) {
            if (window.showToast) showToast(data.error, 'error');
            return;
        }

        renderCopyBar(data.unique_items || {});

        const startNo = (page - 1) * PAGE_SIZE;

        dataTable.renderBody(data.items, function(item, idx) {
            const fieldLabel = FIELD_LABELS[item.field_name] || item.field_name;
            const fieldClass = window.esc ? esc(item.field_name) : item.field_name;
            
            const itemEscaped = window.esc ? esc(item.item || '-') : (item.item || '-');
            const accountEscaped = window.esc ? esc(item.account_name || '-') : (item.account_name || '-');
            const changedIdEscaped = window.esc ? esc(item.changed_id || '-') : (item.changed_id || '-');
            const changedAtEscaped = window.esc ? esc(item.changed_at) : item.changed_at;

            return `
                <tr data-id="${item.id}">
                    <td style="text-align:center;color:var(--text-secondary);">${startNo + idx + 1}</td>
                    <td>${itemEscaped}</td>
                    <td>${accountEscaped}</td>
                    <td><span class="field-badge ${fieldClass}">${window.esc ? esc(fieldLabel) : fieldLabel}</span></td>
                    <td>${formatValue(item.field_name, item.old_value)}</td>
                    <td>${formatValue(item.field_name, item.new_value)}</td>
                    <td>${changedIdEscaped}</td>
                    <td style="white-space:nowrap;color:var(--text-secondary);">${changedAtEscaped}</td>
                </tr>
            `;
        });

        if (dataTable.countEl) {
            dataTable.countEl.innerHTML = `총 <strong>${(data.total || 0).toLocaleString()}</strong>건`;
        }
        pager.render(data.total, page);

    } catch (e) {
        if (window.hideLoading) hideLoading();
        if (window.showToast) showToast('데이터 로드 실패: ' + e.message, 'error');
    }
}

let cachedUniqueItems = {};

function renderCopyBar(uniqueItems) {
    cachedUniqueItems = uniqueItems;
    const bar = document.getElementById('copyBar');
    const retailers = Object.keys(uniqueItems).sort();

    if (retailers.length === 0) {
        bar.innerHTML = '';
        return;
    }

    const allItems = retailers.flatMap(r => uniqueItems[r]);
    const copyIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';

    let html = '<div class="copy-bar">';
    html += `<button class="copy-chip" onclick="copyItems('all')">
        ${copyIcon} <span class="chip-label">전체</span> <span class="chip-count">(${allItems.length})</span>
    </button>`;
    retailers.forEach(r => {
        const count = uniqueItems[r].length;
        html += `<button class="copy-chip" onclick="copyItems('${r.replace(/'/g, "\\'")}')">
            ${copyIcon} <span class="chip-label">${window.esc ? esc(r) : r}</span> <span class="chip-count">(${count})</span>
        </button>`;
    });
    html += '</div>';
    bar.innerHTML = html;
}

function copyItems(retailer) {
    let items;
    if (retailer === 'all') {
        items = Object.keys(cachedUniqueItems).sort().flatMap(r => cachedUniqueItems[r]);
    } else {
        items = cachedUniqueItems[retailer] || [];
    }
    const text = items.join(', ');
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => window.showToast && showToast(`${items.length}개 item 복사 완료`, 'success'));
    } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        if (window.showToast) showToast(`${items.length}개 item 복사 완료`, 'success');
    }
}

function resetFilter() {
    // dxFilterBar의 초기화 메서드 혹은 직접 밸류 클리어
    dxFilterBar.setValue('filterItem', '');
    dxFilterBar.setValue('filterField', '');
    dxFilterBar.setValue('filterAccount', '');
    // 날짜는 놔두거나 오늘 날짜로 세팅해야 하지만 그냥 두기도 함
    loadData(1);
}
