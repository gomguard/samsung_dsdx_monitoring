/* DS Layer3 — SKU 이상치 추적 */

let statsData = null;
let currentRetailer = '';
let currentFilter = 'all';
let currentPage = 1;
let totalPages = 1;

document.addEventListener('DOMContentLoaded', function() {
    new FilterBar('#controlsBar', {
        controls: [
            { type: 'date', key: 'targetDate', label: '조회 날짜' },
            { type: 'button', label: '조회', style: 'primary', onClick: function() { loadData(); } },
            { type: 'button', label: '전날', style: 'cancel', color: '#1a365d', border: '1px solid #1a365d', onClick: function() { setPrevDay('targetDate', loadData); } },
            { type: 'button', label: '다음날', style: 'cancel', color: '#1a365d', border: '1px solid #1a365d', onClick: function() { setNextDay('targetDate', loadData); } },
        ]
    }).render();

    document.getElementById('targetDate').value = getPersistedDate();
    loadData();
});

async function loadData() {
    var date = document.getElementById('targetDate').value;
    if (!validateQueryDate(date, 'targetDate')) {
        date = document.getElementById('targetDate').value;
    }
    setPersistedDate(date);
    document.getElementById('tableLoading').classList.remove('hidden');
    document.getElementById('tableContent').innerHTML = '';

    try {
        var response = await fetch('/ds/layer3/api/stats/?date=' + date + '&days=4');
        statsData = await response.json();
        updateSummary(statsData);
        renderTable(statsData);
    } catch (error) {
        console.error('Error loading data:', error);
        document.getElementById('tableContent').innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }

    document.getElementById('tableLoading').classList.add('hidden');
}

function updateSummary(data) {
    if (!data.summary) return;
    document.getElementById('totalTables').textContent = data.summary.total_tables || 0;
    document.getElementById('newTotal').textContent = (data.summary.new_skus || 0).toLocaleString();
    document.getElementById('recurringTotal').textContent = (data.summary.repeat_skus || 0).toLocaleString();


}

function renderTable(data) {
    var container = document.getElementById('tableContent');
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="loading">데이터가 없습니다.</div>';
        return;
    }

    var html = '<table class="retailer-table"><thead><tr>' +
        '<th>No</th><th>리테일러</th><th>지역</th><th>국가</th>' +
        '<th>신규 SKU</th><th>반복 SKU</th><th>전체</th><th>상태</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < data.results.length; i++) {
        var item = data.results[i];
        var rowClass = item.status === 'danger' ? 'row-danger' : '';
        var total = item.total_anomaly_skus || 0;

        html += '<tr class="' + rowClass + '" onclick="openDetail(\'' + esc(item.retailer) + '\')">' +
            '<td>' + item.no + '</td>' +
            '<td><span class="retailer-name">' + esc(item.retailer) + '</span></td>' +
            '<td>' + esc(item.region) + '</td>' +
            '<td><span class="country-badge">' + esc(item.country) + '</span></td>' +
            '<td class="error-count ' + (item.new_skus > 0 ? 'has-new' : 'no-error') + '">' + item.new_skus + '</td>' +
            '<td class="error-count ' + (item.repeat_skus > 0 ? 'has-error' : 'no-error') + '">' + item.repeat_skus + '</td>' +
            '<td class="error-count ' + (total > 0 ? 'has-error' : 'no-error') + '">' + total + '</td>' +
            '<td><span class="status-badge ' + item.status + '"><span class="status-dot"></span>' + (item.status === 'success' ? '정상' : '이상') + '</span></td>' +
            '</tr>';
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

function openDetail(retailer) {
    currentRetailer = retailer;
    currentFilter = 'all';
    currentPage = 1;

    document.getElementById('modalTitle').textContent = retailer + ' - SKU 이상치 상세';
    document.getElementById('modalSubtitle').textContent = '4일 분석';
    document.getElementById('detailModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    renderFilterSelector();
    loadDetailData();
}

function renderFilterSelector() {
    var container = document.getElementById('filterSelector');
    var filters = [
        { key: 'all', label: '전체' },
        { key: 'new', label: '신규 (1일)' },
        { key: 'repeat', label: '반복 (2일+)' }
    ];

    var html = '';
    for (var i = 0; i < filters.length; i++) {
        var f = filters[i];
        html += '<button class="' + (f.key === currentFilter ? 'active' : '') + '" onclick="selectFilter(\'' + f.key + '\')">' + f.label + '</button>';
    }
    container.innerHTML = html;
}

function selectFilter(filter) {
    currentFilter = filter;
    currentPage = 1;
    renderFilterSelector();
    loadDetailData();
}

async function loadDetailData() {
    var date = document.getElementById('targetDate').value;
    document.getElementById('modalLoading').classList.remove('hidden');
    document.getElementById('modalContent').innerHTML = '';

    try {
        var url = '/ds/layer3/api/sku-detail/?retailer=' + encodeURIComponent(currentRetailer) +
            '&date=' + date + '&days=4&filter=' + currentFilter +
            '&sort_by=consecutive_days&sort_order=desc&page=' + currentPage + '&page_size=50';
        var response = await fetch(url);
        var data = await response.json();

        if (data.error) {
            document.getElementById('modalContent').innerHTML = '<div class="loading">' + esc(data.error) + '</div>';
        } else {
            renderDetailTable(data);
            totalPages = data.total_pages;
            updatePagination(data);
        }
    } catch (error) {
        console.error('Error loading detail:', error);
        document.getElementById('modalContent').innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }

    document.getElementById('modalLoading').classList.add('hidden');
}

function renderDetailTable(data) {
    if (!data.data || data.data.length === 0) {
        document.getElementById('modalContent').innerHTML = '<div class="loading">이상치 SKU가 없습니다.</div>';
        return;
    }

    var html = '<div class="table-scroll-container"><table class="detail-table"><thead><tr>' +
        '<th style="width:120px">SKU</th>' +
        '<th style="width:60px">연속</th>' +
        '<th style="width:250px">제품명</th>' +
        '<th style="width:80px">가격</th>' +
        '<th style="width:80px">원인</th>' +
        '<th style="width:70px">URL</th></tr></thead><tbody>';

    for (var i = 0; i < data.data.length; i++) {
        var item = data.data[i];
        var consecutive = item.consecutive_days || 0;
        var badgeClass = consecutive >= 2 ? 'recurring' : 'new';
        var badgeText = consecutive > 3 ? '3일+' : (consecutive === 3 ? '3일' : (consecutive === 2 ? '2일' : '신규'));

        html += '<tr>' +
            '<td title="' + esc(item.retailersku) + '">' + esc(item.retailersku) + '</td>' +
            '<td><span class="recurring-badge ' + badgeClass + '">' + badgeText + '</span></td>' +
            '<td title="' + esc(item.latest_title) + '">' + esc(item.latest_title || '') + '</td>' +
            '<td>' + esc(item.latest_retailprice || '-') + '</td>' +
            '<td>' + esc(item.latest_cause || '-') + '</td>' +
            '<td>' + (item.latest_producturl ? '<a href="' + esc(item.latest_producturl) + '" target="_blank" title="새 탭에서 열기"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a> <span style="cursor:pointer" title="URL 복사" onclick="event.stopPropagation();copyProductUrl(\'' + esc(item.latest_producturl).replace(/'/g, "\\'") + '\')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></span>' : '-') + '</td>' +
            '</tr>';
    }

    html += '</tbody></table></div>';
    document.getElementById('modalContent').innerHTML = html;
}

function updatePagination(data) {
    var filterLabels = { all: '전체', 'new': '신규', repeat: '반복' };
    document.getElementById('modalInfo').textContent = filterLabels[currentFilter] + ': ' + (data.total_count || 0).toLocaleString() + '건';
    document.getElementById('pageInfo').textContent = currentPage + ' / ' + (data.total_pages || 1);
    document.getElementById('prevBtn').disabled = currentPage <= 1;
    document.getElementById('nextBtn').disabled = currentPage >= (data.total_pages || 1);
}

function prevPage() { if (currentPage > 1) { currentPage--; loadDetailData(); } }
function nextPage() { if (currentPage < totalPages) { currentPage++; loadDetailData(); } }

function closeModal() {
    document.getElementById('detailModal').classList.add('hidden');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });
