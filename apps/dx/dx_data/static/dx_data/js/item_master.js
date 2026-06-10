let currentTable = 'tv';
let currentPage = 1;
let PAGE_SIZE = 15; // 기본 15건으로 변경

let dxFilterBar = null;
let dataTable = null;
let pager = null;

// 변경 추적: { id: { is_product?: bool, is_checked?: bool } }
const pendingChanges = new Map();
// 원본 값 저장: { id: { is_product: bool, is_checked: bool } }
const originalValues = new Map();

document.addEventListener('DOMContentLoaded', function() {
    // 1. 공통 필터바 초기화
    dxFilterBar = new FilterBar('#dxFilterBar', {
        sticky: false,
        padding: '12px 20px',
        marginBottom: '0',
        controls: [
            { type: 'select', key: 'searchField', options: [
                { value: 'item', label: 'Item' },
                { value: 'sku', label: 'SKU' },
                { value: 'product_url', label: 'URL' }
            ]},
            { type: 'input', key: 'searchText', placeholder: '검색어 입력', onEnter: () => loadData(1) },
            { type: 'select', key: 'filterProduct', options: [
                { value: '', label: '제품여부 (전체)' },
                { value: 'true', label: '제품' },
                { value: 'false', label: '비제품' }
            ]},
            { type: 'select', key: 'filterChecked', options: [
                { value: '', label: '확인완료 (전체)' },
                { value: 'true', label: '확인완료' },
                { value: 'false', label: '미확인' }
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

    // 2. 공통 테이블 부분 초기화 (빈 껍데기)
    dataTable = new CommonTable('#tableContainer', {
        variant: 'list',
        showTotalCount: true, // 내장 총 건수 옵션 활성화
        pageSize: PAGE_SIZE,
        onPageSizeChange: function(newSize) {
            PAGE_SIZE = newSize;
            pager.options.pageSize = newSize;
            loadData(1);
        },
        columns: getTableColumns()
    }).render();

    // 3. 페이지네이션 초기화
    pager = new Pagination('#paginationContainer', {
        pageSize: PAGE_SIZE,
        maxVisible: 7,
        showInfo: false, // 건수는 이미 테이블에 표시되므로 끔
        margin: '0',
        padding: '0',
        border: 'none',
        onPageChange: function(page) {
            loadData(page);
        }
    });

    loadData(1);

    // 페이지 이탈 방지
    window.addEventListener('beforeunload', function(e) {
        if (pendingChanges.size > 0) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
});

function getTableColumns() {
    const extraColLabel = '화면크기';
    return [
        { key: 'no', label: 'No.', width: 60, align: 'center' },
        { key: 'item', label: 'Item' },
        { key: 'retailer', label: '리테일러', width: 120 },
        { key: 'sku', label: 'SKU', width: 150 },
        { key: 'extra', label: extraColLabel, width: 110 },
        { key: 'is_product', label: '제품여부', width: 130 },
        { key: 'is_checked', label: '확인완료', width: 130 },
        { key: 'url', label: 'URL', width: 120 }
    ];
}

function switchTab(table) {
    if (table !== 'tv') return;
    if (pendingChanges.size > 0) {
        if (!confirm('저장하지 않은 변경사항이 있습니다. 탭을 전환하시겠습니까?')) return;
        pendingChanges.clear();
        originalValues.clear();
        updateSaveBar();
    }
    currentTable = table;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.table === table);
    });
    
    // 테이블 헤더 (컬럼 텍스트) 갱신
    dataTable = new CommonTable('#tableContainer', {
        variant: 'list',
        showTotalCount: true,
        pageSize: PAGE_SIZE,
        onPageSizeChange: function(newSize) {
            PAGE_SIZE = newSize;
            pager.options.pageSize = newSize;
            loadData(1);
        },
        columns: getTableColumns()
    }).render();
    
    resetFilter();
}

function getFilterParams(page) {
    const field = dxFilterBar.getValue('searchField') || 'item';
    const input = dxFilterBar.getValue('searchText') || '';
    const isProduct = dxFilterBar.getValue('filterProduct') || '';
    const isChecked = dxFilterBar.getValue('filterChecked') || '';
    const account = dxFilterBar.getValue('filterAccount') || '';

    const params = new URLSearchParams({
        table: currentTable,
        page: page,
        page_size: PAGE_SIZE,
        search_field: field,
    });
    if (input) params.append('search', input);
    if (isProduct) params.append('is_product', isProduct);
    if (isChecked) params.append('is_checked', isChecked);
    if (account) params.append('account_name', account);

    return params.toString();
}

async function loadData(page) {
    if (!page) page = currentPage;
    currentPage = page;

    if (window.showLoading) showLoading('#tableContainer');

    try {
        const res = await fetch(`/dx/data/api/item-master/list/?${getFilterParams(page)}`);
        const data = await res.json();

        if (window.hideLoading) hideLoading();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        const startNo = (page - 1) * PAGE_SIZE;

        // 공통 테이블에 데이터 밀어넣기
        dataTable.renderBody(data.items, function(item, idx) {
            const pending = pendingChanges.get(item.id);
            const hasPending = !!pending;
            const isProduct = pending && 'is_product' in pending ? pending.is_product : item.is_product;
            const isChecked = pending && 'is_checked' in pending ? pending.is_checked : item.is_checked;
            
            const prodChecked = isProduct ? 'checked' : '';
            const chkChecked = isChecked ? 'checked' : '';
            const prodClass = isProduct ? 'yes' : 'no';
            const prodText = isProduct ? '제품' : '비제품';
            const chkClass = isChecked ? 'yes' : 'no';
            const chkText = isChecked ? '확인' : '미확인';
            const changedClass = hasPending ? ' changed' : '';
            
            const safeHref = window.safeUrl ? safeUrl(item.product_url) : item.product_url;
            let urlHtml = '-';
            if (safeHref) {
                const urlEscaped = window.esc ? esc(safeHref) : safeHref;
                const jsEscaped = window.escJs ? escJs(safeHref) : safeHref;
                urlHtml = `<a href="${urlEscaped}" target="_blank" class="url-link" title="${urlEscaped}">링크</a><button class="copy-btn" onclick="copyUrl('${jsEscaped}')" title="URL 복사"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg></button>`;
            }

            if (!originalValues.has(item.id)) {
                originalValues.set(item.id, { is_product: item.is_product, is_checked: item.is_checked });
            }

            const itemEscaped = window.esc ? esc(item.item || '') : (item.item || '');
            const accountEscaped = window.esc ? esc(item.account_name || '-') : (item.account_name || '-');
            const skuEscaped = window.esc ? esc(item.sku || '-') : (item.sku || '-');
            const extraEscaped = window.esc ? esc(item.extra_col || '-') : (item.extra_col || '-');

            return `
                <tr data-id="${item.id}" class="${changedClass}">
                    <td style="text-align:center;color:var(--text-secondary);">${startNo + idx + 1}</td>
                    <td><span class="item-name" title="${itemEscaped}">${itemEscaped}</span></td>
                    <td>${accountEscaped}</td>
                    <td>${skuEscaped}</td>
                    <td>${extraEscaped}</td>
                    <td>
                        <label class="toggle-switch">
                            <input type="checkbox" ${prodChecked} onchange="toggleField(${item.id}, 'is_product', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="product-label ${prodClass}" id="label_product_${item.id}">${prodText}</span>
                    </td>
                    <td>
                        <label class="toggle-switch">
                            <input type="checkbox" ${chkChecked} onchange="toggleField(${item.id}, 'is_checked', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="checked-label ${chkClass}" id="label_checked_${item.id}">${chkText}</span>
                    </td>
                    <td>${urlHtml}</td>
                </tr>
            `;
        });

        // 총 데이터 개수 수동 업데이트 (서버사이드 페이지네이션이므로)
        if (dataTable.countEl) {
            dataTable.countEl.innerHTML = `총 <strong>${data.total.toLocaleString()}</strong>건`;
        }

        // 페이지네이션 업데이트
        pager.render(data.total, page);

    } catch (e) {
        if (window.hideLoading) hideLoading();
        if (window.showToast) showToast('데이터 로드 실패: ' + e.message, 'error');
    }
}

function resetFilter() {
    dxFilterBar.setValue('searchText', '');
    dxFilterBar.setValue('filterProduct', '');
    dxFilterBar.setValue('filterChecked', '');
    dxFilterBar.setValue('filterAccount', '');
    dxFilterBar.setValue('searchField', 'item');
    loadData(1);
}

function toggleField(id, field, value) {
    const original = originalValues.get(id);
    if (!original) return;

    const pending = pendingChanges.get(id) || {};
    pending[field] = value;

    if (field === 'is_product') {
        if (value !== original.is_product) {
            pending.is_checked = true;
        } else {
            pending.is_checked = original.is_checked;
        }
        const chkInput = document.querySelector(`tr[data-id="${id}"] td:nth-child(7) input[type="checkbox"]`);
        if (chkInput) chkInput.checked = pending.is_checked;
        const chkLabel = document.getElementById(`label_checked_${id}`);
        if (chkLabel) {
            chkLabel.textContent = pending.is_checked ? '확인' : '미확인';
            chkLabel.className = `checked-label ${pending.is_checked ? 'yes' : 'no'}`;
        }
    }

    const allSame = Object.keys(pending).every(k => pending[k] === original[k]);
    if (allSame) {
        pendingChanges.delete(id);
    } else {
        pendingChanges.set(id, pending);
    }

    if (field === 'is_product') {
        const label = document.getElementById(`label_product_${id}`);
        if (label) {
            label.textContent = value ? '제품' : '비제품';
            label.className = `product-label ${value ? 'yes' : 'no'}`;
        }
    } else if (field === 'is_checked') {
        const label = document.getElementById(`label_checked_${id}`);
        if (label) {
            label.textContent = value ? '확인' : '미확인';
            label.className = `checked-label ${value ? 'yes' : 'no'}`;
        }
    }

    const row = document.querySelector(`tr[data-id="${id}"]`);
    if (row) {
        row.classList.toggle('changed', pendingChanges.has(id));
    }

    updateSaveBar();
}

function updateSaveBar() {
    const bar = document.getElementById('saveBar');
    const count = document.getElementById('saveCount');

    if (pendingChanges.size > 0) {
        bar.classList.add('show');
        count.textContent = `${pendingChanges.size}건 변경됨`;
    } else {
        bar.classList.remove('show');
    }
}

function cancelChanges() {
    pendingChanges.clear();
    originalValues.clear();
    updateSaveBar();
    loadData(currentPage);
}

async function saveChanges() {
    if (pendingChanges.size === 0) return;

    const changes = [];
    pendingChanges.forEach((val, id) => {
        const change = { id: id };
        if ('is_product' in val) change.is_product = val.is_product;
        if ('is_checked' in val) change.is_checked = val.is_checked;
        changes.push(change);
    });

    const btn = document.getElementById('saveBtn');
    btn.disabled = true;
    btn.textContent = '저장 중...';

    try {
        const res = await fetch('/dx/data/api/item-master/save/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                table: currentTable,
                changes: changes,
                user_id: currentUserId
            })
        });
        const data = await res.json();

        if (data.success) {
            if (window.showToast) showToast(`${data.updated}건 저장 완료`, 'success');
            pendingChanges.clear();
            originalValues.clear();
            updateSaveBar();
            loadData(currentPage);
        } else {
            if (window.showToast) showToast(data.error || '저장 실패', 'error');
        }
    } catch (e) {
        if (window.showToast) showToast('저장 중 오류 발생', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '저장';
    }
}

function copyUrl(url) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => { if(window.showToast) showToast('URL 복사 완료', 'success'); });
    } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        if(window.showToast) showToast('URL 복사 완료', 'success');
    }
}

function getCsrfToken() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
}
