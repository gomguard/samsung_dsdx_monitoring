/**
 * DS Layer 1 — 상세 모달
 * 리테일러 클릭 시 수집 데이터 상세 조회 + 페이징 + 정렬
 */

let currentTableName = '';
let currentPage = 1;
let modalPager = null;
let currentStartTime = null;
let currentEndTime = null;
let currentSortBy = 'crawl_strdatetime';
let currentSortOrder = 'asc';
let detailTable = null;

async function openDetail(tableName, retailerName, country, startTime = null, endTime = null) {
    currentTableName = tableName;
    currentPage = 1;
    currentStartTime = startTime;
    currentEndTime = endTime;
    currentSortBy = 'crawl_strdatetime';
    currentSortOrder = 'asc';

    const timeRange = startTime ? ` (${startTime} ~ ${endTime || '다음날'})` : '';
    document.getElementById('modalTitle').textContent = `${retailerName} (${country})${timeRange}`;
    document.getElementById('modalSubtitle').textContent = `테이블: ${tableName}`;
    document.getElementById('detailModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    if (!modalPager) {
        modalPager = new Pagination('#modalPagination', {
            variant: 'simple',
            pageSize: 50,
            showInfo: true,
            onPageChange: (page) => {
                currentPage = page;
                loadDetailData();
            }
        });
    }

    if (detailTable) {
        detailTable.setSort(currentSortBy, currentSortOrder);
    }

    await loadDetailData();
}

async function loadDetailData() {
    const date = document.getElementById('targetDate').value;

    document.getElementById('modalLoading').classList.remove('hidden');
    if (detailTable) {
        detailTable.getTable().querySelector('tbody').innerHTML = '';
    }

    try {
        let url = `/ds/layer1/api/table/?table=${currentTableName}&date=${date}&page=${currentPage}&page_size=50`;
        if (currentStartTime) {
            url += `&start_time=${encodeURIComponent(currentStartTime)}`;
        }
        if (currentEndTime) {
            url += `&end_time=${encodeURIComponent(currentEndTime)}`;
        }
        url += `&sort_by=${currentSortBy}&sort_order=${currentSortOrder}`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            detailTable = null;
            document.getElementById('modalContent').innerHTML = `<div class="loading">${esc(data.error)}</div>`;
        } else if (!data.data || data.data.length === 0) {
            detailTable = null;
            document.getElementById('modalContent').innerHTML = '<div class="empty-state">수집된 데이터가 없습니다</div>';
            modalPager.render(0, 1);
        } else {
            renderDetailTable(data);
            modalPager.render(data.total_count, currentPage);
        }
    } catch (error) {
        console.error('Error loading detail:', error);
        detailTable = null;
        document.getElementById('modalContent').innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }

    document.getElementById('modalLoading').classList.add('hidden');
}

function renderDetailTable(data) {
    if (!detailTable) {
        detailTable = new CommonTable('#modalContent', {
            variant: 'detail',
            columns: [
                { key: 'no', label: 'No', width: 50, align: 'center' },
                { key: 'crawl_strdatetime', label: '수집일시', width: 145, sortable: true },
                { key: 'image', label: '이미지', width: 80 },
                { key: 'title', label: '제품명', sortable: true },
                { key: 'retailprice', label: '가격', width: 90, sortable: true },
                { key: 'ships_from', label: 'Ships From', width: 140, sortable: true },
                { key: 'sold_by', label: 'Sold By', width: 140, sortable: true },
                { key: 'url', label: 'URL', width: 100, align: 'center' },
            ],
            onSort: (key, order) => {
                currentSortBy = key;
                currentSortOrder = order;
                currentPage = 1;
                loadDetailData();
            }
        }).render();
        detailTable.setSort(currentSortBy, currentSortOrder);
    }

    const startNo = (currentPage - 1) * 50 + 1;
    detailTable.renderBody(data.data, (item, i) => {
        const imgSrc = item.imageurl && item.imageurl.startsWith('http') ? item.imageurl : '';
        return `
            <tr>
                <td style="text-align: center; color: #64748b;">${startNo + i}</td>
                <td style="font-size: 12px; color: #6b7280; white-space: nowrap;">${item.crawl_datetime || '-'}</td>
                <td>${imgSrc ? `<img src="${imgSrc}" class="thumb" onerror="this.style.display='none'">` : '-'}</td>
                <td title="${item.title}">${item.title || '-'}</td>
                <td>${item.retailprice || '-'}</td>
                <td>${item.ships_from || '-'}</td>
                <td>${item.sold_by || '-'}</td>
                <td style="text-align:center; white-space:nowrap;">${item.producturl ? `<a href="${item.producturl}" target="_blank">보기</a>${AppButton.iconHtml('copy', `copyProductUrl('${escJs(item.producturl || '')}', this)`, { style: 'ghost', title: '링크 복사' })}` : '-'}</td>
            </tr>
        `;
    });
}

// copyProductUrl → ui.js 공통

function closeModal() {
    document.getElementById('detailModal').classList.add('hidden');
    document.body.style.overflow = '';
    detailTable = null;
    document.getElementById('modalContent').innerHTML = '';
}
