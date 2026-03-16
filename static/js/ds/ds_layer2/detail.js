let currentTableName = '';
let currentErrorType = 'title_null';
let currentPage = 1;
let modalPager = null;
let currentRetailerData = {};
let currentStartTime = null;
let currentEndTime = null;
let currentSortBy = 'crawl_strdatetime';
let currentSortOrder = 'asc';
let currentDetailData = []; // 현재 보이는 상세 데이터
let currentRetailerName = ''; // 현재 리테일러 이름
let currentCountry = ''; // 현재 국가

function renderNullTable(data) {
    const container = document.getElementById('nullTableContent');

    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="loading">데이터가 없습니다.</div>';
        return;
    }

    let html = `
        <table class="retailer-table" id="nullTable">
            <thead>
                <tr>
                    ${!(reportStatus.is_closed || currentBatchView === 'all') ? '<th class="text-center"><input type="checkbox" class="bulk-checkbox" id="bulkSelectAll" onchange="toggleBulkSelectAll()"></th>' : ''}
                    <th>No</th>
                    <th>리테일러</th>
                    <th>지역</th>
                    <th>국가</th>
                    <th>예상</th>
                    <th>수집</th>
                    <th>Title NULL</th>
                    <th>Image NULL</th>
                    <th>0원</th>
                    <th>부분 NULL</th>
                    <th>정상</th>
                    <th>상태</th>
                    ${!(reportStatus.is_closed || currentBatchView === 'all') ? '<th>관리</th>' : ''}
                </tr>
            </thead>
            <tbody>
    `;

    for (const item of data.results) {
        // null_union: title NULL 또는 imageurl NULL (중복 제외한 합집합)
        const nullError = (item.null_union || 0) + (item.price_zero || 0) + item.partial_null;
        const nullStatus = item.total === 0 ? 'pending' : nullError === 0 ? 'success' : 'danger';
        const validTotal = item.valid + item.all_null;
        const rowClass = nullStatus === 'danger' ? 'row-danger' : '';

        // 배치 확장 버튼 (전체 뷰일 때만)
        const expandBtn = (item.has_multi_batch && currentBatchView === 'all')
            ? `<button class="expand-btn" onclick="event.stopPropagation(); toggleNullBatchRows('${item.retailer}')" id="nullExpandBtn_${item.retailer}">▶ 배치별</button>`
            : '';

        // 최종 모드에서 마지막 배치 시간 범위
        const finalStartTime = item.final_start_time ? `'${item.final_start_time}'` : 'null';
        const finalEndTime = item.final_end_time ? `'${item.final_end_time}'` : 'null';

        // 저장 여부에 따른 버튼 렌더링
        const isSaved = isRetailerSaved(item.retailer);
        const isClosed = reportStatus.is_closed;
        const hasError = nullError > 0;  // 이상치 여부

        let actionButtons = '';

        // 전체 탭 또는 마감된 날짜면 관리 열 비움
        if (currentBatchView === 'all' || isClosed) {
            actionButtons = '';
        } else if (nullStatus === 'pending') {
            // 수집중(대기)이면 버튼 숨김
            actionButtons = '';
        } else {
            if (isSaved) {
                actionButtons = AppButton.html('취소', `deleteRetailer('${item.retailer}', event)`, { size: 'sm', bg: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0', padding: '3px 9px', radius: '4px', fontSize: '11px' });
            } else if (item.expected_count > 0 && item.total < item.expected_count) {
                actionButtons = '';
            } else {
                actionButtons = AppButton.html('마감', `saveRetailer('${item.retailer}', event)`, { size: 'sm', style: 'primary', padding: '3px 9px', radius: '4px', fontSize: '11px' });
            }
        }

        // 체크박스: 미저장 + 수집완료만 활성화
        const canCheck = !isClosed && currentBatchView !== 'all' && !isSaved && nullStatus !== 'pending';

        html += `
            <tr class="${rowClass}" onclick="openNullDetail('${item.table_name}', '${item.retailer}', '${item.country}', ${item.title_null}, ${item.imageurl_null || 0}, ${item.price_zero || 0}, ${item.partial_null}, ${finalStartTime}, ${finalEndTime})" title="클릭하여 상세 보기" data-retailer="${item.retailer}">
                ${!(reportStatus.is_closed || currentBatchView === 'all') ? `<td class="text-center" onclick="event.stopPropagation()"><input type="checkbox" class="bulk-checkbox bulk-retailer-check" data-retailer="${item.retailer}" ${canCheck ? '' : 'disabled'} onchange="updateBulkCount()"></td>` : ''}
                <td>${item.no}</td>
                <td><span class="retailer-name">${item.retailer}</span>${expandBtn}</td>
                <td>${item.region}</td>
                <td><span class="country-badge">${item.country}</span></td>
                <td>${item.expected_count.toLocaleString()}</td>
                <td>${item.total.toLocaleString()}</td>
                <td class="error-count ${item.title_null > 0 ? 'has-error' : 'no-error'}">${item.title_null}</td>
                <td class="error-count ${(item.imageurl_null || 0) > 0 ? 'has-error' : 'no-error'}">${item.imageurl_null || 0}</td>
                <td class="error-count ${(item.price_zero || 0) > 0 ? 'has-error' : 'no-error'}">${item.price_zero || 0}</td>
                <td class="error-count ${item.partial_null > 0 ? 'has-error' : 'no-error'}">${item.partial_null}</td>
                <td class="error-count no-error">${validTotal.toLocaleString()}</td>
                <td>
                    <span class="status-badge ${nullStatus}">
                        <span class="status-dot"></span>
                        ${getStatusLabel(nullStatus)}
                    </span>
                </td>
                ${!(currentBatchView === 'all' || isClosed) ? `<td onclick="event.stopPropagation()">${actionButtons}</td>` : ''}
            </tr>
        `;

        // 배치 서브 행 (전체 뷰일 때만 렌더링)
        if (item.has_multi_batch && item.batches && currentBatchView === 'all') {
            for (const batch of item.batches) {
                const errorBadge = batch.error_count > 0
                    ? `<span class="batch-error-badge has-error">이상 ${batch.error_count}건</span>`
                    : `<span class="batch-error-badge no-error">정상</span>`;

                const endTimeParam = batch.end_time === '다음날' ? 'null' : `'${batch.end_time}'`;

                html += `
                    <tr class="batch-sub-row hidden" data-batch-retailer="${item.retailer}"
                        onclick="event.stopPropagation(); openNullDetail('${item.table_name}', '${item.retailer}', '${item.country}', ${batch.null_union}, 0, ${batch.price_zero || 0}, ${batch.partial_null}, '${batch.start_time}', ${endTimeParam})"
                        title="클릭하여 배치 상세 보기" style="cursor: pointer;">
                        <td></td>
                        <td colspan="4">
                            <span class="batch-indicator">
                                <span class="batch-time">${batch.start_time} ~ ${batch.end_time}</span>
                                <span class="batch-memo">${batch.memo || ''}</span>
                            </span>
                        </td>
                        <td>${batch.total.toLocaleString()}</td>
                        <td class="error-count ${batch.null_union > 0 ? 'has-error' : 'no-error'}">${batch.null_union}</td>
                        <td>-</td>
                        <td class="error-count ${batch.partial_null > 0 ? 'has-error' : 'no-error'}">${batch.partial_null}</td>
                        <td colspan="2">${errorBadge}</td>
                        <td></td>
                    </tr>
                `;
            }
        }
    }

    html += '</tbody></table>';

    container.innerHTML = html;

    // 일괄 마감 버튼 (마감 전 + 최종 탭) → 상단에 렌더링
    const bulkTop = document.getElementById('bulkActionsTop');
    if (bulkTop) {
        if (!reportStatus.is_closed && currentBatchView !== 'all') {
            bulkTop.innerHTML = `
                <span id="bulkCount" style="font-size: 13px; color: var(--text-secondary);"></span>
                ${AppButton.html('일괄 마감', 'bulkSaveRetailers()', { bg: '#f97316', padding: '10px 20px', id: 'bulkSaveBtn', disabled: true })}
            `;
        } else {
            bulkTop.innerHTML = '';
        }
    }
    updateBulkCount();
}

function getStatusLabel(status) {
    const labels = {
        'success': '정상',
        'warning': '경고',
        'danger': '이상',
        'pending': '대기',
        'error': '오류'
    };
    return labels[status] || '확인필요';
}

function openNullDetail(tableName, retailerName, country, titleNull, imageurlNull, priceZero, partialNull, startTime = null, endTime = null) {
    currentTableName = tableName;
    currentRetailerName = retailerName;
    currentCountry = country;
    currentPage = 1;
    currentStartTime = startTime;
    currentEndTime = endTime;
    currentSortBy = 'crawl_strdatetime';
    currentSortOrder = 'asc';
    currentRetailerData = { title_null: titleNull, imageurl_null: imageurlNull, price_zero: priceZero, partial_null: partialNull };
    currentDetailData = [];

    if (titleNull > 0) {
        currentErrorType = 'title_null';
    } else if (imageurlNull > 0) {
        currentErrorType = 'imageurl_null';
    } else if (priceZero > 0) {
        currentErrorType = 'price_zero';
    } else if (partialNull > 0) {
        currentErrorType = 'partial_null';
    } else {
        currentErrorType = 'title_null';
    }

    const timeRange = startTime ? ` (${startTime} ~ ${endTime || '다음날'})` : '';
    document.getElementById('modalTitle').textContent = `${retailerName} (${country}) - NULL 검증${timeRange}`;
    document.getElementById('modalSubtitle').textContent = `테이블: ${tableName}`;
    document.getElementById('detailModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    if (!modalPager) {
        modalPager = new Pagination('#modalPaginationContainer', {
            variant: 'simple',
            pageSize: 50,
            showInfo: false,
            onPageChange: (page) => {
                currentPage = page;
                loadDetailData();
            }
        });
    }

    renderNullErrorTypeSelector();
    loadDetailData();
}

function renderNullErrorTypeSelector() {
    const container = document.getElementById('errorTypeSelector');
    const errorTypes = [
        { key: 'title_null', label: 'Title NULL', count: currentRetailerData.title_null },
        { key: 'imageurl_null', label: 'Image NULL', count: currentRetailerData.imageurl_null },
        { key: 'price_zero', label: '0원', count: currentRetailerData.price_zero || 0 },
        { key: 'partial_null', label: '부분 NULL', count: currentRetailerData.partial_null }
    ];

    let html = '';
    for (const et of errorTypes) {
        const isActive = et.key === currentErrorType;
        html += `<button class="${isActive ? 'active' : ''}" onclick="selectErrorType('${et.key}')">${et.label} (${et.count})</button>`;
    }

    container.innerHTML = html;
}

function selectErrorType(errorType) {
    currentErrorType = errorType;
    currentPage = 1;
    currentSortBy = 'crawl_strdatetime';
    currentSortOrder = 'asc';
    renderNullErrorTypeSelector();
    loadDetailData();
}

async function loadDetailData() {
    const date = document.getElementById('targetDate').value;
    document.getElementById('modalLoading').classList.remove('hidden');
    document.getElementById('modalContent').innerHTML = '';

    try {
        let url = `/ds/layer2/api/detail/?table=${currentTableName}&error_type=${currentErrorType}&date=${date}&page=${currentPage}&page_size=50`;
        url += `&sort_by=${currentSortBy}&sort_order=${currentSortOrder}`;

        if (currentStartTime) {
            url += `&start_time=${currentStartTime}`;
        }
        if (currentEndTime) {
            url += `&end_time=${currentEndTime}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            document.getElementById('modalContent').innerHTML = `<div class="loading">${esc(data.error)}</div>`;
        } else {
            renderDetailTable(data);
            // 에러 타입 정보 업데이트
            const typeLabels = { title_null: 'Title NULL', imageurl_null: 'Image NULL', imageurl_invalid: 'Image 형식오류', price_zero: '0원', partial_null: '부분 NULL' };
            document.getElementById('modalInfo').textContent = `${typeLabels[currentErrorType]}: ${data.total_count.toLocaleString()}건`;
            modalPager.render(data.total_count, currentPage);
        }
    } catch (error) {
        console.error('Error loading detail:', error);
        document.getElementById('modalContent').innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }

    document.getElementById('modalLoading').classList.add('hidden');
}

function renderDetailTable(data) {
    // 현재 페이지 데이터 저장
    currentDetailData = data.data;

    if (data.data.length === 0) {
        document.getElementById('modalContent').innerHTML = '<div class="loading">비정상 데이터가 없습니다.</div>';
        return;
    }

    const date = document.getElementById('targetDate').value;

    let html = `
        <table class="detail-table">
            <thead>
                <tr>
                    <th style="width: 40px;"><input type="checkbox" id="checkAll" onchange="toggleAllCheckboxes(this.checked)" title="전체 선택"></th>
                    <th>crawl_date</th>
                    <th>country_code</th>
                    <th>title</th>
                    <th>retailprice</th>
                    <th>ships_from</th>
                    <th>sold_by</th>
                    <th>imageurl</th>
                    <th>producturl</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.data.forEach((item, index) => {
        const title = item.title || '';
        const retailprice = item.retailprice || '';
        const shipsFrom = item.ships_from || '';
        const soldBy = item.sold_by || '';
        const imageurl = item.imageurl || '';
        const producturl = item.producturl || '';

        html += `
            <tr>
                <td style="text-align: center;"><input type="checkbox" class="row-checkbox" data-index="${index}" onchange="updateCheckCount()"></td>
                <td>${date}</td>
                <td>${currentCountry}</td>
                <td class="title-cell" title="${title}">${title || '<span class="null-value">NULL</span>'}</td>
                <td>${retailprice || '<span class="null-value">NULL</span>'}</td>
                <td>${shipsFrom || '<span class="null-value">NULL</span>'}</td>
                <td>${soldBy || '<span class="null-value">NULL</span>'}</td>
                <td style="max-width: 200px;">${imageurl ? `<a href="${imageurl}" target="_blank" title="${imageurl}">${imageurl.substring(0, 30)}...</a>` : '<span class="null-value">NULL</span>'}</td>
                <td>${producturl ? `<a href="${producturl}" target="_blank">링크</a><button class="app-icon-btn-ghost" onclick="event.stopPropagation(); copyProductUrl('${producturl.replace(/'/g, "\\'")}', this)" title="링크 복사"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>` : '-'}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    document.getElementById('modalContent').innerHTML = html;
    updateCheckCount();
}

function sortBy(column) {
    if (currentSortBy === column) {
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortBy = column;
        currentSortOrder = 'asc';
    }
    currentPage = 1;
    loadDetailData();
}

function closeModal() {
    document.getElementById('detailModal').classList.add('hidden');
    document.body.style.overflow = '';
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// NULL 테이블 배치 행 토글
function toggleNullBatchRows(retailer) {
    const batchRows = document.querySelectorAll(`tr[data-batch-retailer="${retailer}"]`);
    const expandBtn = document.getElementById(`nullExpandBtn_${retailer}`);

    if (batchRows.length === 0) return;

    const isExpanded = !batchRows[0].classList.contains('hidden');

    batchRows.forEach(row => {
        if (isExpanded) {
            row.classList.add('hidden');
        } else {
            row.classList.remove('hidden');
        }
    });

    if (expandBtn) {
        if (isExpanded) {
            expandBtn.textContent = '▶ 배치별';
            expandBtn.classList.remove('expanded');
        } else {
            expandBtn.textContent = '▼ 접기';
            expandBtn.classList.add('expanded');
        }
    }
}

// 행 데이터를 보고서 형식으로 변환
function formatRowForReport(item) {
    const date = document.getElementById('targetDate').value;
    // 형식: crawl_date, country_code, title, retailprice, ships_from, sold_by, imageurl, producturl, 증빙사진, 비고
    const crawlDate = date;
    const countryCode = currentCountry || '';
    const title = item.title || '';
    const retailprice = item.retailprice || '';
    const shipsFrom = item.ships_from || '';
    const soldBy = item.sold_by || '';
    const imageurl = item.imageurl || '';
    const producturl = item.producturl || '';
    const evidence = ''; // 증빙사진 - 빈칸
    const note = ''; // 비고 - 빈칸

    // 탭으로 구분된 형식 (엑셀 붙여넣기용)
    return [crawlDate, countryCode, title, retailprice, shipsFrom, soldBy, imageurl, producturl, evidence, note].join('\t');
}

// 전체 선택/해제
function toggleAllCheckboxes(checked) {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    checkboxes.forEach(cb => cb.checked = checked);
    updateCheckCount();
}

// 선택 개수 업데이트
function updateCheckCount() {
    const checkboxes = document.querySelectorAll('.row-checkbox:checked');
    const count = checkboxes.length;
    const btnText = document.getElementById('copyBtnText');
    if (btnText) {
        btnText.textContent = `선택 복사 (${count}건)`;
    }

    // 전체 선택 체크박스 상태 업데이트
    const allCheckboxes = document.querySelectorAll('.row-checkbox');
    const checkAll = document.getElementById('checkAll');
    if (checkAll && allCheckboxes.length > 0) {
        checkAll.checked = count === allCheckboxes.length;
        checkAll.indeterminate = count > 0 && count < allCheckboxes.length;
    }
}

// 선택된 항목 복사
function copyCheckedToReport() {
    const checkboxes = document.querySelectorAll('.row-checkbox:checked');

    if (checkboxes.length === 0) {
        showToast('복사할 항목을 선택해주세요');
        return;
    }

    const rows = [];
    checkboxes.forEach(cb => {
        const index = parseInt(cb.dataset.index);
        const item = currentDetailData[index];
        if (item) {
            rows.push(formatRowForReport(item));
        }
    });

    const text = rows.join('\n');
    const btn = document.getElementById('copyAllBtn');

    const onSuccess = () => {
        if (btn) {
            btn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span id="copyBtnText">복사 완료!</span>
            `;
            btn.style.background = '#059669';
            btn.style.borderColor = '#059669';
            setTimeout(() => {
                btn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    <span id="copyBtnText">선택 복사 (${checkboxes.length}건)</span>
                `;
                btn.style.background = '#4338ca';
                btn.style.borderColor = '#4338ca';
            }, 2000);
        }
        showToast(`${rows.length}건 복사 완료`);
    };

    const onError = (err) => {
        console.error('Copy failed:', err);
        showToast('복사 실패');
    };

    copyText(text).then(onSuccess).catch(onError);
}
