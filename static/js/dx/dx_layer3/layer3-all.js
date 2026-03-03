let currentData = null;

// ViewStack — 모달 대신 인라인 콘텐츠 교체
const ViewStack = {
    stack: [],
    getContainer() {
        return document.getElementById('categories-container') || document.getElementById('field-missing-section');
    },
    push(html, title) {
        const container = this.getContainer();
        if (!container) return;
        this.stack.push({
            html: container.innerHTML,
            scrollTop: window.scrollY,
            title: AppModal.getTitle('detail')
        });
        container.innerHTML = html;
        window.scrollTo(0, 0);
        // 하위 뷰 진입 시 필터바 숨김 + category-section 배경/보더 제거
        var filterBar = document.querySelector('.filter-section');
        if (filterBar) filterBar.style.display = 'none';
        if (container.classList.contains('category-section')) {
            container.style.background = 'none';
            container.style.border = 'none';
        }
    },
    pop() {
        if (this.stack.length === 0) return false;
        const state = this.stack.pop();
        const container = this.getContainer();
        if (container) {
            container.innerHTML = state.html;
            window.scrollTo(0, state.scrollTop);
        }
        // 최상위로 돌아오면 필터바 복원 + category-section 스타일 복원
        if (this.stack.length === 0) {
            var filterBar = document.querySelector('.filter-section');
            if (filterBar) filterBar.style.display = '';
            if (container && container.classList.contains('category-section')) {
                container.style.background = '';
                container.style.border = '';
            }
        }
        return true;
    },
    reset(html) {
        this.stack = [];
        const container = this.getContainer();
        if (container) container.innerHTML = html;
    },
    depth() { return this.stack.length; }
};

// 카테고리별 특성 인라인 모드 판별
function isCatSpecInline() {
    return (window.LAYER3 && window.LAYER3.section) === 'category_spec';
}

// 크로스 필드 검증 인라인 모드 판별
function isCrossFieldInline() {
    return (window.LAYER3 && window.LAYER3.section) === 'cross_field';
}

// 인라인 상세 타이틀 HTML (제목 + 날짜)
function _inlineTitle(title) {
    var dateVal = document.getElementById('target-date') ? document.getElementById('target-date').value : '';
    var dateDisplay = '';
    if (dateVal) {
        var d = new Date(dateVal + 'T00:00:00');
        var weekdays = ['일', '월', '화', '수', '목', '금', '토'];
        dateDisplay = dateVal + '(' + weekdays[d.getDay()] + ')';
    }
    return '<span>' + title + '</span>' + (dateDisplay ? '<span class="inline-detail-date">' + dateDisplay + '</span>' : '');
}

// 요일 표시 업데이트
function updateWeekday() {
    const dateInput = document.getElementById('target-date');
    const weekdayDisplay = document.getElementById('weekday-display');
    if (dateInput.value && weekdayDisplay) {
        const date = new Date(dateInput.value + 'T00:00:00');
        const weekdays = ['일', '월', '화', '수', '목', '금', '토'];
        const weekday = weekdays[date.getDay()];
        const isWeekend = date.getDay() === 0 || date.getDay() === 6;
        weekdayDisplay.textContent = `(${weekday})`;
        weekdayDisplay.style.color = isWeekend ? 'var(--color-critical)' : 'var(--text-secondary)';
    }
}

// 로컬 날짜를 YYYY-MM-DD 형식으로 변환
function formatLocalDate(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('target-date');
    const saved = localStorage.getItem('monitoringSelectedDate');
    if (saved) {
        dateInput.value = saved;
    } else {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        dateInput.value = formatLocalDate(yesterday);
    }

    // 날짜 변경 시 요일 업데이트 + localStorage 저장
    dateInput.addEventListener('change', function() {
        updateWeekday();
        localStorage.setItem('monitoringSelectedDate', dateInput.value);
    });
    updateWeekday();
    checkBackupStatus();
    loadData();
});

async function checkBackupStatus() {
    const date = document.getElementById('target-date').value;
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

// 다음날(조회 날짜 기준 +1일) 설정 후 조회
function setNextDay() {
    const dateInput = document.getElementById('target-date');
    const current = new Date(dateInput.value);
    current.setDate(current.getDate() + 1);
    dateInput.value = formatLocalDate(current);
    localStorage.setItem('monitoringSelectedDate', dateInput.value);
    updateWeekday();
    loadData();
}

// 전날(조회 날짜 기준 -1일) 설정 후 조회
function setPrevDay() {
    const dateInput = document.getElementById('target-date');
    const current = new Date(dateInput.value);
    current.setDate(current.getDate() - 1);
    dateInput.value = formatLocalDate(current);
    localStorage.setItem('monitoringSelectedDate', dateInput.value);
    updateWeekday();
    loadData();
}

// 섹션 → 카테고리명 매핑
const SECTION_CATEGORY_MAP = {
    'time_series': '시계열 이상치',
    'cross_field': '크로스 필드 검증',
    'category_spec': '카테고리별 특성'
};

// 데이터 로드
async function loadData() {
    checkBackupStatus();
    const date = document.getElementById('target-date').value;
    const section = (window.LAYER3 && window.LAYER3.section) || 'dashboard';

    // 인라인 상세보기 중이면 현재 보고 있는 항목 저장 (날짜 변경 후 복원용)
    let reopenDetail = null;
    if (section === 'category_spec' && ViewStack.depth() > 0 && window.categorySpecTitle) {
        reopenDetail = window.categorySpecTitle;
    }
    ViewStack.stack = [];  // ViewStack 초기화

    const catContainer = document.getElementById('categories-container');
    if (catContainer) catContainer.innerHTML = '<div class="loading">데이터를 불러오는 중...</div>';

    // 필드 누락 캐시 초기화 (조회 시 항상 새로운 데이터 로드)
    retailerMissingCache = {};

    try {
        const sectionParam = section !== 'dashboard' ? `&section=${section}` : '';
        const data = await fetchAPI(`/layer3/api/stats/?date=${date}&type=all${sectionParam}`);
        currentData = data;
        renderData(data);
        updateCurrentInfo(date);

        // 필드 누락 데이터 로드 (대시보드 또는 필드 누락 페이지에서만)
        if (section === 'dashboard' || section === 'field_missing') {
            loadAllRetailersMissing();
        }

        // 인라인 상세보기 복원 (날짜 변경 시 같은 화면 유지)
        if (reopenDetail) {
            showDetail('카테고리별 특성', reopenDetail);
        }

        // URL focus 파라미터 처리 (사이드바에서 직접 진입 시)
        if (!reopenDetail) {
            const urlParams = new URLSearchParams(window.location.search);
            const focus = urlParams.get('focus');
            if (focus && section === 'category_spec') {
                showDetail('카테고리별 특성', focus);
                // focus 파라미터 제거 (뒤로가기 시 중복 방지)
                urlParams.delete('focus');
                const cleanUrl = urlParams.toString() ? `${window.location.pathname}?${urlParams}` : window.location.pathname;
                history.replaceState(null, '', cleanUrl);
            }
        }
    } catch (error) {
        console.error('Error:', error);
        if (catContainer) catContainer.innerHTML = '<div class="loading">데이터 로드 실패</div>';
    }
}

// 조회 날짜 정보 표시
function updateCurrentInfo(date) {
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
    document.getElementById('current-info').innerHTML = `<strong>${esc(date)}</strong> 검증 현황 <span class="date-badge ${badgeClass}">${esc(badgeText)}</span>`;
}

// 데이터 렌더링
function renderData(data) {
    const section = (window.LAYER3 && window.LAYER3.section) || 'dashboard';
    const filterCategory = SECTION_CATEGORY_MAP[section] || null;

    // Summary 업데이트 (대시보드에서만 표시)
    if (!filterCategory) {
        const elChecked = document.getElementById('total-checked');
        const elPassed = document.getElementById('total-passed');
        const elFailed = document.getElementById('total-failed');
        const elRate = document.getElementById('pass-rate');
        if (elChecked) elChecked.textContent = (data.summary.total_checked || 0).toLocaleString();
        if (elPassed) elPassed.textContent = (data.summary.passed || 0).toLocaleString();
        if (elFailed) elFailed.textContent = (data.summary.failed || 0).toLocaleString();
        if (elRate) elRate.textContent = (data.summary.pass_rate || 0) + '%';
    }

    // 카테고리별 그룹화
    const categories = {};
    (data.checks || []).forEach(check => {
        const cat = check.category || '기타';
        // 섹션 페이지에서는 해당 카테고리만 표시
        if (filterCategory && cat !== filterCategory) return;
        if (!categories[cat]) {
            categories[cat] = [];
        }
        categories[cat].push(check);
    });

    // 카테고리 아이콘 및 색상 매핑
    const categoryConfig = {
        '시계열 이상치': { icon: '📈', class: 'time-series' },
        '크로스 필드 검증': { icon: '🔗', class: 'cross-field' },
        '카테고리별 특성': { icon: '📊', class: 'category-spec' }
    };

    // 검증 규칙이 있는 체크 항목들 (크로스 필드 검증 항목)
    const crossfieldChecksWithRules = ['TV 논리적 일관성', 'HHP 논리적 일관성', 'TV Sentiment↔리뷰 일관성', 'HHP Sentiment↔리뷰 일관성'];

    // 상태 표시 텍스트 변환
    const statusText = (status) => {
        if (status === 'REVIEW_NEEDED') return '검토필요';
        return status;
    };

    let html = '';

    Object.entries(categories).forEach(([categoryName, checks], catIdx) => {
        const config = categoryConfig[categoryName] || { icon: '📋', class: 'time-series' };
        const totalChecked = checks.reduce((sum, c) => sum + (c.checked || 0), 0);
        const totalFailed = checks.reduce((sum, c) => sum + (c.failed || 0), 0);
        const hasReviewNeeded = checks.some(c => c.status === 'REVIEW_NEEDED');
        const catStatus = hasReviewNeeded ? 'review_needed' : (totalFailed === 0 ? 'ok' : (totalFailed < 10 ? 'warning' : 'critical'));

        if (filterCategory) {
            // 섹션 페이지: 카테고리 헤더 없이 체크 항목만 표시
            html += `<div class="category-section"><div class="category-content" id="cat-content-${catIdx}" style="display:block;">`;
        } else {
            // 대시보드: 카테고리 헤더 + 접기/펼치기
            html += `
            <div class="category-section">
                <div class="category-header" onclick="toggleCategory(${catIdx})">
                    <div class="category-title">
                        <div class="category-icon ${config.class}">${config.icon}</div>
                        <span>${esc(categoryName)}</span>
                        <span class="toggle-icon" id="cat-toggle-${catIdx}">▶</span>
                    </div>
                    <div class="category-summary">
                        <div class="category-stat">
                            <div class="value">${totalChecked.toLocaleString()}</div>
                            <div class="label">검사</div>
                        </div>
                        <div class="category-stat">
                            <div class="value" style="color: var(--color-critical);">${totalFailed.toLocaleString()}</div>
                            <div class="label">이상치</div>
                        </div>
                        <span class="status-badge ${catStatus}">${statusText(catStatus.toUpperCase())}</span>
                    </div>
                </div>
                <div class="category-content" id="cat-content-${catIdx}">
            `;
        }

        checks.forEach((check, checkIdx) => {
            const status = (check.status || 'OK').toLowerCase();
            // 카테고리별 특성은 모두 검증 규칙 버튼 표시, 크로스 필드는 특정 항목만
            const hasRules = categoryName === '카테고리별 특성' || crossfieldChecksWithRules.includes(check.name);
            const rulesBtn = hasRules ? `<button class="btn-rules" onclick="event.stopPropagation(); showRulesModal('${escJs(check.name)}')">검증 규칙</button>` : '';

            html += `
                <div class="check-item clickable-row" onclick="showDetail('${escJs(categoryName)}', '${escJs(check.name)}')">
                    <div class="check-info">
                        <div class="check-name">
                            ${esc(check.name)}
                            ${check.threshold ? `<span class="threshold-badge">${esc(String(check.threshold))}</span>` : ''}
                            ${rulesBtn}
                        </div>
                        <div class="check-description">${esc(check.description || '')}</div>
                    </div>
                    <div class="check-stats">
                        <div class="check-stat">
                            <div class="value">${(check.checked || 0).toLocaleString()}</div>
                            <div class="label">검사</div>
                        </div>
                        <div class="check-stat">
                            <div class="value" style="color: var(--color-ok);">${(check.passed || 0).toLocaleString()}</div>
                            <div class="label">정상</div>
                        </div>
                        <div class="check-stat">
                            <div class="value" style="color: var(--color-critical);">${(check.failed || 0).toLocaleString()}</div>
                            <div class="label">이상치</div>
                        </div>
                        <span class="status-badge ${status}">${statusText(status.toUpperCase())}</span>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    if (Object.keys(categories).length === 0) {
        html = '<div class="loading">해당 조건의 데이터가 없습니다.</div>';
    }

    const catContainer = document.getElementById('categories-container');
    if (catContainer) {
        catContainer.innerHTML = html;
        // 섹션 페이지에서는 카테고리를 자동 펼침
        if (filterCategory) {
            catContainer.querySelectorAll('.category-content').forEach(el => el.classList.add('show'));
            catContainer.querySelectorAll('.toggle-icon').forEach(el => el.classList.add('expanded'));
        }
    }

}

// 카테고리 토글
function toggleCategory(idx) {
    const content = document.getElementById(`cat-content-${idx}`);
    const toggle = document.getElementById(`cat-toggle-${idx}`);

    if (content.classList.contains('show')) {
        content.classList.remove('show');
        toggle.classList.remove('expanded');
    } else {
        content.classList.add('show');
        toggle.classList.add('expanded');
    }
}

// 상세 정보 표시
async function showDetail(category, checkName) {
    const date = document.getElementById('target-date').value;

    let apiUrl = '';
    let title = checkName;

    // API URL 결정
    if (category === '시계열 이상치') {
        // checkName에서 타입 결정 (TV/HHP)
        let itemType = checkName.includes('HHP') ? 'hhp' : 'tv';

        if (checkName.includes('가격')) {
            apiUrl = `/layer3/api/time-series-detail/?date=${date}&type=${itemType}&check=price`;
            if (checkName.includes('전주')) {
                apiUrl += '&period=weekly';
            }
        } else if (checkName.includes('순위')) {
            apiUrl = `/layer3/api/time-series-detail/?date=${date}&type=${itemType}&check=rank`;
        } else if (checkName.includes('리뷰')) {
            apiUrl = `/layer3/api/review-change-detail/?date=${date}&type=${itemType}`;
        }
    } else if (category === '크로스 필드 검증') {
        if (checkName.includes('Sentiment')) {
            // Sentiment↔리뷰 일관성 검증
            const type = checkName.includes('TV') ? 'tv' : 'hhp';
            apiUrl = `/layer3/api/sentiment-cross-detail/?date=${date}&type=${type}`;
        } else if (checkName.includes('Comp Product')) {
            // Comp Product 자사/경쟁사 구분
            apiUrl = `/layer3/api/comp-product-cross-detail/?date=${date}`;
        } else {
            // TV/HHP 논리적 일관성
            const type = checkName.includes('TV') ? 'tv' : 'hhp';
            apiUrl = `/layer3/api/cross-field-detail/?date=${date}&type=${type}`;
        }

        // 크로스 필드 섹션 페이지 → 인라인 표시
        if (isCrossFieldInline() && apiUrl) {
            ViewStack.push(`
                <div class="inline-detail">
                    <button class="btn-back" onclick="ViewStack.pop()">← 목록으로</button>
                    <div class="inline-detail-title">${_inlineTitle(title)}</div>
                    <div class="inline-detail-body"><p style="text-align:center;">데이터를 불러오는 중...</p></div>
                </div>
            `);
            try {
                const data = await fetchAPI(apiUrl);
                renderCrossfieldSummaryContent(title, category, data);
            } catch (error) {
                console.error('Error:', error);
                const body = document.querySelector('.inline-detail-body');
                if (body) body.innerHTML = '<p>데이터 로드 실패</p>';
            }
            return;
        }
    } else if (category === '카테고리별 특성') {
        // display_name을 그대로 전달하여 동적 처리
        apiUrl = `/layer3/api/category-spec-detail/?date=${date}&display_name=${encodeURIComponent(checkName)}&mode=summary`;

        // 카테고리별 특성 섹션 페이지 → 인라인 표시
        if (isCatSpecInline()) {
            ViewStack.push(`
                <div class="inline-detail">
                    <button class="btn-back" onclick="ViewStack.pop()">← 목록으로</button>
                    <div class="inline-detail-title">${title}</div>
                    <div class="inline-detail-body"><p style="text-align:center;">데이터를 불러오는 중...</p></div>
                </div>
            `);
            try {
                const data = await fetchAPI(apiUrl);
                renderCatSpecSummaryContent(title, data);
            } catch (error) {
                console.error('Error:', error);
                const body = document.querySelector('.inline-detail-body');
                if (body) body.innerHTML = '<p>데이터 로드 실패</p>';
            }
            return;
        }
    }

    if (!apiUrl) {
        AppModal.setTitle('detail', title);
        AppModal.setBody('detail', '<p>상세 조회 API가 구현되지 않았습니다.</p>');
        AppModal.open('detail');
        return;
    }

    try {
        const data = await fetchAPI(apiUrl);
        renderDetailModal(title, category, data);
    } catch (error) {
        console.error('Error:', error);
        AppModal.setTitle('detail', title);
        AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
        AppModal.open('detail');
    }
}

// 상세 모달 렌더링
function renderDetailModal(title, category, data) {
    AppModal.setTitle('detail', title + ` (${data.total_anomalies || data.total_changes || data.total_duplicates || 0}건)`);

    let html = '';

    if (category === '시계열 이상치') {
        const changes = data.changes || [];
        if (changes.length === 0) {
            html = '<p>이상치 데이터가 없습니다.</p>';
        } else {
            const isPriceCheck = data.check_type === 'price';
            const isReviewCheck = data.check_type === 'review';
            const productLine = (data.product_line || 'TV').toUpperCase();
            const tableName = productLine === 'HHP' ? 'hhp_retail_com' : 'tv_retail_com';
            const dateColumn = productLine === 'HHP' ? 'crawl_strdatetime' : 'crawl_datetime';

            // item 목록 추출
            const items = [...new Set(changes.map(r => r.item).filter(Boolean))].sort();
            const itemListDisplay = items.join(', ');
            const inClause = items.map(item => `'${item}'`).join(', ');

            // 조회 쿼리 생성
            const queryDate = data.date || document.getElementById('target-date').value;
            let selectCols = 'id, item, account_name, retailer_sku_name, ' + dateColumn;
            if (isPriceCheck) {
                selectCols += ', final_sku_price';
            } else if (isReviewCheck) {
                selectCols += ', count_of_reviews';
            } else {
                selectCols += ', retailer_rank, is_own_brand';
            }
            selectCols += ', product_url';

            const query = `SELECT ${selectCols}
FROM ${tableName}
WHERE item IN (${inClause})
  AND DATE(${dateColumn}::timestamp) >= DATE('${queryDate}') - INTERVAL '2 days'
  AND DATE(${dateColumn}::timestamp) <= DATE('${queryDate}')
ORDER BY item, ${dateColumn} ASC;`;

            // 쿼리 박스 표시
            if (items.length > 0) {
                html += `
                <div class="query-section">
                    <div class="item-list-box">
                        <div class="query-box-header">
                            <span class="query-box-title">Item 목록 (${items.length}개)</span>
                            <button class="btn-copy" onclick="copyQueryToClipboard(this.parentElement.nextElementSibling)">복사</button>
                        </div>
                        <div class="item-list-content">${itemListDisplay}</div>
                    </div>
                    <div class="query-box">
                        <div class="query-box-header">
                            <span class="query-box-title">3일치 조회 쿼리</span>
                            <button class="btn-copy" onclick="copyQueryToClipboard(this.parentElement.nextElementSibling)">복사</button>
                        </div>
                        <pre class="query-content">${query}</pre>
                    </div>
                </div>`;
            }

            html += '<div class="table-scroll-container"><table class="detail-table"><thead><tr>';
            html += '<th>No.</th><th>Item</th><th>Retailer</th><th>제품명</th><th>수집 시점</th>';
            if (isPriceCheck) {
                html += '<th>이전 가격</th><th>현재 가격</th><th>변동률</th><th>URL</th>';
            } else if (isReviewCheck) {
                html += '<th>이전 리뷰 수</th><th>현재 리뷰 수</th><th>증가율</th><th>URL</th>';
            } else {
                html += '<th>이전 순위</th><th>현재 순위</th><th>변동</th><th>URL</th>';
            }
            html += '</tr></thead><tbody>';

            changes.forEach((row, idx) => {
                html += '<tr>';
                html += `<td>${idx + 1}</td>`;
                html += `<td>${esc(row.item || '-')}</td>`;
                html += `<td>${esc(row.account_name || row.retailer || '-')}</td>`;
                html += `<td>${esc(row.product_name || '-')}</td>`;
                // 수집 시점 (오전/오후)
                const periodText = row.period === 'AM' ? '오전' : (row.period === 'PM' ? '오후' : '-');
                html += `<td>${periodText}</td>`;
                if (isPriceCheck) {
                    // HHP는 문자열($19.99), TV는 숫자
                    const prevPrice = row.prev_price != null ? (typeof row.prev_price === 'string' ? row.prev_price : '$' + row.prev_price.toLocaleString()) : '-';
                    const currPrice = row.curr_price != null ? (typeof row.curr_price === 'string' ? row.curr_price : '$' + row.curr_price.toLocaleString()) : '-';
                    html += `<td>${prevPrice}</td>`;
                    html += `<td>${currPrice}</td>`;
                    html += `<td style="color: ${row.change_pct > 0 ? 'red' : 'green'};">${row.change_pct || 0}%</td>`;
                } else if (isReviewCheck) {
                    html += `<td>${row.prev_count != null ? row.prev_count.toLocaleString() : '-'}</td>`;
                    html += `<td>${row.curr_count != null ? row.curr_count.toLocaleString() : '-'}</td>`;
                    html += `<td style="color: red;">+${row.change_pct || 0}%</td>`;
                } else {
                    html += `<td>${row.prev_rank || '-'}</td>`;
                    html += `<td>${row.curr_rank || '-'}</td>`;
                    const change = row.rank_change || 0;
                    html += `<td style="color: ${change > 0 ? 'red' : 'green'};">${change > 0 ? '+' : ''}${change}</td>`;
                }
                const safeLink = safeUrl(row.product_url);
                if (safeLink) {
                    html += `<td><a href="${esc(safeLink)}" target="_blank" style="color: #1976d2;">링크</a></td>`;
                } else {
                    html += '<td>-</td>';
                }
                html += '</tr>';
            });

            html += '</tbody></table></div>';
        }
    } else if (category === '크로스 필드 검증') {
        // Sentiment 검증인 경우 기존 방식 유지
        if (title.includes('Sentiment')) {
            const anomalies = data.anomalies || [];
            if (anomalies.length === 0) {
                html = '<p>논리 오류 데이터가 없습니다.</p>';
            } else {
                const hasRetailComId = anomalies.some(row => row.retail_com_id);
                html = '<div class="table-scroll-container"><table class="detail-table"><thead><tr>';
                html += '<th>No.</th>';
                if (hasRetailComId) {
                    html += '<th>ID</th>';
                }
                html += '<th>Item</th><th>Retailer</th><th>Page Type</th><th>오류 내용</th>';
                html += '</tr></thead><tbody>';

                anomalies.forEach((row, idx) => {
                    const errorHtml = (row.errors || []).map(e => `<li>${esc(e.error)}</li>`).join('');
                    html += '<tr>';
                    html += `<td>${idx + 1}</td>`;
                    if (hasRetailComId) {
                        html += `<td>${esc(String(row.retail_com_id || '-'))}</td>`;
                    }
                    html += `<td>${esc(row.item || '-')}</td>`;
                    html += `<td>${esc(row.account_name || '-')}</td>`;
                    html += `<td>${esc(row.page_type || '-')}</td>`;
                    html += `<td><ul class="error-list">${errorHtml}</ul></td>`;
                    html += '</tr>';
                });
                html += '</tbody></table></div>';
            }
        } else {
            // TV/HHP 논리적 일관성 - 공통 함수로 위임 (모달/인라인 모두 처리)
            renderCrossfieldSummaryContent(title, category, data);
            return;
        }
    } else if (category === '카테고리별 특성') {
        // 공통 함수로 위임 (모달/인라인 모두 처리)
        renderCatSpecSummaryContent(title, data);
        return;
    } else {
        html = '<p>상세 데이터를 표시할 수 없습니다.</p>';
    }

    AppModal.setBody('detail', html);
    AppModal.open('detail');
}

// 크로스필드 요약 렌더링 (모달 / 인라인 공용)
function renderCrossfieldSummaryContent(title, _category, data) {
    const inline = isCrossFieldInline();
    const ruleSummary = data.rule_summary || [];

    // 현재 상태 저장 (뒤로가기용)
    window.crossfieldSummaryData = data;
    window.crossfieldTitle = title;
    window.crossfieldProductLine = data.product_line;

    const titleText = title + ` (${data.total_anomalies || 0}건)`;

    // 날짜 선택 UI (인라인은 상단 필터바 사용)
    let html = '';
    if (!inline) {
        html += `<div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
            <label style="font-weight: 500;">조회 날짜:</label>
            <input type="date" id="crossfield-date-picker" value="${data.date}"
                style="padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px;"
                onchange="reloadCrossfieldData(this.value, '${escJs(data.product_line)}', '${escJs(title)}')">
        </div>`;
    }

    if (ruleSummary.length === 0) {
        html += '<p>논리 오류 데이터가 없습니다.</p>';
    } else {
        // 플레이스홀더 치환용 정보
        const tableName = data.table_name || '';
        const dateCol = data.date_col || '';
        const noReviewTexts = data.no_review_texts || '';
        const targetDate = data.date || '';

        html += '<div class="rule-summary-section">';
        if (inline) html += `<div class="rule-summary-section-header">${_inlineTitle(titleText)}</div>`;
        html += '<div class="rule-summary-container">';
        ruleSummary.forEach((rule, idx) => {
            const fieldDisplay = rule.field2 ? `${rule.field1} ↔ ${rule.field2}` : rule.field1;
            const queryId = `crossfield-query-${idx}`;
            const displayQuery = replaceCrossfieldQueryPlaceholders(rule.query, tableName, dateCol, noReviewTexts, targetDate);
            const detailTitle = `${fieldDisplay} (${rule.error_message})`;
            html += `
                <div class="rule-summary-card-wrapper">
                    <div class="rule-summary-card" data-rule-id="${esc(String(rule.rule_id))}" onclick="loadCrossfieldRuleDetail('${escJs(data.product_line.toLowerCase())}', '${escJs(rule.rule_id)}', '${escJs(data.date)}', '${escJs(detailTitle)}')">
                        <div class="rule-info">
                            <div class="rule-name">
                                ${esc(fieldDisplay)}
                                <button class="btn-show-query" onclick="event.stopPropagation(); toggleCrossfieldQuery('${escJs(queryId)}')" title="검증 쿼리 보기">SQL</button>
                            </div>
                            <div class="rule-desc">${esc(rule.error_message)}</div>
                        </div>
                        <div class="rule-count${rule.error_count === 0 ? ' zero' : ''}">${rule.error_count}건</div>
                    </div>
                    <div id="${queryId}" class="crossfield-query-box" style="display: none;">
                        <pre>${esc(displayQuery)}</pre>
                        <button class="btn-copy-query" onclick="copyQueryToClipboard(this.previousElementSibling)">복사</button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        html += '</div>';
    }

    if (inline) {
        const titleEl = document.querySelector('.inline-detail-title');
        const bodyEl = document.querySelector('.inline-detail-body');
        if (titleEl) titleEl.style.display = 'none';
        if (bodyEl) bodyEl.innerHTML = html;
    } else {
        AppModal.setTitle('detail', titleText);
        AppModal.setBody('detail', html);
        AppModal.open('detail');
    }
}

// 카테고리별 특성 요약 렌더링 (모달 / 인라인 공용)
function renderCatSpecSummaryContent(title, data) {
    window.categorySpecSummaryData = data;
    window.categorySpecTitle = title;
    window.categorySpecDisplayName = title;

    const ruleSummary = data.rule_summary || [];
    const titleText = title + ` (${data.total_anomalies || 0}건)`;
    const inline = isCatSpecInline();

    // 날짜 선택기: 모달에서만 표시 (인라인은 상단 필터바 사용)
    let html = '';
    if (!inline) {
        html += `<div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
            <label style="font-weight: 500;">조회 날짜:</label>
            <input type="date" id="category-spec-date-picker" value="${data.date}"
                style="padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px;"
                onchange="reloadCategorySpecData(this.value, '${escJs(title)}', '${escJs(title)}')">
        </div>`;
    }

    if (ruleSummary.length === 0) {
        html += '<p>범위 이탈 데이터가 없습니다.</p>';
    } else {
        html += '<div class="rule-summary-section">';
        if (isCatSpecInline()) html += `<div class="rule-summary-section-header">${_inlineTitle(titleText)}</div>`;
        html += '<div class="rule-summary-container">';
        ruleSummary.forEach(rule => {
            html += `
                <div class="rule-summary-card" onclick="loadCategorySpecRuleDetail('${escJs(title)}', '${escJs(rule.rule_id)}', '${escJs(data.date)}', '${escJs(rule.detail_name)}')">
                    <div class="rule-info">
                        <div class="rule-name">${esc(rule.detail_name)}</div>
                        <div class="rule-desc">${esc(rule.error_message)}</div>
                    </div>
                    <div class="rule-count${rule.error_count === 0 ? ' zero' : ''}">${rule.error_count}건</div>
                </div>
            `;
        });
        html += '</div>';
        html += '</div>';
    }

    if (isCatSpecInline()) {
        const titleEl = document.querySelector('.inline-detail-title');
        const bodyEl = document.querySelector('.inline-detail-body');
        if (titleEl) titleEl.style.display = 'none';
        if (bodyEl) bodyEl.innerHTML = html;
    } else {
        AppModal.setTitle('detail', titleText);
        AppModal.setBody('detail', html);
        AppModal.open('detail');
    }
}

// 모달 닫기
function closeModal() {
    AppModal.close('detail');
}

// 크로스필드 쿼리 플레이스홀더 치환
function replaceCrossfieldQueryPlaceholders(query, tableName, dateCol, noReviewTexts, targetDate) {
    if (!query) return '쿼리 없음';
    let result = query;
    result = result.replace(/\{table\}/g, tableName || 'table_name');
    result = result.replace(/\{date_col\}/g, dateCol || 'crawl_datetime');
    result = result.replace(/\{no_review_texts\}/g, noReviewTexts || "'No customer reviews', 'Not yet reviewed', 'No ratings yet'");
    result = result.replace(/%s/g, `'${targetDate}'`);
    return result;
}

// 크로스필드 검증 쿼리 토글
function toggleCrossfieldQuery(queryId) {
    const queryBox = document.getElementById(queryId);
    if (queryBox) {
        queryBox.style.display = queryBox.style.display === 'none' ? 'block' : 'none';
    }
}

// 크로스필드 데이터 날짜 변경 시 재로드
async function reloadCrossfieldData(date, productLine, title) {
    const inline = isCrossFieldInline();
    const bodyEl = inline ? document.querySelector('.inline-detail-body') : AppModal.getBody('detail');
    if (bodyEl) bodyEl.innerHTML = '<p style="text-align:center;">데이터를 불러오는 중...</p>';

    try {
        const data = await fetchAPI(`/layer3/api/cross-field-detail/?date=${date}&type=${productLine.toLowerCase()}`);

        if (data.error) {
            if (bodyEl) bodyEl.innerHTML = `<p style="color: red;">오류: ${esc(data.error)}</p>`;
            return;
        }

        // 공통 렌더링 (모달/인라인 모두 처리)
        renderCrossfieldSummaryContent(title, '크로스 필드 검증', data);

    } catch (error) {
        console.error('Error:', error);
        if (bodyEl) bodyEl.innerHTML = '<p style="color: red;">데이터 로드 실패</p>';
    }
}

// 크로스필드 검증 유형별 상세 데이터 로드
async function loadCrossfieldRuleDetail(productLine, ruleId, date, ruleName) {
    const inline = isCrossFieldInline();

    if (inline) {
        ViewStack.push(`
            <div class="inline-detail">
                <button class="btn-back" onclick="ViewStack.pop()">← 뒤로가기</button>
                <div class="inline-detail-title">${_inlineTitle(ruleName)}</div>
                <div class="inline-detail-body"><p style="text-align:center;">데이터를 불러오는 중...</p></div>
            </div>
        `);
    } else {
        AppModal.setTitle('detail', ruleName);
        AppModal.setBody('detail', '<p style="text-align:center;">데이터를 불러오는 중...</p>');
    }

    try {
        const data = await fetchAPI(`/layer3/api/cross-field-detail/?date=${date}&type=${productLine}&rule_id=${ruleId}`);

        if (data.error) {
            const errHtml = `<p style="color: red;">오류: ${esc(data.error)}</p>`;
            if (inline) {
                const body = document.querySelector('.inline-detail-body');
                if (body) body.innerHTML = errHtml;
            } else {
                AppModal.setBody('detail', errHtml);
            }
            return;
        }

        let html = '';

        // 뒤로가기 버튼 (모달에서만, 인라인은 상위 컨테이너에 있음)
        if (!inline) {
            html += `<button class="btn-back" onclick="backToCrossfieldSummary()">← 뒤로가기</button>`;
        }

        const anomalies = data.anomalies || [];
        if (anomalies.length === 0) {
            html += '<p>해당 검증 유형에 대한 이상치 데이터가 없습니다.</p>';
        } else {
            // 리테일러별 데이터 그룹핑
            const retailerData = {};
            anomalies.forEach(row => {
                const retailer = row.account_name || 'Unknown';
                if (!retailerData[retailer]) {
                    retailerData[retailer] = { items: [], rows: [] };
                }
                retailerData[retailer].rows.push(row);
                if (row.item && !retailerData[retailer].items.includes(row.item)) {
                    retailerData[retailer].items.push(row.item);
                }
            });

            // 전역에 저장 (리테일러 클릭 시 사용)
            window.crossfieldRetailerData = retailerData;
            window.crossfieldAnomalies = anomalies;
            window.crossfieldProductLine = productLine;
            window.crossfieldDate = date;
            window.crossfieldRuleName = ruleName;
            window.crossfieldRuleId = ruleId;
            window.crossfieldSelectFields = data.select_fields || '';
            window.crossfieldValidationType = data.validation_type || '';
            window.crossfieldTableName = data.table_name || '';
            window.crossfieldEditableCols = new Set(data.editable_columns || []);
            window.crossfieldNormalReviews = data.normal_reviews || {};
            window.crossfieldRetailerColumns = data.retailer_columns || {};
            window.crossfieldPendingEdits = {};

            const titleText = `${ruleName} (${data.total_anomalies}건)`;

            // 리테일러 목록 (rule-summary-card 스타일)
            html += '<div class="rule-summary-section">';
            if (inline) html += `<div class="rule-summary-section-header">${_inlineTitle(titleText)}</div>`;
            html += '<div class="rule-summary-container">';
            Object.keys(retailerData).sort().forEach(retailer => {
                const items = retailerData[retailer].items;
                const rowCount = retailerData[retailer].rows.length;
                html += `
                    <div class="rule-summary-card" data-retailer="${esc(retailer)}" onclick="showRetailerDetail('${escJs(retailer)}')">
                        <div class="rule-info">
                            <div class="rule-name">${esc(retailer)}</div>
                            <div class="rule-desc">${items.length} items</div>
                        </div>
                        <span class="rule-count${rowCount === 0 ? ' zero' : ''}">${rowCount}건</span>
                    </div>
                `;
            });
            html += '</div>';
            html += '</div>';
        }
        if (inline) {
            const titleEl = document.querySelector('.inline-detail-title');
            const bodyEl = document.querySelector('.inline-detail-body');
            if (titleEl) titleEl.style.display = 'none';
            if (bodyEl) bodyEl.innerHTML = html;
        } else {
            AppModal.setTitle('detail', ruleName + ' (' + (data.total_anomalies || 0) + '건)');
            AppModal.setBody('detail', html);
        }

    } catch (error) {
        console.error('Error:', error);
        const errHtml = '<p style="color: red;">데이터 로드 실패</p>';
        if (inline) {
            const body = document.querySelector('.inline-detail-body');
            if (body) body.innerHTML = errHtml;
        } else {
            AppModal.setBody('detail', errHtml);
        }
    }
}

// HTTP 환경용 폴백 복사 함수
function fallbackCopy(text, onSuccess, onError) {
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
        if (onSuccess) onSuccess();
    } catch (err) {
        console.error('복사 실패:', err);
        if (onError) onError(err);
    }
    document.body.removeChild(textArea);
}

// 클립보드 복사 함수 (HTTPS/HTTP 모두 지원)
function copyToClipboard(element) {
    const text = element.textContent;

    function showSuccess() {
        element.style.background = '#c8e6c9';
        element.setAttribute('data-copied', 'true');
        setTimeout(() => {
            element.style.background = '#e3f2fd';
            element.removeAttribute('data-copied');
        }, 1000);
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

// SQL 포맷팅 함수 (한줄 쿼리를 보기 좋게 정리)
function formatSQL(sql) {
    if (!sql) return sql;
    // 공백 정리 (연속 공백을 하나로)
    let formatted = sql.replace(/\s+/g, ' ').trim();
    // 주요 키워드 앞에 줄바꿈 추가
    const keywords = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'ORDER BY', 'GROUP BY', 'HAVING', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'LIMIT', 'OFFSET'];
    keywords.forEach(kw => {
        // 키워드가 문자열 중간에 있을 때만 줄바꿈 (맨 앞 SELECT 제외)
        const regex = new RegExp(`\\s+(${kw})\\s+`, 'gi');
        formatted = formatted.replace(regex, `\n${kw} `);
    });
    // AND 들여쓰기
    formatted = formatted.replace(/\nAND /gi, '\n    AND ');
    formatted = formatted.replace(/\nOR /gi, '\n    OR ');
    return formatted;
}

// 쿼리 박스용 복사 함수 (HTTPS/HTTP 모두 지원)
function copyQueryToClipboard(element) {
    const text = element.textContent;
    const formattedSQL = formatSQL(text);

    function showSuccess() {
        // 버튼 찾기 (여러 위치 지원)
        let btn = element.previousElementSibling?.querySelector?.('.btn-copy');
        if (!btn) btn = element.previousElementSibling?.querySelector?.('.btn-copy-query');
        if (!btn && element.nextElementSibling?.classList?.contains('btn-copy-query')) {
            btn = element.nextElementSibling;
        }
        if (btn) {
            const originalText = btn.textContent;
            const originalBg = btn.style.background;
            btn.textContent = '복사됨!';
            btn.style.background = '#22c55e';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.style.background = originalBg || '#3b82f6';
            }, 1500);
        }
    }

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(formattedSQL).then(showSuccess).catch(err => {
            console.error('복사 실패:', err);
            fallbackCopy(formattedSQL, showSuccess);
        });
    } else {
        fallbackCopy(formattedSQL, showSuccess);
    }
}

function copyUrlToClipboard(text, btn) {
    function onSuccess() {
        const orig = btn.textContent;
        btn.textContent = '완료';
        btn.style.background = '#22c55e';
        setTimeout(() => { btn.textContent = orig; btn.style.background = '#6b7280'; }, 1200);
    }
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(() => fallbackCopy(text, onSuccess));
    } else {
        fallbackCopy(text, onSuccess);
    }
}

// 크로스필드 검증 유형 목록으로 돌아가기
function backToCrossfieldSummary() {
    if (isCrossFieldInline()) {
        ViewStack.pop();
        // pop 후 규칙 카드 건수 갱신
        setTimeout(_cfUpdateRuleCardCount, 0);
        return;
    }
    if (window.crossfieldSummaryData && window.crossfieldTitle) {
        AppModal.setTitle('detail', window.crossfieldTitle + ` (${window.crossfieldSummaryData.total_anomalies}건)`);
        renderDetailModal(window.crossfieldTitle, '크로스 필드 검증', window.crossfieldSummaryData);
    }
}

// 카테고리별 특성 데이터 날짜 변경 시 재로드
async function reloadCategorySpecData(date, displayName, title) {
    const inline = isCatSpecInline();
    const bodyEl = inline ? document.querySelector('.inline-detail-body') : AppModal.getBody('detail');
    if (bodyEl) bodyEl.innerHTML = '<p style="text-align:center;">데이터를 불러오는 중...</p>';

    try {
        const data = await fetchAPI(`/layer3/api/category-spec-detail/?date=${date}&display_name=${encodeURIComponent(displayName)}&mode=summary`);

        if (data.error) {
            if (bodyEl) bodyEl.innerHTML = `<p style="color: red;">오류: ${esc(data.error)}</p>`;
            return;
        }

        // 공통 렌더링 (모달/인라인 모두 처리)
        renderCatSpecSummaryContent(title, data);

    } catch (error) {
        console.error('Error:', error);
        if (bodyEl) bodyEl.innerHTML = '<p style="color: red;">데이터 로드 실패</p>';
    }
}

// 카테고리별 특성 규칙별 상세 데이터 로드
let masterTableDetailState = {
    data: null, displayName: '', ruleId: '', date: '', ruleName: '', currentRetailer: 'all', currentPage: 1,
    filterProduct: 'all',   // 'all' | 'product' | 'non_product'
    filterChecked: 'all'    // 'all' | 'checked' | 'unchecked'
};
const SPEC_PAGE_SIZE = 20;
// is_product / is_checked 변경 추적: Map<mst_id, { is_product?, is_checked?, table }>
let specPendingChanges = new Map();
let specOriginalValues = new Map();  // Map<mst_id, { is_product, is_checked }>

async function loadCategorySpecRuleDetail(displayName, ruleId, date, ruleName) {
    const inline = isCatSpecInline();

    if (inline) {
        ViewStack.push(`
            <div class="inline-detail">
                <button class="btn-back" onclick="specCancelAndBack()">← 뒤로가기</button>
                <div class="inline-detail-title">${ruleName}</div>
                <div class="inline-detail-body"><p style="text-align:center;">데이터를 불러오는 중...</p></div>
            </div>
        `);
    } else {
        AppModal.setTitle('detail', ruleName);
        AppModal.setBody('detail', '<p style="text-align:center;">데이터를 불러오는 중...</p>');
    }

    try {
        const data = await fetchAPI(`/layer3/api/category-spec-detail/?date=${date}&display_name=${encodeURIComponent(displayName)}&rule_id=${ruleId}`);

        if (data.error) {
            const errTarget = inline ? document.querySelector('.inline-detail-body') : AppModal.getBody('detail');
            if (errTarget) errTarget.innerHTML = `<p style="color: red;">오류: ${esc(data.error)}</p>`;
            return;
        }

        // 리테일러별 탭으로 표시
        masterTableDetailState = { data, displayName, ruleId, date, ruleName, currentRetailer: 'all', currentPage: 1, filterProduct: 'all', filterChecked: 'all' };
        renderCategorySpecDetail(data, ruleName, 'all');

    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p style="color: red;">데이터 로드 실패</p>');
    }
}

// 카테고리 특성 상세보기 렌더링 (리테일러별 탭 + is_product 토글)
function renderCategorySpecDetail(data, ruleName, selectedRetailer) {
    const retailerCounts = data.retailer_counts || {};
    const retailerData = data.retailer_data || {};
    const allAnomalies = data.anomalies || [];
    const displayColumns = data.display_columns || [];
    const hasMstId = allAnomalies.some(r => r.mst_id != null);

    // 선택된 리테일러에 따른 데이터 필터링
    let retailerFiltered = [];
    if (selectedRetailer === 'all') {
        retailerFiltered = allAnomalies;
    } else {
        retailerFiltered = retailerData[selectedRetailer] || [];
    }

    // 제품여부 / 확인완료 필터 적용
    const fProduct = masterTableDetailState.filterProduct || 'all';
    const fChecked = masterTableDetailState.filterChecked || 'all';

    const filteredData = retailerFiltered.filter(row => {
        // 변경 대기 중인 행은 저장 전까지 항상 표시
        if (row.mst_id && specPendingChanges.has(row.mst_id)) return true;
        const ip = row.is_product;
        const ic = row.is_checked;
        if (fProduct === 'product' && ip === false) return false;
        if (fProduct === 'non_product' && ip !== false) return false;
        if (fChecked === 'checked' && ic !== true) return false;
        if (fChecked === 'unchecked' && ic === true) return false;
        return true;
    });

    // table key 결정 (tv / hhp)
    const productLine = (data.product_line || '').toUpperCase();
    const tableKey = productLine.includes('HHP') ? 'hhp' : 'tv';

    const inline = isCatSpecInline();
    let html = '';

    // 뒤로가기 버튼 (모달에서만, 인라인은 상위 컨테이너에 있음)
    if (!inline) {
        html += `<button class="btn-back" onclick="backToCategorySpecSummary()">← 뒤로가기</button>`;
    }

    // 리테일러 탭
    const retailers = Object.keys(retailerCounts).sort();
    const totalCount = allAnomalies.length;

    html += `<div class="retailer-tabs" style="display: flex; gap: 8px; margin: 16px 0; flex-wrap: wrap;">`;

    // All 탭
    html += `<button class="retailer-tab" onclick="switchMasterTableRetailer('all')" style="padding: 8px 16px; border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer; font-size: 13px; ${selectedRetailer === 'all' ? 'background: #3b82f6; color: white; border-color: #3b82f6;' : 'background: white; color: #374151;'}">
        All <span style="font-weight: 600;">(${totalCount})</span>
    </button>`;

    // 각 리테일러 탭
    retailers.forEach(retailer => {
        const count = retailerCounts[retailer];
        const isActive = selectedRetailer === retailer;
        html += `<button class="retailer-tab" onclick="switchMasterTableRetailer('${escJs(retailer)}')" style="padding: 8px 16px; border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer; font-size: 13px; ${isActive ? 'background: #3b82f6; color: white; border-color: #3b82f6;' : 'background: white; color: #374151;'}">
            ${esc(retailer)} <span style="font-weight: 600;">(${count})</span>
        </button>`;
    });

    html += `</div>`;

    // 제품여부 / 확인완료 필터 (인라인=섹션 페이지에서만)
    if (hasMstId && inline) {
        // 각 필터별 건수 계산 (리테일러 필터 적용 후 기준)
        let cntProduct = 0, cntNonProduct = 0, cntChecked = 0, cntUnchecked = 0;
        retailerFiltered.forEach(row => {
            const p = row.mst_id && specPendingChanges.has(row.mst_id) ? specPendingChanges.get(row.mst_id) : null;
            const ip = p && 'is_product' in p ? p.is_product : row.is_product;
            const ic = p && 'is_checked' in p ? p.is_checked : row.is_checked;
            if (ip === false) cntNonProduct++; else cntProduct++;
            if (ic === true) cntChecked++; else cntUnchecked++;
        });

        const fbtn = (type, value, label, count) => {
            const current = type === 'product' ? fProduct : fChecked;
            const active = current === value;
            return `<button onclick="specSetFilter('${type}','${value}')" style="padding: 4px 12px; border: 1px solid ${active ? '#6b7280' : '#e5e7eb'}; border-radius: 4px; cursor: pointer; font-size: 12px; background: ${active ? '#374151' : 'white'}; color: ${active ? 'white' : '#6b7280'};">${label} (${count})</button>`;
        };

        html += `<div style="display: flex; gap: 16px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">`;
        html += `<div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 12px; font-weight: 600; color: #6b7280;">제품여부</span>
            ${fbtn('product', 'all', '전체', retailerFiltered.length)}
            ${fbtn('product', 'product', '제품', cntProduct)}
            ${fbtn('product', 'non_product', '비제품', cntNonProduct)}
        </div>`;
        html += `<span style="width: 1px; height: 20px; background: #e5e7eb;"></span>`;
        html += `<div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 12px; font-weight: 600; color: #6b7280;">확인완료</span>
            ${fbtn('checked', 'all', '전체', retailerFiltered.length)}
            ${fbtn('checked', 'checked', '확인완료', cntChecked)}
            ${fbtn('checked', 'unchecked', '미확인', cntUnchecked)}
        </div>`;
        html += `</div>`;
    }

    // Item 목록 추출 (중복 제거)
    const items = [...new Set(filteredData.map(row => row.item).filter(item => item))];

    if (items.length > 0) {
        const tableName = data.table_name || (tableKey === 'hhp' ? 'hhp_item_mst' : 'tv_item_mst');
        const inClauseWithQuotes = items.map(item => `'${item}'`).join(', ');
        const itemListDisplay = items.join(', ');

        let retailerCondition = '';
        if (selectedRetailer !== 'all') {
            retailerCondition = `\n  AND account_name = '${selectedRetailer}'`;
        }

        let selectColumns = 'id, account_name, item, is_product, product_url';
        if (displayColumns.length > 0) {
            selectColumns = displayColumns.map(col => col.key).join(', ');
        }

        const query = `SELECT ${selectColumns}
FROM ${tableName}
WHERE item IN (${inClauseWithQuotes})${retailerCondition}
ORDER BY account_name, item;`;

        html += `
        <div class="query-section">
            <div class="item-list-box">
                <div class="query-box-header">
                    <span class="query-box-title">Item 목록 (${items.length}개)</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById('spec-item-list'))">복사</button>
                </div>
                <div id="spec-item-list" class="item-list-content">${esc(itemListDisplay)}</div>
            </div>
            <div class="query-box">
                <div class="query-box-header">
                    <span class="query-box-title">조회 쿼리</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById('spec-query-box'))">복사</button>
                </div>
                <pre id="spec-query-box" class="query-content">${esc(query)}</pre>
            </div>
        </div>`;
    }

    // 데이터 테이블
    if (filteredData.length === 0) {
        html += '<p>해당 리테일러에 대한 이상치 데이터가 없습니다.</p>';
    } else {
        // 변경 건수 저장 바 (인라인=섹션 페이지에서만)
        const pendingCount = specPendingChanges.size;
        if (pendingCount > 0 && inline) {
            html += `
            <div id="spec-save-bar" style="background: #fefce8; border: 2px solid #eab308; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-radius: 8px;">
                <span style="font-size: 13px; font-weight: 600; color: #854d0e;">${pendingCount}건 변경됨</span>
                <div style="display: flex; gap: 8px;">
                    ${AppButton.html('취소', 'specCancelChanges', { style: 'cancel', size: 'sm' })}
                    ${AppButton.html('저장', 'specSaveChanges', { style: 'save', size: 'sm' })}
                </div>
            </div>`;
        }
        html += '<div class="table-scroll-container"><table class="detail-table"><thead><tr>';
        html += '<th>No.</th>';

        // display_columns가 없으면 데이터 키에서 자동 생성 (mst_id, is_product, is_checked 제외)
        const hiddenKeys = ['id', 'mst_id', 'is_product', 'is_checked'];
        const cols = displayColumns.length > 0 ? displayColumns
            : Object.keys(filteredData[0] || {}).filter(k => !hiddenKeys.includes(k)).map(k => ({ key: k, label: k }));

        cols.forEach(col => {
            html += `<th>${esc(col.label)}</th>`;
        });
        // is_product / is_checked 토글 컬럼 (인라인=섹션 페이지에서만)
        if (hasMstId && inline) {
            html += '<th style="text-align: center; min-width: 70px; white-space: nowrap;">제품여부</th>';
            html += '<th style="text-align: center; min-width: 70px; white-space: nowrap;">확인완료</th>';
        }
        html += '</tr></thead><tbody>';

        // 페이지네이션 계산
        const totalRows = filteredData.length;
        const totalPages = Math.ceil(totalRows / SPEC_PAGE_SIZE);
        const currentPage = masterTableDetailState.currentPage || 1;
        const startIdx = (currentPage - 1) * SPEC_PAGE_SIZE;
        const endIdx = Math.min(startIdx + SPEC_PAGE_SIZE, totalRows);
        const pageData = filteredData.slice(startIdx, endIdx);

        pageData.forEach((row, idx) => {
            const mstId = row.mst_id;
            const pending = mstId && specPendingChanges.has(mstId) ? specPendingChanges.get(mstId) : null;
            const isProduct = pending && 'is_product' in pending ? pending.is_product : row.is_product;
            const isChecked = pending && 'is_checked' in pending ? pending.is_checked : row.is_checked;
            const isNonProduct = isProduct === false;
            let rowStyle = '';
            if (pending) rowStyle = 'background: #fefce8;';
            else if (isNonProduct) rowStyle = 'opacity: 0.45;';

            html += `<tr style="${rowStyle}">`;
            html += `<td>${startIdx + idx + 1}</td>`;
            cols.forEach(col => {
                const value = row[col.key];
                if (col.key.toLowerCase().includes('url') && value) {
                    const safe = safeUrl(value);
                    if (safe) {
                        const escaped = safe.replace(/'/g, "\\'");
                        html += `<td style="white-space: nowrap;">
                            <a href="${esc(safe)}" target="_blank" style="color: #3b82f6; text-decoration: none;">링크</a>
                            ${AppButton.iconHtml('copy', "copyUrlToClipboard('" + escaped + "', this)", { style: 'ghost', title: 'URL 복사' })}
                        </td>`;
                    } else {
                        html += '<td>-</td>';
                    }
                } else {
                    html += `<td>${value !== null && value !== undefined ? esc(String(value)) : '-'}</td>`;
                }
            });
            // is_product + is_checked 토글 (인라인=섹션 페이지에서만)
            if (hasMstId && inline) {
                if (mstId) {
                    if (!specOriginalValues.has(mstId)) {
                        specOriginalValues.set(mstId, { is_product: row.is_product, is_checked: row.is_checked });
                    }
                    const prodChecked = isProduct ? 'checked' : '';
                    const chkChecked = isChecked ? 'checked' : '';
                    html += `<td style="text-align: center;">
                        <input type="checkbox" ${prodChecked} onchange="toggleSpecField(${mstId}, 'is_product', this.checked, '${tableKey}')"
                            style="width: 16px; height: 16px; cursor: pointer; accent-color: #7c3aed;">
                    </td>`;
                    html += `<td style="text-align: center;">
                        <input type="checkbox" ${chkChecked} onchange="toggleSpecField(${mstId}, 'is_checked', this.checked, '${tableKey}')"
                            style="width: 16px; height: 16px; cursor: pointer; accent-color: #059669;">
                    </td>`;
                } else {
                    html += '<td style="text-align: center; color: #9ca3af;" title="마스터 미등록">-</td>';
                    html += '<td style="text-align: center; color: #9ca3af;" title="마스터 미등록">-</td>';
                }
            }
            html += '</tr>';
        });

        html += '</tbody></table></div>';

        // 페이지네이션 컨테이너
        html += `<div id="spec-pagination-container"></div>`;
    }

    // 건수 계산: 리테일러 필터 기준 (제품여부/확인완료 필터 적용 전)
    const displayTotal = retailerFiltered.length;
    let nonProductCount = 0;
    let checkedCount = 0;
    retailerFiltered.forEach(r => {
        const p = r.mst_id && specPendingChanges.has(r.mst_id) ? specPendingChanges.get(r.mst_id) : null;
        const ip = p && 'is_product' in p ? p.is_product : r.is_product;
        const ic = p && 'is_checked' in p ? p.is_checked : r.is_checked;
        if (ip === false) nonProductCount++;
        else if (ic === true) checkedCount++;
    });
    const excludeCount = nonProductCount + checkedCount;
    const activeCount = displayTotal - excludeCount;
    const retailerLabel = selectedRetailer === 'all' ? '전체' : selectedRetailer;
    let countLabel = `${displayTotal}건`;
    if (excludeCount > 0) {
        const parts = [];
        if (nonProductCount > 0) parts.push(`비제품 ${nonProductCount}`);
        if (checkedCount > 0) parts.push(`확인완료 ${checkedCount}`);
        countLabel = `${activeCount}건 (${parts.join(', ')}건 제외)`;
    }
    const hasFilter = fProduct !== 'all' || fChecked !== 'all';
    const filterLabel = hasFilter ? ` [필터: ${filteredData.length}건]` : '';
    const titleText = `${ruleName} - ${retailerLabel} ${countLabel}${filterLabel}`;
    if (inline) {
        const titleEl = document.querySelector('.inline-detail-title');
        const bodyEl = document.querySelector('.inline-detail-body');
        if (titleEl) titleEl.innerHTML = _inlineTitle(titleText);
        if (bodyEl) bodyEl.innerHTML = html;
    } else {
        AppModal.setTitle('detail', titleText);
        AppModal.setBody('detail', html);
    }

    // 페이지네이션 바인딩
    const paginationEl = document.getElementById('spec-pagination-container');
    if (paginationEl && filteredData.length > SPEC_PAGE_SIZE) {
        new Pagination(paginationEl, {
            pageSize: SPEC_PAGE_SIZE,
            onPageChange: (page) => specGoToPage(page)
        }).render(filteredData.length, masterTableDetailState.currentPage || 1);
    }
}

// is_product / is_checked 토글 (통합)
function toggleSpecField(mstId, field, value, tableKey) {
    const original = specOriginalValues.get(mstId) || {};
    const pending = specPendingChanges.get(mstId) || { table: tableKey };
    pending[field] = value;
    pending.table = tableKey;

    // 제품여부 변경 시 확인완료 자동 연동
    if (field === 'is_product') {
        if (value === original.is_product) {
            // 원래 값으로 돌아오면 is_checked도 원복
            delete pending.is_checked;
        } else {
            pending.is_checked = true;
        }
    }

    // 모든 필드가 원본과 같으면 pending에서 제거
    const allSame = Object.keys(original).every(k => {
        if (!(k in pending)) return true;
        return pending[k] === original[k];
    });
    if (allSame) {
        specPendingChanges.delete(mstId);
    } else {
        specPendingChanges.set(mstId, pending);
    }

    if (isCatSpecInline()) {
        const scrollY = window.scrollY;
        renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);
        window.scrollTo(0, scrollY);
    } else {
        const modalBody = AppModal.getBody('detail');
        const scrollTop = modalBody.scrollTop;
        renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);
        modalBody.scrollTop = scrollTop;
    }
}

// 하위 호환 (기존 호출 유지)
function toggleSpecIsProduct(mstId, isProduct, tableKey) {
    toggleSpecField(mstId, 'is_product', isProduct, tableKey);
}

// 변경 취소 후 뒤로가기 (인라인 규칙 상세에서)
function specCancelAndBack() {
    specPendingChanges.clear();
    specOriginalValues.clear();
    ViewStack.pop();
}

// 변경 취소
function specCancelChanges() {
    specPendingChanges.clear();
    specOriginalValues.clear();
    renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);
}

// 변경 저장
async function specSaveChanges() {
    if (specPendingChanges.size === 0) return;

    // table별로 그룹화
    const byTable = {};
    specPendingChanges.forEach((val, mstId) => {
        const t = val.table || 'tv';
        if (!byTable[t]) byTable[t] = [];
        const change = { id: mstId };
        if ('is_product' in val) change.is_product = val.is_product;
        if ('is_checked' in val) change.is_checked = val.is_checked;
        byTable[t].push(change);
    });

    try {
        for (const [tableKey, changes] of Object.entries(byTable)) {
            const res = await fetch('/dx/data/api/item-master/save/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ table: tableKey, changes, user_id: window.LAYER3.username || '' })
            });
            const result = await res.json();
            if (result.error) {
                showToast(result.error, 'error');
                return;
            }
        }

        showToast(`${specPendingChanges.size}건 저장 완료`, 'success');

        // anomalies / retailer_data에 변경 반영
        const applyChanges = (row) => {
            if (!row.mst_id || !specPendingChanges.has(row.mst_id)) return;
            const p = specPendingChanges.get(row.mst_id);
            if ('is_product' in p) row.is_product = p.is_product;
            if ('is_checked' in p) row.is_checked = p.is_checked;
        };
        (masterTableDetailState.data.anomalies || []).forEach(applyChanges);
        const rd = masterTableDetailState.data.retailer_data || {};
        Object.values(rd).forEach(rows => rows.forEach(applyChanges));

        specPendingChanges.clear();
        specOriginalValues.clear();
        renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);

    } catch (e) {
        showToast('저장 실패: ' + e.message, 'error');
    }
}

// 필터 전환
function specSetFilter(type, value) {
    if (type === 'product') masterTableDetailState.filterProduct = value;
    else if (type === 'checked') masterTableDetailState.filterChecked = value;
    masterTableDetailState.currentPage = 1;
    renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);
}

// 리테일러 탭 전환
function switchMasterTableRetailer(retailer) {
    masterTableDetailState.currentRetailer = retailer;
    masterTableDetailState.currentPage = 1;
    renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, retailer);
}

function specGoToPage(page) {
    masterTableDetailState.currentPage = page;
    renderCategorySpecDetail(masterTableDetailState.data, masterTableDetailState.ruleName, masterTableDetailState.currentRetailer);
    // 테이블 상단으로 스크롤
    const tableEl = document.querySelector('.table-scroll-container');
    if (tableEl) tableEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 카테고리별 특성 규칙 요약으로 돌아가기
function backToCategorySpecSummary() {
    specPendingChanges.clear();
    specOriginalValues.clear();
    if (isCatSpecInline()) {
        ViewStack.pop();
        return;
    }
    if (window.categorySpecSummaryData && window.categorySpecTitle) {
        AppModal.setTitle('detail', window.categorySpecTitle + ` (${window.categorySpecSummaryData.total_anomalies}건)`);
        renderDetailModal(window.categorySpecTitle, '카테고리별 특성', window.categorySpecSummaryData);
    }
}

// 리테일러 상세 데이터 표시
function showRetailerDetail(retailer) {
    const inline = isCrossFieldInline();
    const retailerData = window.crossfieldRetailerData;
    if (!retailerData || !retailerData[retailer]) return;

    const data = retailerData[retailer];
    const rows = data.rows;
    const items = data.items;

    const productLine = window.crossfieldProductLine || 'HHP';
    const date = window.crossfieldDate || new Date().toISOString().slice(0, 10);
    const tableName = productLine.toUpperCase() === 'HHP' ? 'hhp_retail_com' : 'tv_retail_com';
    const dateCol = productLine.toUpperCase() === 'HHP' ? 'crawl_strdatetime' : 'crawl_datetime';
    const productLineDisplay = productLine.toUpperCase();
    const ruleNameDisplay = window.crossfieldRuleName || '';
    const titleText = `${ruleNameDisplay} (${rows.length}건)`;
    const subtitleText = `${productLineDisplay} Retail | ${retailer}`;

    const editableCols = inline ? (window.crossfieldEditableCols || new Set()) : new Set();
    const normalReviews = inline ? (window.crossfieldNormalReviews || {}) : {};

    // 동적 컬럼
    const excludeKeys = ['id', 'item', 'account_name', 'page_type'];
    const dynamicKeys = [];
    if (rows.length > 0) {
        Object.keys(rows[0]).forEach(key => {
            if (!excludeKeys.includes(key)) dynamicKeys.push(key);
        });
    }
    const urlKey = dynamicKeys.find(k => k === 'product_url');
    const otherKeys = dynamicKeys.filter(k => k !== 'product_url');

    // --- 인라인 모드: Layer2 스타일 ---
    if (inline) {
        const _wn = ['일','월','화','수','목','금','토'][new Date(date).getDay()];
        const dateDisplay = `${date}(${_wn})`;

        // Item 목록 토글
        const retailerSafe = retailer.replace(/[^a-zA-Z0-9]/g, '');
        const itemListDisplay = items.join(', ');
        const itemQueryHtml = `
            <div class="item-toggle-section">
                <div class="item-toggle-header" onclick="var c=this.nextElementSibling;c.style.display=c.style.display==='none'?'':'none';this.querySelector('.toggle-arrow').textContent=c.style.display==='none'?'▸':'▾';">
                    <span class="toggle-arrow">▸</span> Item 목록 (${items.length}개)
                </div>
                <div class="item-toggle-content" style="display:none;">
                    <div class="item-copy-header">
                        <span class="item-copy-title">Item 목록 (${items.length}개)</span>
                        <button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById('item-list-${retailerSafe}'))">복사</button>
                    </div>
                    <div id="item-list-${retailerSafe}" class="item-copy-content">${esc(itemListDisplay)}</div>
                </div>
            </div>`;

        // 컬럼 정의: 기본 표시 컬럼
        const allColumns = [
            { key: '_no', label: 'No', width: 50, fixed: true },
            { key: 'id', label: 'id', width: 80 },
            { key: 'item', label: 'item', width: 140 },
            { key: 'page_type', label: 'page_type', width: 80 }
        ];
        otherKeys.forEach(k => {
            allColumns.push({ key: k, label: k, width: 140 });
        });
        if (urlKey) {
            allColumns.push({ key: 'product_url', label: 'product_url', width: 100 });
        }
        const defaultVisibleKeys = allColumns.map(c => c.key);

        // 리테일러 전체 수집 컬럼 추가 (컬럼 선택용, 기본 비표시)
        const retailerCols = (window.crossfieldRetailerColumns || {})[retailer] || [];
        const existingKeys = {};
        allColumns.forEach(c => { existingKeys[c.key] = true; });
        retailerCols.forEach(col => {
            if (!existingKeys[col]) {
                allColumns.push({ key: col, label: col, width: 120 });
            }
        });

        // 컨테이너 HTML
        const containerHtml = `<div class="detail-view-wrapper">
            <div id="cf-detail-item-query">${itemQueryHtml}</div>
            <div id="cf-detail-filter-bar"></div>
            <div id="cf-detail-action-bar"></div>
            <div id="cf-detail-table-area"></div>
            <div id="cf-detail-pagination"></div>
        </div>`;

        const daysInputHtml = `<div style="display:flex;align-items:center;gap:6px;margin-right:12px;">
            <label style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">일수:</label>
            <input type="number" id="cf-detail-days" value="1" min="1" max="30"
                style="width:50px;padding:3px 6px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;font-size:12px;text-align:center;"
                onkeydown="if(event.key==='Enter')reloadCfDays()">
            <button onclick="reloadCfDays()" style="padding:3px 10px;font-size:12px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;background:var(--page-color,#0d9488);color:#fff;cursor:pointer;white-space:nowrap;">조회</button>
        </div>`;

        const wrapper = `<div class="inline-detail-view">
            <div class="inline-detail-header"><div>
                <div class="inline-detail-title">${esc(titleText)}</div>
                <div class="inline-detail-subtitle">${esc(subtitleText)}</div>
            </div><div style="display:flex;align-items:center;">${daysInputHtml}<div class="inline-detail-date">${dateDisplay}</div></div></div>
            <div id="cf-detail-body">${containerHtml}</div>
        </div>`;

        ViewStack.push(`
            <div class="inline-detail">
                <button class="btn-back" onclick="ViewStack.pop()">← 뒤로가기</button>
                ${wrapper}
            </div>
        `);

        // 데이터 준비 (CommonTable 형식) - 전체 수집 컬럼 포함
        const tableRows = rows.map((row, idx) => {
            const r = { _no: idx + 1, id: row.id || '-', item: row.item || '-', page_type: row.page_type || '-' };
            otherKeys.forEach(key => {
                r[key] = row[key] !== null && row[key] !== undefined ? String(row[key]) : '-';
            });
            // 추가 수집 컬럼 (컬럼 선택 시 표시용)
            retailerCols.forEach(col => {
                if (!(col in r)) {
                    r[col] = row[col] !== null && row[col] !== undefined ? String(row[col]) : '-';
                }
            });
            if (urlKey) {
                const url = safeUrl(row[urlKey]);
                r['product_url'] = url ? `<a href="${esc(url)}" target="_blank" style="color:#1976d2;">링크</a>` : '-';
            }
            // 편집용 메타데이터
            r._rowId = row.id;
            r._rowDate = (row[dateCol] || '').substring(0, 10);
            return r;
        });

        // 현재 리테일러 저장 (일수 재조회용)
        window._cfCurrentRetailer = retailer;

        // 상태 저장
        window._cfDetailState = {
            _ruleId: window.crossfieldRuleId || '',
            allData: tableRows,
            filteredData: null,
            allColumns: allColumns,
            visibleKeys: defaultVisibleKeys.slice(),
            editableCols: editableCols,
            normalReviews: normalReviews,
            sortState: [],
            table: null,
            filterBar: null,
            pager: null
        };

        // FilterBar
        const filterCols = [{ value: 'id', label: 'id' }, { value: 'item', label: 'item' }];
        otherKeys.forEach(k => filterCols.push({ value: k, label: k }));

        window._cfDetailState.filterBar = new FilterBar('#cf-detail-filter-bar', {
            sticky: false,
            padding: '8px 12px',
            controls: [
                { type: 'select', key: 'filterCol', label: '항목', width: 'auto', options: filterCols },
                { type: 'input', key: 'filterVal', placeholder: '검색어 입력...', onEnter: function() { _cfApplyFilter(); } }
            ],
            onSearch: function() { _cfApplyFilter(); },
            onReset: function() { _cfClearFilter(); },
            columnSelector: {
                columns: allColumns.map(c => ({ key: c.key, label: c.label })),
                fixed: ['_no'],
                defaultVisible: defaultVisibleKeys,
                onUpdate: function(selected) {
                    window._cfDetailState.visibleKeys = selected;
                    _cfRebuildTable();
                }
            },
            right: [
                { type: 'button', label: '정렬 초기화', style: 'outline', size: 'fb', onClick: function() { window._cfDetailState.sortState = []; _cfRebuildTable(); } }
            ]
        }).render();

        // CommonTable + Pagination 빌드
        _cfRebuildTable();

        // 편집/정상처리 이벤트
        setTimeout(function() { _cfBindEditEvents(); }, 100);

    } else {
        // --- 모달 모드: 기존 방식 ---
        let html = '';
        html += `<button class="btn-back" onclick="backToRetailerList()">← 뒤로가기</button>`;

        // 쿼리 생성
        let dynamicCols = [];
        const selectFieldsRaw = window.crossfieldSelectFields || '';
        if (selectFieldsRaw) {
            dynamicCols = selectFieldsRaw.split('|').map(f => f.trim()).filter(f => f);
        } else {
            const excludeCols = ['id', 'item', dateCol, 'account_name', 'product_url', 'page_type'];
            if (rows.length > 0) {
                Object.keys(rows[0]).forEach(key => {
                    if (!excludeCols.includes(key)) dynamicCols.push(key);
                });
            }
        }
        const inClauseWithQuotes = items.map(item => `'${item}'`).join(', ');
        const validationType = window.crossfieldValidationType || '';
        let validationTagCol = '';
        if (validationType === 'cross_detail_mismatch') {
            validationTagCol = `\n'review' || LEAST(CAST(REPLACE(count_of_reviews, ',', '') AS INTEGER), 20)::text || ' -' AS expected_pattern,\nCASE WHEN LOWER(detailed_review_content) LIKE '%review' || LEAST(CAST(REPLACE(count_of_reviews, ',', '') AS INTEGER), 20)::text || ' -%' THEN 'OK' ELSE 'MISSING' END AS validation_tag,`;
        }
        let selectCols = ['id', 'account_name', 'item', dateCol].join(', ');
        const query = `SELECT ${selectCols},${validationTagCol}\n${dynamicCols.join(', ')}, product_url\nFROM ${tableName}\nWHERE account_name = '${retailer}'\nAND item IN (${inClauseWithQuotes})\nAND DATE(${dateCol}::timestamp) >= DATE('${date}') - INTERVAL '2 days'\nAND DATE(${dateCol}::timestamp) <= DATE('${date}')\nORDER BY item, ${dateCol};`;

        const retailerSafe = retailer.replace(/[^a-zA-Z0-9]/g, '');
        const itemListDisplay = items.join(', ');
        html += `<div class="query-section">
            <div class="item-list-box">
                <div class="query-box-header">
                    <span class="query-box-title">${esc(retailer)} - Item 목록 (${items.length}개)</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById('item-list-${retailerSafe}'))">복사</button>
                </div>
                <div id="item-list-${retailerSafe}" class="item-list-content">${esc(itemListDisplay)}</div>
            </div>
            <div class="query-box">
                <div class="query-box-header">
                    <span class="query-box-title">3일치 조회 쿼리</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById('query-box-${retailerSafe}'))">복사</button>
                </div>
                <pre id="query-box-${retailerSafe}" class="query-content">${esc(query)}</pre>
            </div>
        </div>`;

        html += '<div class="table-scroll-container"><table class="detail-table"><thead><tr>';
        html += '<th>No.</th><th>ID</th><th>Item</th><th>Page Type</th>';
        otherKeys.forEach(key => { html += `<th>${key.toUpperCase()}</th>`; });
        if (urlKey) html += '<th>URL</th>';
        html += '</tr></thead><tbody>';
        rows.forEach((row, idx) => {
            html += '<tr>';
            html += `<td>${idx + 1}</td>`;
            html += `<td>${esc(String(row.id || '-'))}</td>`;
            html += `<td>${esc(row.item || '-')}</td>`;
            html += `<td>${esc(row.page_type || '-')}</td>`;
            otherKeys.forEach(key => {
                const value = row[key];
                html += `<td>${value !== null && value !== undefined ? esc(String(value)) : '-'}</td>`;
            });
            if (urlKey) {
                const url = safeUrl(row[urlKey]);
                html += url ? `<td><a href="${esc(url)}" target="_blank" style="color:#1976d2;">링크</a></td>` : '<td>-</td>';
            }
            html += '</tr>';
        });
        html += '</tbody></table></div>';

        const modalTitle = `${ruleNameDisplay} : ${productLineDisplay} ${retailer} (${rows.length}건)`;
        window.crossfieldCurrentTitle = AppModal.getTitle('detail');
        AppModal.setTitle('detail', modalTitle);
        AppModal.setBody('detail', html);
    }
}

// ---- 크로스필드 상세 CommonTable 헬퍼 ----
function _cfRebuildTable() {
    var st = window._cfDetailState;
    if (!st) return;
    var visibleCols = st.allColumns.filter(c => st.visibleKeys.includes(c.key));
    st._visibleCols = visibleCols;

    var ctColumns = visibleCols.map(c => ({
        key: c.key,
        label: c.label,
        width: c.width,
        sortable: c.key !== '_no',
        align: c.key === '_no' ? 'center' : undefined
    }));

    st.table = new CommonTable('#cf-detail-table-area', {
        variant: 'detail',
        columns: ctColumns,
        vlines: true,
        section: true,
        showTotalCount: true,
        padding: '6px 12px',
        reorder: true,
        fixedColumns: ['_no'],
        multiSort: true,
        onSort: function(sortArr) {
            st.sortState = sortArr;
            _cfSortAndRender();
        }
    }).render();

    var pageSize = 15;
    st.pager = new Pagination('#cf-detail-pagination', {
        pageSize: pageSize,
        showInfo: true,
        padding: '0',
        margin: '0',
        border: 'none',
        onPageChange: function(page) { _cfRenderPage(page); }
    });

    _cfSortAndRender();
}

function _cfSortAndRender() {
    var st = window._cfDetailState;
    if (!st) return;
    var dataArr = st.filteredData || st.allData;

    // 정상 처리된 행 제외
    if (st.editableCols && st.editableCols.size > 0 && st.normalReviews) {
        dataArr = dataArr.filter(function(row) {
            var rowId = row._rowId;
            if (!rowId) return true;
            var hasNormal = false;
            st.editableCols.forEach(function(col) {
                if (st.normalReviews[rowId + '_' + col]) hasNormal = true;
            });
            return !hasNormal;
        });
    }

    if (st.sortState && st.sortState.length > 0) {
        dataArr = dataArr.slice().sort(function(a, b) {
            for (var i = 0; i < st.sortState.length; i++) {
                var s = st.sortState[i];
                var va = a[s.key] || '', vb = b[s.key] || '';
                var na = parseFloat(va), nb = parseFloat(vb);
                var cmp = 0;
                if (!isNaN(na) && !isNaN(nb)) cmp = na - nb;
                else cmp = String(va).localeCompare(String(vb));
                if (cmp !== 0) return s.order === 'asc' ? cmp : -cmp;
            }
            return 0;
        });
    }
    st._sortedData = dataArr;
    _cfRenderPage(1);

    // 헤더 타이틀 건수 갱신
    var titleEl = document.querySelector('.inline-detail-title');
    if (titleEl) {
        titleEl.textContent = titleEl.textContent.replace(/\(\d+건\)/, '(' + dataArr.length + '건)');
    }
}

function _cfRenderPage(page) {
    var st = window._cfDetailState;
    if (!st || !st.table) return;
    var dataArr = st._sortedData || st.allData;
    var pageSize = 15;
    var start = (page - 1) * pageSize;
    var pageData = dataArr.slice(start, start + pageSize);
    pageData.forEach(function(r, i) { r._no = start + i + 1; });

    var visibleCols = st._visibleCols || st.allColumns;

    // renderBody로 tr을 직접 생성 (td에 data-editable, cell-normal 등 속성 부여)
    var targetDate = window.crossfieldDate || '';
    st.table.renderBody(pageData, function(row) {
        var tr = '<tr>';
        var rowId = row._rowId;
        var isTargetDate = row._rowDate === targetDate;
        visibleCols.forEach(function(c) {
            var val = row[c.key];
            var displayVal = val !== null && val !== undefined ? String(val) : '-';

            if (c.key === '_no') {
                tr += '<td style="text-align:center;">' + displayVal + '</td>';
                return;
            }
            if (c.key === 'product_url') {
                tr += '<td>' + displayVal + '</td>';
                return;
            }

            var nrKey = rowId + '_' + c.key;
            if (isTargetDate && st.normalReviews[nrKey]) {
                var nr = st.normalReviews[nrKey];
                var tip = '정상 처리됨';
                if (nr.reason) tip += ' | 사유: ' + nr.reason;
                if (nr.memo) tip += ' | 메모: ' + nr.memo;
                tr += '<td class="cell-normal" data-row-id="' + rowId + '" data-col="' + esc(c.key) + '" data-normal-key="' + nrKey + '" title="' + esc(tip) + '">' + esc(displayVal) + '<span class="normal-badge">정상</span></td>';
            } else if (isTargetDate && st.editableCols.has(c.key) && rowId) {
                tr += '<td data-editable="true" data-row-id="' + rowId + '" data-col="' + esc(c.key) + '">' + esc(displayVal) + '</td>';
            } else if (isTargetDate && rowId) {
                tr += '<td data-row-id="' + rowId + '" data-col="' + esc(c.key) + '">' + esc(displayVal) + '</td>';
            } else {
                tr += '<td>' + esc(displayVal) + '</td>';
            }
        });
        tr += '</tr>';
        return tr;
    });

    // 페이지네이션 UI 갱신
    if (st.pager) st.pager.render(dataArr.length, page);

    // 총 건수 덮어쓰기
    var countEl = document.querySelector('#cf-detail-table-area .ct-count');
    if (countEl) {
        var suffix = st.filteredData ? ' (필터 적용)' : '';
        countEl.innerHTML = '총 <strong>' + dataArr.length.toLocaleString() + '</strong>건' + suffix;
    }

    // 편집 이벤트 재바인딩
    if (st.editableCols && st.editableCols.size > 0) {
        setTimeout(function() { _cfBindEditEvents(); }, 50);
    }
}

function _cfApplyFilter() {
    var st = window._cfDetailState;
    if (!st || !st.filterBar) return;
    var vals = st.filterBar.getValues();
    var col = vals.filterCol;
    var keyword = (vals.filterVal || '').trim().toLowerCase();
    if (!keyword) { _cfClearFilter(); return; }
    st.filteredData = st.allData.filter(function(r) {
        return String(r[col] || '').toLowerCase().includes(keyword);
    });
    _cfSortAndRender();
}

function _cfClearFilter() {
    var st = window._cfDetailState;
    if (!st) return;
    st.filteredData = null;
    if (st.filterBar) st.filterBar.reset();
    _cfSortAndRender();
}


// 일수 변경하여 크로스필드 상세 재조회
async function reloadCfDays() {
    var daysInput = document.getElementById('cf-detail-days');
    var days = daysInput ? parseInt(daysInput.value) || 1 : 1;
    if (days < 1) days = 1;
    if (days > 30) days = 30;

    var productLine = (window.crossfieldProductLine || 'tv').toLowerCase();
    var date = window.crossfieldDate || '';
    var ruleId = window._cfDetailState?._ruleId || '';
    var currentRetailer = window._cfCurrentRetailer || '';

    if (!ruleId || !date) return;

    // 로딩 표시
    var tableArea = document.getElementById('cf-detail-table-area');
    if (tableArea) tableArea.innerHTML = '<p style="text-align:center;padding:20px;">데이터를 불러오는 중...</p>';

    try {
        var data = await fetchAPI(`/layer3/api/cross-field-detail/?date=${date}&type=${productLine}&rule_id=${ruleId}&days=${days}`);
        if (data.error) {
            if (tableArea) tableArea.innerHTML = '<p style="color:red;">오류: ' + esc(data.error) + '</p>';
            return;
        }

        // 데이터 갱신
        var anomalies = data.anomalies || [];
        var retailerData = {};
        anomalies.forEach(function(row) {
            var retailer = row.account_name || 'Unknown';
            if (!retailerData[retailer]) retailerData[retailer] = { items: [], rows: [] };
            retailerData[retailer].rows.push(row);
            if (row.item && !retailerData[retailer].items.includes(row.item)) {
                retailerData[retailer].items.push(row.item);
            }
        });

        window.crossfieldRetailerData = retailerData;
        window.crossfieldAnomalies = anomalies;
        window.crossfieldEditableCols = new Set(data.editable_columns || []);
        window.crossfieldNormalReviews = data.normal_reviews || {};
        window.crossfieldRetailerColumns = data.retailer_columns || {};
        window.crossfieldPendingEdits = {};

        // 현재 리테일러 데이터 갱신
        if (currentRetailer && retailerData[currentRetailer]) {
            var rows = retailerData[currentRetailer].rows;
            var items = retailerData[currentRetailer].items;
            var editableCols = window.crossfieldEditableCols;
            var normalReviews = window.crossfieldNormalReviews;

            // 동적 컬럼
            var excludeKeys = ['id', 'item', 'account_name', 'page_type'];
            var dynamicKeys = [];
            if (rows.length > 0) {
                Object.keys(rows[0]).forEach(function(key) {
                    if (!excludeKeys.includes(key)) dynamicKeys.push(key);
                });
            }
            var urlKey = dynamicKeys.find(function(k) { return k === 'product_url'; });
            var otherKeys = dynamicKeys.filter(function(k) { return k !== 'product_url'; });

            var tableRows = rows.map(function(row, idx) {
                var r = { _no: idx + 1, id: row.id || '-', item: row.item || '-', page_type: row.page_type || '-' };
                otherKeys.forEach(function(key) {
                    r[key] = row[key] !== null && row[key] !== undefined ? String(row[key]) : '-';
                });
                if (urlKey) {
                    var url = safeUrl(row[urlKey]);
                    r['product_url'] = url ? '<a href="' + esc(url) + '" target="_blank" style="color:#1976d2;">링크</a>' : '-';
                }
                r._rowId = row.id;
                var dateCol = (window.crossfieldProductLine || 'tv').toUpperCase() === 'HHP' ? 'crawl_strdatetime' : 'crawl_datetime';
                r._rowDate = (row[dateCol] || '').substring(0, 10);
                return r;
            });

            var st = window._cfDetailState;
            if (st) {
                st.allData = tableRows;
                st.filteredData = null;
                st.editableCols = editableCols;
                st.normalReviews = normalReviews;
                st.sortState = [];

                // 컬럼 갱신: 추가된 수집 컬럼 반영
                var existKeys = {};
                st.allColumns.forEach(function(c) { existKeys[c.key] = true; });
                otherKeys.forEach(function(k) {
                    if (!existKeys[k]) {
                        st.allColumns.splice(st.allColumns.length - (urlKey ? 1 : 0), 0, { key: k, label: k, width: 120 });
                        existKeys[k] = true;
                    }
                });

                // 타이틀 업데이트
                var titleEl = document.querySelector('.inline-detail-title');
                var daysLabel = days > 1 ? ' / ' + days + '일치' : '';
                var ruleNameDisplay = window.crossfieldRuleName || '';
                if (titleEl) titleEl.textContent = ruleNameDisplay + ' (' + rows.length + '건' + daysLabel + ')';

                // 아이템 목록 갱신
                var retailerSafe = currentRetailer.replace(/[^a-zA-Z0-9]/g, '');
                var itemListEl = document.getElementById('item-list-' + retailerSafe);
                if (itemListEl) itemListEl.textContent = items.join(', ');
                var toggleHeader = document.querySelector('.item-toggle-header');
                if (toggleHeader) {
                    var arrow = toggleHeader.querySelector('.toggle-arrow');
                    var arrowText = arrow ? arrow.textContent : '▸';
                    toggleHeader.innerHTML = '<span class="toggle-arrow">' + arrowText + '</span> Item 목록 (' + items.length + '개)';
                }

                _cfRebuildTable();
            }
        } else {
            if (tableArea) tableArea.innerHTML = '<p>해당 리테일러의 데이터가 없습니다.</p>';
        }
    } catch (err) {
        console.error('reloadCfDays error:', err);
        if (tableArea) tableArea.innerHTML = '<p style="color:red;">데이터 로드 실패</p>';
    }
}

// ============================================================
// 크로스필드 셀 수정 / 정상 처리
// ============================================================

function _cfBindEditEvents() {
    var container = document.querySelector('#cf-detail-table-area') || document.querySelector('.inline-detail-body') || document.querySelector('.app-modal-body');
    if (!container) return;
    var tableEl = container.querySelector('table');
    if (!tableEl) return;

    // 중복 바인딩 방지
    if (tableEl._cfEditBound) return;
    tableEl._cfEditBound = true;

    // 클릭: 셀 선택 또는 정상처리/취소 바
    tableEl.addEventListener('click', function(e) {
        var td = e.target.closest('td[data-editable]');
        var normalTd = !td ? e.target.closest('td.cell-normal') : null;
        var reviewTd = (!td && !normalTd) ? e.target.closest('td[data-row-id]') : null;
        var prev = tableEl.querySelector('.cell-selected');
        if (prev) prev.classList.remove('cell-selected');
        _cfHideReviewBar();
        if (td) {
            td.classList.add('cell-selected');
            window._cfSelectedCell = td;
            _cfShowReviewBar(td, 'normal');
        } else if (normalTd) {
            window._cfSelectedCell = null;
            // cell-normal은 무시 (정상처리 완료된 셀)
        } else if (reviewTd) {
            reviewTd.classList.add('cell-selected');
            window._cfSelectedCell = null;
            _cfShowReviewBar(reviewTd, 'normal');
        } else {
            window._cfSelectedCell = null;
        }
    });

    // 테이블 외부 클릭 시 선택 해제
    document.addEventListener('click', function(e) {
        if (!e.target.closest('#cf-detail-table-area') && !e.target.closest('#cf-review-bar')) {
            var sel = tableEl.querySelector('.cell-selected');
            if (sel) sel.classList.remove('cell-selected');
            window._cfSelectedCell = null;
            _cfHideReviewBar();
        }
    });

    // Ctrl+V 붙여넣기
    document.addEventListener('paste', function(e) {
        var td = window._cfSelectedCell;
        if (!td || !td.dataset.editable || document.querySelector('.cell-edit-overlay')) return;
        e.preventDefault();
        var pastedText = (e.clipboardData || window.clipboardData).getData('text').trim();
        _cfApplyEdit(td, pastedText);
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
            _cfApplyEdit(td, newVal);
        }

        input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
            if (ev.key === 'Escape') { committed = true; input.remove(); }
        });
        input.addEventListener('blur', commit);
    });
}

function _cfApplyEdit(td, newVal) {
    var rowId = td.dataset.rowId;
    var colName = td.dataset.col;
    var oldText = td.textContent.trim();
    if (oldText === '-') oldText = '';
    if (newVal === oldText) return;
    _cfHideReviewBar();
    td.textContent = newVal || '-';
    td.classList.add('cell-pending');
    var editKey = rowId + '_' + colName;
    var pendingEdits = window.crossfieldPendingEdits || {};
    var prev = pendingEdits[editKey];
    pendingEdits[editKey] = {
        table_name: window.crossfieldTableName,
        row_id: parseInt(rowId),
        column_name: colName,
        new_value: newVal,
        _oldValue: prev ? prev._oldValue : oldText,
        crawl_date: window.crossfieldDate || '',
        td: td
    };
    window.crossfieldPendingEdits = pendingEdits;
    _cfUpdateSaveButton();
}

function _cfUpdateSaveButton() {
    var container = document.querySelector('#cf-detail-table-area') || document.querySelector('.inline-detail-body') || document.querySelector('.app-modal-body');
    if (!container) return;
    var wrap = document.getElementById('cf-edit-actions');
    var pendingEdits = window.crossfieldPendingEdits || {};
    var count = Object.keys(pendingEdits).length;
    if (count === 0) {
        if (wrap) wrap.remove();
        return;
    }
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.id = 'cf-edit-actions';
        wrap.className = 'detail-edit-actions';
        var infoSpan = document.createElement('span');
        infoSpan.id = 'cf-edit-info';
        infoSpan.className = 'edit-actions-info';
        var btnGroup = document.createElement('div');
        btnGroup.style.cssText = 'display:flex;gap:8px;';
        var btnCancel = document.createElement('button');
        btnCancel.className = 'btn-cancel-edits';
        btnCancel.textContent = '취소';
        btnCancel.addEventListener('click', _cfCancelAllEdits);
        var btnSave = document.createElement('button');
        btnSave.id = 'cf-btn-save';
        btnSave.className = 'btn-save-edits';
        btnSave.addEventListener('click', _cfSaveAllEdits);
        btnGroup.appendChild(btnCancel);
        btnGroup.appendChild(btnSave);
        wrap.appendChild(infoSpan);
        wrap.appendChild(btnGroup);
        var actionBar = document.getElementById('cf-detail-action-bar');
        if (actionBar) {
            actionBar.appendChild(wrap);
        } else {
            var tableEl = container.querySelector('table');
            if (tableEl) tableEl.parentNode.insertBefore(wrap, tableEl);
        }
    }
    document.getElementById('cf-edit-info').textContent = count + '건 변경됨';
    document.getElementById('cf-btn-save').textContent = '저장';
}

function _cfCancelAllEdits() {
    var edits = window.crossfieldPendingEdits || {};
    Object.keys(edits).forEach(function(k) {
        var edit = edits[k];
        if (edit.td) {
            edit.td.classList.remove('cell-pending');
            var origVal = edit._oldValue;
            edit.td.textContent = (origVal === null || origVal === undefined || origVal === '') ? '-' : origVal;
        }
    });
    window.crossfieldPendingEdits = {};
    _cfUpdateSaveButton();
}

function _cfSaveAllEdits() {
    var edits = window.crossfieldPendingEdits || {};
    var keys = Object.keys(edits);
    if (keys.length === 0) return;

    _cfShowMemoDialog(function(memo) {
        _cfDoSaveEdits(memo);
    });
}

function _cfDoSaveEdits(memo) {
    var edits = window.crossfieldPendingEdits || {};
    var keys = Object.keys(edits);
    if (keys.length === 0) return;

    var btn = document.getElementById('cf-btn-save');
    if (btn) { btn.disabled = true; btn.textContent = '저장 중...'; }

    var ruleId = (window._cfDetailState && window._cfDetailState._ruleId) || window.crossfieldRuleId || null;

    var requests = keys.map(function(k) {
        var edit = edits[k];
        return fetch('/dx/layer3/api/update-cell/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                table_name: edit.table_name,
                row_id: edit.row_id,
                column_name: edit.column_name,
                new_value: edit.new_value,
                crawl_date: edit.crawl_date,
                memo: memo || '',
                rule_id: ruleId
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
        _cfUpdateSaveButton();
    });
}

// 수정 저장용 메모 다이얼로그
function _cfShowMemoDialog(callback) {
    var overlay = document.createElement('div');
    overlay.className = 'memo-dialog-overlay';
    overlay.innerHTML = '<div class="memo-dialog">'
        + '<div class="memo-dialog-title">수정 메모</div>'
        + '<textarea class="memo-dialog-input" placeholder="수정 사유 입력 (선택사항)" rows="3"></textarea>'
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

// ==================== 정상 처리 ====================
function _cfShowReviewBar(td, mode) {
    _cfHideReviewBar();
    var bar = document.createElement('div');
    bar.id = 'cf-review-bar';
    bar.className = 'null-review-bar';
    var colName = td.dataset.col || '';
    var rowId = td.dataset.rowId || '';
    var infoText = colName + ' (ID: ' + rowId + ') — 이상치';
    var info = document.createElement('span');
    info.className = 'null-review-info';
    info.textContent = infoText;
    var btn = document.createElement('button');
    btn.className = 'btn-null-normal';
    btn.textContent = '정상 처리';
    btn.addEventListener('click', function() {
        _cfShowReviewDialog(function(reason, memo) {
            _cfSubmitReview(td, 'normal', memo, reason);
        });
    });
    bar.appendChild(info);
    bar.appendChild(btn);
    var actionBar = document.getElementById('cf-detail-action-bar');
    if (actionBar) {
        actionBar.appendChild(bar);
    } else {
        var container = document.querySelector('#cf-detail-table-area') || document.querySelector('.inline-detail-body');
        if (container) {
            var tableEl = container.querySelector('table');
            if (tableEl) tableEl.parentNode.insertBefore(bar, tableEl);
        }
    }
}

function _cfHideReviewBar() {
    var bar = document.getElementById('cf-review-bar');
    if (bar) bar.remove();
}

// 정상 처리 다이얼로그 (이유 선택 필수 + 메모 선택)
function _cfShowReviewDialog(callback) {
    var overlay = document.createElement('div');
    overlay.className = 'memo-dialog-overlay';
    overlay.innerHTML = '<div class="memo-dialog">'
        + '<div class="memo-dialog-title">정상 처리</div>'
        + '<div class="memo-dialog-field"><label class="memo-dialog-label">이유 <span style="color:#dc2626;">*</span></label>'
        + '<select class="memo-dialog-select" id="cf-review-reason-select"><option value="">불러오는 중...</option></select></div>'
        + '<div class="memo-dialog-field"><label class="memo-dialog-label">메모</label>'
        + '<textarea class="memo-dialog-input" placeholder="메모 입력 (선택사항)" rows="3"></textarea></div>'
        + '<div class="memo-dialog-buttons">'
        + '<button class="memo-dialog-cancel">취소</button>'
        + '<button class="memo-dialog-confirm">확인</button>'
        + '</div></div>';
    document.body.appendChild(overlay);
    setTimeout(function() { overlay.classList.add('show'); }, 10);

    // 이유 목록 조회
    fetch('/dx/layer3/api/review-reasons/?check_type=cross_field')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            var sel = document.getElementById('cf-review-reason-select');
            if (!sel) return;
            var reasons = res.reasons || [];
            if (reasons.length === 0) {
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
            var sel = document.getElementById('cf-review-reason-select');
            if (sel) sel.innerHTML = '<option value="">로딩 실패</option>';
        });

    var textarea = overlay.querySelector('.memo-dialog-input');
    function closeDlg() {
        overlay.classList.remove('show');
        setTimeout(function() { overlay.remove(); }, 200);
    }
    overlay.querySelector('.memo-dialog-cancel').addEventListener('click', closeDlg);
    overlay.querySelector('.memo-dialog-confirm').addEventListener('click', function() {
        var selEl = document.getElementById('cf-review-reason-select');
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

function _cfSubmitReview(td, status, memo, reason) {
    var rowId = td.dataset.rowId || (td.dataset.normalKey && td.dataset.normalKey.split('_')[0]);
    var colName = td.dataset.col || (td.dataset.normalKey && td.dataset.normalKey.split('_').slice(1).join('_'));
    if (!rowId || !colName) return;

    var retailerVal = window._cfCurrentRetailer || '';
    var ruleId = (window._cfDetailState && window._cfDetailState._ruleId) || window.crossfieldRuleId || null;

    fetch('/dx/layer3/api/review/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({
            table_name: window.crossfieldTableName,
            record_id: parseInt(rowId),
            column_name: colName,
            status: status,
            memo: memo || '',
            reason: reason || '',
            crawl_date: window.crossfieldDate || '',
            retailer: retailerVal,
            rule_id: ruleId
        })
    }).then(function(r) { return r.json(); })
    .then(function(res) {
        if (res.success) {
            _cfHideReviewBar();
            var nrKey = rowId + '_' + colName;
            if (!window.crossfieldNormalReviews) window.crossfieldNormalReviews = {};
            window.crossfieldNormalReviews[nrKey] = { memo: memo, reason: reason, created_id: '', created_at: '' };
            showToast('정상 처리 완료', 'success');
            // 테이블 재렌더링 (정상 처리 행 제외 + 건수 갱신)
            _cfSortAndRender();
        } else {
            showToast(res.error || '처리 실패', 'error');
        }
    }).catch(function() {
        showToast('네트워크 오류', 'error');
    });
}

// 규칙 요약 카드 건수 갱신 (정상 처리 반영, 리테일러 목록→규칙 요약으로 돌아갈 때)
function _cfUpdateRuleCardCount() {
    var ruleId = window.crossfieldRuleId;
    var retailerData = window.crossfieldRetailerData;
    var normalReviews = window.crossfieldNormalReviews || {};
    var editableCols = window.crossfieldEditableCols || new Set();
    if (!ruleId || !retailerData) return;

    // 현재 규칙의 실제 활성 건수 계산
    var activeCount = 0;
    Object.keys(retailerData).forEach(function(retailer) {
        retailerData[retailer].rows.forEach(function(row) {
            var rowId = row.id;
            if (!rowId) { activeCount++; return; }
            var hasNormal = false;
            editableCols.forEach(function(col) {
                if (normalReviews[rowId + '_' + col]) hasNormal = true;
            });
            if (!hasNormal) activeCount++;
        });
    });

    // 해당 규칙 카드의 건수 갱신
    var card = document.querySelector('.rule-summary-card[data-rule-id="' + ruleId + '"]');
    if (card) {
        var countEl = card.querySelector('.rule-count');
        if (countEl) {
            countEl.textContent = activeCount + '건';
            countEl.className = 'rule-count' + (activeCount === 0 ? ' zero' : '');
        }
    }

    // 전체 타이틀 건수 갱신 (모든 규칙 카드의 건수 합산)
    var totalActive = 0;
    document.querySelectorAll('.rule-summary-card[data-rule-id] .rule-count').forEach(function(el) {
        var num = parseInt(el.textContent) || 0;
        totalActive += num;
    });
    var headerEl = document.querySelector('.rule-summary-section-header span');
    if (headerEl) {
        headerEl.textContent = headerEl.textContent.replace(/\(\d+건\)/, '(' + totalActive + '건)');
    }
}

// 리테일러 카드 + 상위 타이틀 건수 갱신 (정상 처리 반영)
function _cfUpdateRetailerCounts() {
    var retailerData = window.crossfieldRetailerData;
    var normalReviews = window.crossfieldNormalReviews || {};
    var editableCols = window.crossfieldEditableCols || new Set();
    if (!retailerData || editableCols.size === 0) return;

    var totalActive = 0;
    Object.keys(retailerData).forEach(function(retailer) {
        var rows = retailerData[retailer].rows;
        var activeCount = rows.filter(function(row) {
            var rowId = row.id;
            if (!rowId) return true;
            var hasNormal = false;
            editableCols.forEach(function(col) {
                if (normalReviews[rowId + '_' + col]) hasNormal = true;
            });
            return !hasNormal;
        }).length;
        totalActive += activeCount;

        // 리테일러 카드 건수 갱신
        var card = document.querySelector('.rule-summary-card[data-retailer="' + retailer + '"]');
        if (card) {
            var countEl = card.querySelector('.rule-count');
            if (countEl) {
                countEl.textContent = activeCount + '건';
                countEl.className = 'rule-count' + (activeCount === 0 ? ' zero' : '');
            }
        }
    });

    // 상위 타이틀 건수 갱신
    var headerEl = document.querySelector('.rule-summary-section-header span');
    if (headerEl) {
        headerEl.textContent = headerEl.textContent.replace(/\(\d+건\)/, '(' + totalActive + '건)');
    }
}

// 리테일러 목록으로 돌아가기
function backToRetailerList() {
    if (isCrossFieldInline()) {
        ViewStack.pop();
        // pop 후 리테일러 카드 건수 갱신
        setTimeout(_cfUpdateRetailerCounts, 0);
        return;
    }
    if (window.crossfieldRetailerData && window.crossfieldCurrentTitle) {
        const retailerData = window.crossfieldRetailerData;

        let html = '';
        html += `<button class="btn-back" onclick="backToCrossfieldSummary()">← 뒤로가기</button>`;

        html += '<div class="retailer-list-container">';
        Object.keys(retailerData).sort().forEach(retailer => {
            const items = retailerData[retailer].items;
            const rowCount = retailerData[retailer].rows.length;
            html += `
                <div class="retailer-card" onclick="showRetailerDetail('${escJs(retailer)}')">
                    <div class="retailer-card-name">${esc(retailer)}</div>
                    <div class="retailer-card-count">${rowCount}건 (${items.length} items)</div>
                </div>
            `;
        });
        html += '</div>';

        AppModal.setTitle('detail', window.crossfieldCurrentTitle);
        AppModal.setBody('detail', html);
    }
}

// ESC 키로 모달 닫기
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        AppModal.close('detail');
    }
});

// 검증 규칙 모달 표시 (CSV 기반 API 호출)
async function showRulesModal(checkName) {
    AppModal.setTitle('detail', checkName + ' - 검증 규칙');
    AppModal.setBody('detail', '<p style="text-align:center;">로딩 중...</p>');
    AppModal.open('detail');

    // 크로스필드 규칙 체크 (Sentiment, 논리적 일관성)
    const crossfieldChecks = ['TV 논리적 일관성', 'HHP 논리적 일관성', 'TV Sentiment↔리뷰 일관성', 'HHP Sentiment↔리뷰 일관성'];
    const isCrossfield = crossfieldChecks.includes(checkName);

    // checkName에서 category 추출
    let category = 'all';
    let apiUrl = '';

    if (isCrossfield) {
        // 크로스필드 규칙
        if (checkName.includes('TV') && checkName.includes('Sentiment')) {
            category = 'tv_sentiment';
        } else if (checkName.includes('HHP') && checkName.includes('Sentiment')) {
            category = 'hhp_sentiment';
        } else if (checkName.includes('TV')) {
            category = 'tv_retail';
        } else if (checkName.includes('HHP')) {
            category = 'hhp_retail';
        }
        apiUrl = `/layer3/api/crossfield-rules/?section=${category}`;
    } else {
        // 카테고리별 특성 규칙 (display_name으로 매핑)
        // 먼저 category-rules API에서 모든 규칙을 가져와서 display_name으로 매칭
        apiUrl = `/layer3/api/category-rules/?display_name=${encodeURIComponent(checkName)}`;
    }

    // isCategorySpec 변수 (렌더링용)
    const isCategorySpec = !isCrossfield;

    try {
        const data = await fetchAPI(apiUrl);

        if (data.status === 'success' && data.rules.length > 0) {
            let html = '<ul class="rules-list">';
            data.rules.forEach((rule, idx) => {
                const retailerInfo = rule.retailer && rule.retailer !== 'all' ? ` (${rule.retailer})` : '';
                const thresholdInfo = rule.threshold ? ` [${rule.threshold}]` : '';

                if (isCategorySpec) {
                    // 카테고리별 특성 규칙 표시 - detail_name 사용
                    html += `
                        <li>
                            <div class="rule-number">${idx + 1}</div>
                            <div class="rule-content">
                                <div class="rule-title">${esc(rule.detail_name)}${esc(retailerInfo)}</div>
                                <div class="rule-desc">${esc(rule.error_message)}</div>
                                <div class="rule-example">${esc(rule.error_message)}${thresholdInfo ? ' / 범위: ' + esc(String(rule.threshold)) : ''}</div>
                            </div>
                        </li>
                    `;
                } else {
                    // 크로스필드 규칙 표시
                    html += `
                        <li>
                            <div class="rule-number">${idx + 1}</div>
                            <div class="rule-content">
                                <div class="rule-title">${esc(rule.field1)}${rule.field2 ? ' ↔ ' + esc(rule.field2) : ''}${esc(retailerInfo)}</div>
                                <div class="rule-desc">${esc(rule.error_message)}</div>
                            </div>
                        </li>
                    `;
                }
            });
            html += '</ul>';
            AppModal.setBody('detail', html);
        } else {
            // API 실패 시 기존 하드코딩 데이터 사용 (fallback)
            const rules = getValidationRules(checkName);
            let html = '<ul class="rules-list">';
            rules.forEach((rule, idx) => {
                html += `
                    <li>
                        <div class="rule-number">${idx + 1}</div>
                        <div class="rule-content">
                            <div class="rule-title">${esc(rule.title)}</div>
                            <div class="rule-desc">${esc(rule.description)}</div>
                            ${rule.example ? `<div class="rule-example">${esc(rule.example)}</div>` : ''}
                        </div>
                    </li>
                `;
            });
            html += '</ul>';
            AppModal.setBody('detail', html);
        }
    } catch (error) {
        console.error('Failed to fetch rules:', error);
        // 에러 시 기존 하드코딩 데이터 사용 (fallback)
        const rules = getValidationRules(checkName);
        let html = '<ul class="rules-list">';
        rules.forEach((rule, idx) => {
            html += `
                <li>
                    <div class="rule-number">${idx + 1}</div>
                    <div class="rule-content">
                        <div class="rule-title">${rule.title}</div>
                        <div class="rule-desc">${rule.description}</div>
                        ${rule.example ? `<div class="rule-example">${rule.example}</div>` : ''}
                    </div>
                </li>
            `;
        });
        html += '</ul>';
        AppModal.setBody('detail', html);
    }
}

function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// 필드 누락 탐지 토글
function toggleFieldMissing() {
    const content = document.getElementById('field-missing-content');
    const toggle = document.getElementById('field-missing-toggle');

    if (content.classList.contains('show')) {
        content.classList.remove('show');
        toggle.textContent = '▶';
    } else {
        content.classList.add('show');
        toggle.textContent = '▼';
    }
}

// 현재 선택된 제품군 (TV/HHP)
let currentFieldMissingPL = 'tv';

// 탭 전환
function switchFieldMissingTab(pl) {
    currentFieldMissingPL = pl;

    // 탭 버튼 스타일 변경
    document.querySelectorAll('.field-missing-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.pl === pl) {
            tab.classList.add('active');
        }
    });

    // 배지 ID 업데이트 및 리테일러 이름 업데이트
    const retailers = ['Amazon', 'Bestbuy', 'Walmart'];
    const plLabel = pl.toUpperCase();
    retailers.forEach(retailer => {
        const badgeEl = document.querySelector(`[data-retailer="${retailer}"] .retailer-badge`);
        if (badgeEl) badgeEl.id = `badge-${pl}-${retailer}`;

        // 리테일러 이름 업데이트 (TV_Amazon, HHP_Bestbuy 등)
        const nameEl = document.getElementById(`retailer-name-${retailer}`);
        if (nameEl) nameEl.textContent = `${plLabel}_${retailer}`;
    });

    // 데이터 로드
    loadAllRetailersMissing();
}

// 리테일러별 누락 데이터 캐시 (모달 표시용)
let retailerMissingCache = {};

// 모든 리테일러 데이터 로드
async function loadAllRetailersMissing() {
    const date = document.getElementById('target-date').value;
    const retailers = ['Amazon', 'Bestbuy', 'Walmart'];
    let totalMissing = 0;
    let totalFields = 0;

    for (const retailer of retailers) {
        try {
            const data = await fetchAPI(`/layer3/api/field-missing/?date=${date}&type=${currentFieldMissingPL}&retailer=${retailer}`);

            const missingCount = data.summary?.total_missing_cases || 0;
            const fieldsCount = data.summary?.fields_with_issues || 0;
            totalMissing += missingCount;
            totalFields += fieldsCount;

            // 배지 업데이트
            const badgeEl = document.getElementById(`badge-${currentFieldMissingPL}-${retailer}`);
            if (badgeEl) {
                if (missingCount === 0) {
                    badgeEl.className = 'retailer-badge ok';
                    badgeEl.textContent = '정상';
                } else if (missingCount < 10) {
                    badgeEl.className = 'retailer-badge warning';
                    badgeEl.textContent = `${missingCount}건`;
                } else {
                    badgeEl.className = 'retailer-badge critical';
                    badgeEl.textContent = `${missingCount}건`;
                }
            }

            // 누락 데이터 캐시 저장 (모달용)
            const cacheKey = `${currentFieldMissingPL}-${retailer}`;
            retailerMissingCache[cacheKey] = {
                missingFields: data.missing_fields || [],
                summary: data.summary || {},
                date: date,
                prevDates: data.prev_dates || []
            };
        } catch (error) {
            console.error(`Error loading ${retailer}:`, error);
            const badgeEl = document.getElementById(`badge-${currentFieldMissingPL}-${retailer}`);
            if (badgeEl) {
                badgeEl.className = 'retailer-badge';
                badgeEl.textContent = '-';
            }
        }
    }

    // 헤더 요약 업데이트 (대시보드에만 존재)
    const elTotal = document.getElementById('field-missing-total');
    const elFields = document.getElementById('field-missing-fields');
    if (elTotal) elTotal.textContent = totalMissing.toLocaleString();
    if (elFields) elFields.textContent = totalFields;

    const statusBadge = document.getElementById('field-missing-status');
    if (statusBadge) {
        if (totalMissing === 0) {
            statusBadge.className = 'status-badge ok';
            statusBadge.textContent = 'OK';
        } else if (totalMissing < 10) {
            statusBadge.className = 'status-badge warning';
            statusBadge.textContent = 'WARNING';
        } else {
            statusBadge.className = 'status-badge critical';
            statusBadge.textContent = 'CRITICAL';
        }
    }
}

// 누락분 요약 상태 관리
let missingSummaryState = {
    retailer: '',
    productLine: '',
    date: ''
};

// 누락분 요약 버튼 (인라인 또는 모달)
function viewMissingSummary(retailer, dateOverride = null) {
    missingSummaryState.retailer = retailer;
    missingSummaryState.productLine = currentFieldMissingPL;
    missingSummaryState.date = dateOverride || document.getElementById('target-date').value;

    // 누락필드 섹션이면 인라인
    if (window.LAYER3 && window.LAYER3.section === 'field_missing') {
        viewMissingSummaryInline(retailer, missingSummaryState.date);
        return;
    }

    AppModal.setTitle('detail', `${currentFieldMissingPL.toUpperCase()} - ${retailer} 필드별 누락 요약`);
    AppModal.open('detail');

    // 날짜가 변경된 경우 API 재호출
    if (dateOverride) {
        loadMissingSummaryData(retailer, dateOverride);
    } else {
        renderMissingSummaryFromCache(retailer);
    }
}

// 캐시에서 요약 렌더링
function renderMissingSummaryFromCache(retailer) {
    const cacheKey = `${currentFieldMissingPL}-${retailer}`;
    const cached = retailerMissingCache[cacheKey];

    if (!cached) {
        AppModal.setBody('detail', '<p style="text-align: center; padding: 40px;">데이터를 먼저 로드해주세요.</p>');
        return;
    }

    renderMissingSummary(cached.missingFields, cached.summary, cached.date, cached.prevDates, retailer);
}

// API로 요약 데이터 로드
async function loadMissingSummaryData(retailer, date) {
    AppModal.setBody('detail', '<p style="text-align: center; padding: 40px;">데이터를 불러오는 중...</p>');

    try {
        const data = await fetchAPI(`/layer3/api/field-missing/?date=${date}&type=${currentFieldMissingPL}&retailer=${retailer}`);

        const missingFields = data.missing_fields || [];
        const summary = data.summary || {};
        const prevDates = data.prev_dates || [];

        renderMissingSummary(missingFields, summary, date, prevDates, retailer);
    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p style="text-align: center; padding: 40px;">데이터 로드 실패</p>');
    }
}

// 요약 화면 렌더링
function renderMissingSummary(missingFields, summary, date, prevDates, retailer) {
    const periodStart = prevDates.length > 0 ? prevDates[0] : date;
    const periodEnd = date;

    if (missingFields.length === 0) {
        AppModal.setBody('detail', `
            <div style="padding: 40px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                <div style="font-size: 16px; font-weight: 600; color: #059669;">누락된 필드가 없습니다</div>
                <div style="font-size: 13px; margin-top: 8px; color: var(--text-secondary);">기간: ${periodStart} ~ ${periodEnd}</div>
            </div>`);
        return;
    }

    // 상단: 기간 조회 + 요약 정보
    let html = `<div style="margin-bottom: 16px; padding: 12px; background: var(--bg-primary); border-radius: 8px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <label style="font-weight: 500;">조회 날짜:</label>
            <input type="date" id="summary-date-input" value="${date}"
                style="padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 13px;">
            <button onclick="changeSummaryDate('${escJs(retailer)}')" style="padding: 4px 12px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">조회</button>
        </div>
        <span style="color: #6b7280;">|</span>
        <span><strong>기간:</strong> ${periodStart} ~ ${periodEnd}</span>
        <span><strong>총 누락:</strong> <span style="color: #dc2626;">${summary.total_missing_cases || 0}건</span></span>
        <span><strong>문제 필드:</strong> ${summary.fields_with_issues || 0}개</span>
    </div>`;

    // 테이블 (세로 스크롤)
    html += '<div style="max-height: calc(70vh - 180px); overflow-y: auto;">';
    html += '<table class="detail-table"><thead><tr>';
    html += '<th style="width: 40%; position: sticky; top: 0; background: #f8f9fa;">필드명</th>';
    html += '<th style="width: 20%; text-align: right; position: sticky; top: 0; background: #f8f9fa;">누락 item 수</th>';
    html += '<th style="width: 20%; text-align: right; position: sticky; top: 0; background: #f8f9fa;">누락 건수</th>';
    html += '<th style="width: 20%; text-align: right; position: sticky; top: 0; background: #f8f9fa;">비고</th>';
    html += '</tr></thead><tbody>';

    missingFields.forEach(f => {
        const itemCount = f.today_missing_items || 0;
        const rowCount = f.today_null_rows || 0;
        let statusClass = '';
        let statusText = '';

        if (itemCount >= 20) {
            statusClass = 'color: #dc2626; font-weight: 600;';
            statusText = '심각';
        } else if (itemCount >= 10) {
            statusClass = 'color: #f59e0b; font-weight: 600;';
            statusText = '주의';
        } else if (itemCount > 0) {
            statusClass = 'color: #6b7280;';
            statusText = '경미';
        }

        // 필드명 클릭 시 상세 보기
        html += `<tr style="cursor: pointer;" onclick="viewFieldMissingDetail('${escJs(retailer)}', '${escJs(f.column)}', '${escJs(date)}')">
            <td style="font-weight: 500; color: #2563eb;">${esc(f.column)}</td>
            <td style="text-align: right; ${statusClass}">${itemCount}개</td>
            <td style="text-align: right; ${statusClass}">${rowCount}건</td>
            <td style="text-align: right; ${statusClass}">${statusText}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    html += '</div>';
    html += '<p style="margin-top: 12px; font-size: 12px; color: #6b7280;">* 필드명을 클릭하면 해당 필드의 누락 item 3일치 데이터를 볼 수 있습니다.</p>';

    AppModal.setBody('detail', html);
}

// 요약 날짜 변경
function changeSummaryDate(retailer) {
    const newDate = document.getElementById('summary-date-input').value;
    if (!newDate) return;

    missingSummaryState.date = newDate;
    loadMissingSummaryData(retailer, newDate);
}

// --- 인라인 요약 뷰 ---
async function viewMissingSummaryInline(retailer, date) {
    var actualDate = date || document.getElementById('target-date').value;
    var cacheKey = currentFieldMissingPL + '-' + retailer;
    var cached = retailerMissingCache[cacheKey];

    // 캐시가 있고 같은 날짜면 캐시 사용
    if (cached && cached.date === actualDate) {
        _fmRenderSummaryInline(cached.missingFields, cached.summary, cached.date, cached.prevDates, retailer);
    } else {
        // 로딩 표시 후 API 호출
        var loadingHtml = '<div class="detail-view-wrapper" style="padding:40px;text-align:center;">데이터를 불러오는 중...</div>';
        ViewStack.push(loadingHtml, currentFieldMissingPL.toUpperCase() + ' - ' + retailer + ' 필드별 누락 요약');
        try {
            var data = await fetchAPI('/layer3/api/field-missing/?date=' + (date || document.getElementById('target-date').value) + '&type=' + currentFieldMissingPL + '&retailer=' + retailer);
            var missingFields = data.missing_fields || [];
            var summary = data.summary || {};
            var prevDates = data.prev_dates || [];
            var actualDate = date || document.getElementById('target-date').value;
            ViewStack.pop();
            _fmRenderSummaryInline(missingFields, summary, actualDate, prevDates, retailer);
        } catch (e) {
            console.error(e);
            ViewStack.pop();
            showToast('데이터 로드 실패', 'error');
        }
    }
}

function _fmRenderSummaryInline(missingFields, summary, date, prevDates, retailer) {
    var plUpper = currentFieldMissingPL.toUpperCase();
    var totalMissing = summary.total_missing_cases || 0;

    var titleText = plUpper + ' - ' + retailer + ' 필드별 누락 요약 (' + totalMissing + '건)';

    // 카드 목록
    var cardsHtml = '';
    if (missingFields.length === 0) {
        cardsHtml = '<div style="padding:40px;text-align:center;">'
            + '<div style="font-size:16px;font-weight:600;color:#059669;">누락된 필드가 없습니다</div></div>';
    } else {
        cardsHtml = '<div class="rule-summary-container">';
        missingFields.forEach(function(f) {
            var itemCount = f.today_missing_items || 0;
            var rowCount = f.today_null_rows || 0;
            var countClass = '';
            if (itemCount >= 20) countClass = ' critical';
            else if (itemCount >= 10) countClass = ' warning';

            cardsHtml += '<div class="rule-summary-card" onclick="showFieldMissingDetailInline(\'' + escJs(retailer) + '\',\'' + escJs(f.column) + '\')">'
                + '<div class="rule-info">'
                + '<div class="rule-name">' + esc(f.column) + '</div>'
                + '<div class="rule-desc">' + itemCount + ' items | ' + rowCount + '건</div>'
                + '</div>'
                + '<span class="rule-count' + (rowCount === 0 ? ' zero' : countClass) + '">' + rowCount + '건</span>'
                + '</div>';
        });
        cardsHtml += '</div>';
        cardsHtml += '<p style="margin-top:12px;font-size:12px;color:var(--text-secondary);">* 필드명을 클릭하면 해당 필드의 누락 item 데이터를 볼 수 있습니다.</p>';
    }

    var html = '<div class="inline-detail">'
        + '<button class="btn-back" onclick="ViewStack.pop()">&#8592; 뒤로가기</button>'
        + '<div class="rule-summary-section">'
        + '<div class="rule-summary-section-header">' + _inlineTitle(titleText) + '</div>'
        + cardsHtml
        + '</div></div>';

    ViewStack.push(html);
}

// 필드별 누락 상세 보기 (3일치 데이터)
async function viewFieldMissingDetail(retailer, field, date) {
    AppModal.setTitle('detail', `${currentFieldMissingPL.toUpperCase()} - ${retailer} - ${field} 누락 상세`);
    AppModal.setBody('detail', '<p style="text-align: center; padding: 40px;">데이터를 불러오는 중...</p>');

    try {
        const params = new URLSearchParams({
            date: date,
            product_line: currentFieldMissingPL,
            retailer: retailer,
            field: field
        });

        const data = await fetchAPI(`/layer3/api/field-missing-detail-by-field/?${params}`);

        if (data.status === 'success') {
            renderFieldMissingDetail(data, retailer, field);
        } else {
            AppModal.setBody('detail', `<p style="text-align: center; padding: 40px;">오류: ${esc(data.message || '데이터 로드 실패')}</p>`);
        }
    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p style="text-align: center; padding: 40px;">데이터 로드 실패</p>');
    }
}

// 필드별 누락 상세 렌더링
function renderFieldMissingDetail(data, retailer, field) {
    const items = data.data || [];
    const columns = data.columns || [];

    // 고유 item 목록 추출
    const uniqueItems = [...new Set(items.map(row => row.item).filter(Boolean))];

    // 누락 item 수와 누락 데이터 수 (API에서 반환)
    const missingItemCount = data.missing_item_count || uniqueItems.length;
    const todayNullCount = data.today_null_count || 0;

    // 상단: 뒤로가기 + 정보
    let html = `<div style="margin-bottom: 12px; padding: 12px; background: var(--bg-primary); border-radius: 8px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <button onclick="viewMissingSummary('${escJs(retailer)}', '${escJs(data.date)}')" style="padding: 6px 12px; background: #6b7280; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">← 뒤로가기</button>
        <span style="color: #6b7280;">|</span>
        <span><strong>필드:</strong> <span style="color: #dc2626;">${esc(field)}</span></span>
        <span><strong>기간:</strong> ${data.prev_dates?.[0] || ''} ~ ${data.date || ''}</span>
        <span><strong>누락 item 수:</strong> <span style="color: #dc2626;">${missingItemCount}개</span></span>
        <span><strong>누락 데이터 수:</strong> <span style="color: #dc2626;">${todayNullCount}건</span></span>
    </div>`;

    // 누락 item 목록 및 조회 쿼리 표시
    if (uniqueItems.length > 0) {
        const itemListDisplay = uniqueItems.join(', ');
        const inClause = uniqueItems.map(item => `'${item}'`).join(', ');
        const productLine = currentFieldMissingPL || 'tv';
        const tableName = productLine === 'hhp' ? 'hhp_retail_com' : 'tv_retail_com';
        const dateColumn = productLine === 'hhp' ? 'crawl_strdatetime' : 'crawl_datetime';
        const queryDate = data.date || '';

        // API에서 반환한 컬럼 목록 사용 (필수 + 현재필드 + 관련필드)
        const queryColumns = columns.join(', ');
        const query = `SELECT ${queryColumns}
FROM ${tableName}
WHERE account_name = '${retailer}'
  AND item IN (${inClause})
  AND DATE(${dateColumn}::timestamp) >= DATE('${queryDate}') - INTERVAL '2 days'
  AND DATE(${dateColumn}::timestamp) <= DATE('${queryDate}')
ORDER BY item, ${dateColumn} ASC;`;

        html += `
        <div class="query-section">
            <div class="item-list-box">
                <div class="query-box-header">
                    <span class="query-box-title">누락 Item 목록 (${uniqueItems.length}개)</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(this.parentElement.nextElementSibling)">복사</button>
                </div>
                <div class="item-list-content">${esc(itemListDisplay)}</div>
            </div>
            <div class="query-box">
                <div class="query-box-header">
                    <span class="query-box-title">3일치 조회 쿼리</span>
                    <button class="btn-copy" onclick="copyQueryToClipboard(this.parentElement.nextElementSibling)">복사</button>
                </div>
                <pre class="query-content">${esc(query)}</pre>
            </div>
        </div>`;
    }

    if (items.length === 0) {
        html += '<p style="text-align: center; padding: 40px; color: var(--text-secondary);">누락 데이터가 없습니다.</p>';
        AppModal.setBody('detail', html);
        return;
    }

    // 테이블 (세로 스크롤)
    html += `<div style="flex: 1; overflow-y: auto; overflow-x: auto;">`;
    html += '<table class="detail-table" style="width: 100%; font-size: 13px; border-collapse: collapse;">';

    // 헤더
    html += '<thead><tr>';
    columns.forEach(col => {
        let colLabel = col;
        if (col === 'crawl_datetime') colLabel = '수집시간';
        else if (col === 'product_url') colLabel = 'URL';
        else if (col === 'id') colLabel = 'ID';

        // 검사 대상 필드 강조
        let headerStyle = 'padding: 10px 12px; position: sticky; top: 0; background: #f8f9fa; border-bottom: 2px solid #e5e7eb; text-align: left;';
        if (col === field) {
            headerStyle += ' background: #fef2f2; color: #dc2626; font-weight: 700;';
        }
        html += `<th style="${headerStyle}">${colLabel}</th>`;
    });
    html += '</tr></thead>';

    // 바디 - item별로 배경색 번갈아 (흰색/회색), 대상일 NULL만 빨간 배경
    html += '<tbody>';

    let currentItem = '';
    let itemColorIndex = 0;
    const itemColors = ['#ffffff', '#f3f4f6']; // 흰색, 옅은 회색
    const targetDate = data.date || ''; // 조회 대상일 (예: 2026-01-26)

    items.forEach(row => {
        // item이 바뀌면 색상 인덱스 변경
        if (row.item !== currentItem) {
            currentItem = row.item;
            itemColorIndex = 1 - itemColorIndex; // 0 <-> 1 토글
        }
        const rowBgColor = itemColors[itemColorIndex];

        // 행의 날짜가 대상일인지 확인
        const rowDate = (row.crawl_datetime || row.crawl_strdatetime || '').substring(0, 10);
        const isTargetDate = rowDate === targetDate;

        html += `<tr style="background: ${rowBgColor};">`;
        columns.forEach(col => {
            let val = row[col];
            let style = 'padding: 8px 12px; border-bottom: 1px solid #e5e7eb;';

            // 검사 대상 필드 강조 (대상일 NULL일 때만 빨간 배경)
            if (col === field && (val === null || val === undefined || val === '') && isTargetDate) {
                style += ' background: #fee2e2;';
            }

            if (val === null || val === undefined || val === '') {
                if (isTargetDate) {
                    val = '<span style="color: #dc2626; font-weight: 600;">NULL</span>';
                } else {
                    val = 'NULL';
                }
            } else if (col === 'product_url') {
                const safe = safeUrl(String(val));
                val = safe ? `<a href="${esc(safe)}" target="_blank" style="color: #2563eb; text-decoration: none;">링크</a>` : esc(val);
            } else if (col === 'id') {
                style += ' color: #6b7280; font-size: 12px;';
            } else if (typeof val === 'string' && val.length > 80) {
                val = val.substring(0, 80) + '...';
            }

            if (col === 'item') {
                style += ' font-weight: 500;';
            }
            if (col === 'crawl_datetime') {
                style += ' font-size: 12px; color: #6b7280; white-space: nowrap;';
            }

            html += `<td style="${style}">${val}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table></div>';

    AppModal.setBody('detail', html);
}

// 누락분 보기 - 상태 관리
let missingItemsState = {
    retailer: '',
    productLine: '',
    date: '',
    offset: 0,
    limit: 100,
    hasMore: true,
    isLoading: false,
    totalCount: 0,
    loadedCount: 0,
    fields: []
};

// 누락분 보기 버튼
async function viewMissingItems(retailer) {
    const date = document.getElementById('target-date').value;

    // 상태 초기화
    missingItemsState = {
        retailer: retailer,
        productLine: currentFieldMissingPL,
        date: date,
        offset: 0,
        limit: 100,
        hasMore: true,
        isLoading: false,
        totalCount: 0,
        loadedCount: 0,
        fields: []
    };

    AppModal.setTitle('detail', `${currentFieldMissingPL.toUpperCase()} - ${retailer} 필드 누락 항목`);
    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    AppModal.open('detail');

    // 첫 데이터 로드
    await loadMissingItems(true);
}

// 누락분 데이터 로드 (무한스크롤용)
async function loadMissingItems(isInitial = false) {
    if (missingItemsState.isLoading || (!isInitial && !missingItemsState.hasMore)) return;

    missingItemsState.isLoading = true;

    try {
        const params = new URLSearchParams({
            date: missingItemsState.date,
            product_line: missingItemsState.productLine,
            retailer: missingItemsState.retailer,
            offset: missingItemsState.offset,
            limit: missingItemsState.limit
        });

        const data = await fetchAPI(`/layer3/api/field-missing-detail-problem/?${params}`);

        if (data.status === 'success') {
            if (isInitial) {
                missingItemsState.fields = data.fields;
                missingItemsState.totalCount = data.total_count || 0;
                renderMissingItemsModalInitial(data);
            } else {
                appendMissingItemsRows(data.data);
            }

            missingItemsState.offset += data.data.length;
            missingItemsState.loadedCount += data.data.length;
            missingItemsState.hasMore = data.has_more;

            // 로드 상태 업데이트
            updateMissingItemsLoadStatus();
        } else {
            if (isInitial) {
                AppModal.setBody('detail', `<p>오류: ${esc(data.message || '데이터 로드 실패')}</p>`);
            }
        }
    } catch (error) {
        console.error('Error:', error);
        if (isInitial) {
            AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
        }
    } finally {
        missingItemsState.isLoading = false;
    }
}

// 로드 상태 업데이트
function updateMissingItemsLoadStatus() {
    const statusEl = document.getElementById('missing-items-load-status');
    if (statusEl) {
        statusEl.innerHTML = `<strong>로드:</strong> ${missingItemsState.loadedCount} / ${missingItemsState.totalCount}건`;
        if (!missingItemsState.hasMore) {
            statusEl.innerHTML += ' (전체 로드 완료)';
        }
    }
}

// 누락분 모달 초기 렌더링
function renderMissingItemsModalInitial(data) {
    const items = data.data || [];

    if (items.length === 0 && missingItemsState.totalCount === 0) {
        AppModal.setBody('detail', `
            <div style="padding: 40px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                <div style="font-size: 16px; font-weight: 600; color: #059669;">누락된 필드가 없습니다</div>
                <div style="font-size: 13px; margin-top: 8px; color: var(--text-secondary);">직전 2일과 비교하여 오늘 누락된 항목이 없습니다.</div>
            </div>`);
        return;
    }

    let html = `<div style="margin-bottom: 16px; padding: 12px; background: var(--bg-primary); border-radius: 8px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <span><strong>검사 필드:</strong> ${data.fields?.length || 0}개</span>
        <span><strong>누락 항목:</strong> <span style="color: #dc2626;">${missingItemsState.totalCount}건</span></span>
        <span id="missing-items-load-status"><strong>로드:</strong> ${items.length} / ${missingItemsState.totalCount}건</span>
    </div>`;

    html += `<div id="missing-items-scroll-container" style="flex: 1; overflow-y: auto; max-height: calc(80vh - 150px);">`;
    html += '<table class="detail-table" id="missing-items-table"><thead><tr>';
    html += '<th>Item</th><th>Account</th><th>필드</th><th>직전 값</th><th>Today</th>';
    html += '</tr></thead><tbody id="missing-items-tbody">';

    items.forEach(row => {
        html += getMissingItemRow(row);
    });

    html += '</tbody></table></div>';

    // 로딩 인디케이터
    html += `<div id="missing-items-loading" style="display: none; text-align: center; padding: 12px; color: #6b7280;">
        <span>데이터 로딩 중...</span>
    </div>`;

    AppModal.setBody('detail', html);

    // 스크롤 이벤트 리스너
    const scrollContainer = document.getElementById('missing-items-scroll-container');
    scrollContainer.addEventListener('scroll', onMissingItemsScroll);
}

// 테이블 행 HTML 생성
function getMissingItemRow(row) {
    const todayStyle = row.today_has_value ? 'color: #059669;' : 'color: #dc2626; font-weight: 600;';
    const todayValue = row.today_has_value ? (row.today_value || '-') : '❌ 없음';

    return `<tr>
        <td>${esc(row.item || '-')}</td>
        <td>${esc(row.account_name || '-')}</td>
        <td style="font-weight: 500;">${esc(row.field_name || '-')}</td>
        <td>${esc(row.d1_value || '-')}</td>
        <td style="${todayStyle}">${esc(todayValue)}</td>
    </tr>`;
}

// 행 추가 (무한 스크롤)
function appendMissingItemsRows(items) {
    const tbody = document.getElementById('missing-items-tbody');
    if (!tbody) return;

    items.forEach(row => {
        tbody.insertAdjacentHTML('beforeend', getMissingItemRow(row));
    });
}

// 스크롤 이벤트 핸들러
function onMissingItemsScroll(e) {
    const container = e.target;
    const threshold = 200;

    if (container.scrollHeight - container.scrollTop - container.clientHeight < threshold) {
        if (!missingItemsState.isLoading && missingItemsState.hasMore) {
            const loadingEl = document.getElementById('missing-items-loading');
            if (loadingEl) loadingEl.style.display = 'block';

            loadMissingItems(false)
                .then(() => { if (loadingEl) loadingEl.style.display = 'none'; })
                .catch(() => { if (loadingEl) loadingEl.style.display = 'none'; });
        }
    }
}

// 3일치 보기 - 상태 관리
let threeDaysState = {
    retailer: '',
    productLine: '',
    date: '',
    columns: [],
    displayFields: [],
    offset: 0,
    limit: 100,
    hasMore: true,
    isLoading: false,
    totalCount: 0,
    loadedCount: 0
};

// 3일치 보기 버튼
async function view3DaysData(retailer) {
    const date = document.getElementById('target-date').value;

    // 상태 초기화
    threeDaysState = {
        retailer: retailer,
        productLine: currentFieldMissingPL,
        date: date,
        columns: [],
        displayFields: [],
        offset: 0,
        limit: 100,
        hasMore: true,
        isLoading: false,
        totalCount: 0,
        loadedCount: 0
    };

    AppModal.setTitle('detail', `${currentFieldMissingPL.toUpperCase()} - ${retailer} 3일치 데이터`);
    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    AppModal.open('detail');

    // 첫 데이터 로드
    await load3DaysData(true);
}

// 3일치 데이터 로드 (무한스크롤용)
async function load3DaysData(isInitial = false) {
    if (threeDaysState.isLoading || (!isInitial && !threeDaysState.hasMore)) return;

    threeDaysState.isLoading = true;

    try {
        const params = new URLSearchParams({
            date: threeDaysState.date,
            product_line: threeDaysState.productLine,
            retailer: threeDaysState.retailer,
            offset: threeDaysState.offset,
            limit: threeDaysState.limit
        });

        const data = await fetchAPI(`/layer3/api/field-missing-detail-all/?${params}`);

        if (data.status === 'success') {
            if (isInitial) {
                threeDaysState.columns = data.columns;
                threeDaysState.displayFields = data.display_fields;
                threeDaysState.totalCount = data.total_count || 0;
                render3DaysModalInitial(data);
            } else {
                append3DaysRows(data.data);
            }

            threeDaysState.offset += data.fetched_rows;
            threeDaysState.loadedCount += data.fetched_rows;
            threeDaysState.hasMore = data.has_more;

            // 로드 상태 업데이트
            updateLoadStatus();
        } else {
            if (isInitial) {
                AppModal.setBody('detail', `<p>오류: ${esc(data.message || '데이터 로드 실패')}</p>`);
            }
        }
    } catch (error) {
        console.error('Error:', error);
        if (isInitial) {
            AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
        }
    }

    threeDaysState.isLoading = false;
}

// 날짜 변경하여 재조회
async function change3DaysDate() {
    const newDate = document.getElementById('three-days-date-input').value;
    if (!newDate) return;

    threeDaysState.date = newDate;
    threeDaysState.offset = 0;
    threeDaysState.hasMore = true;
    threeDaysState.loadedCount = 0;

    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    await load3DaysData(true);
}

// 3일치 모달 초기 렌더링 (날짜 조회 + 무한스크롤)
function render3DaysModalInitial(data) {
    const items = data.data || [];
    const columns = data.columns || [];
    const displayFields = data.display_fields || [];

    if (items.length === 0 && threeDaysState.totalCount === 0) {
        AppModal.setBody('detail', '<p style="text-align: center; padding: 40px; color: var(--text-secondary);">데이터가 없습니다.</p>');
        return;
    }

    // 상단: 날짜 조회 + 정보
    let html = `<div style="margin-bottom: 12px; padding: 12px; background: var(--bg-primary); border-radius: 8px; flex-shrink: 0; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <label style="font-weight: 500;">조회 날짜:</label>
            <input type="date" id="three-days-date-input" value="${threeDaysState.date}"
                style="padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 13px;">
            <button onclick="change3DaysDate()" style="padding: 4px 12px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">조회</button>
        </div>
        <span style="color: #6b7280;">|</span>
        <span><strong>기간:</strong> ${data.prev_dates?.[0] || ''} ~ ${data.date || ''} (3일)</span>
        <span><strong>필드:</strong> ${displayFields.length}개</span>
        <span id="load-status"><strong>로드:</strong> ${items.length} / ${threeDaysState.totalCount}건</span>
    </div>`;

    // 테이블 컨테이너 (최대 높이 제한으로 세로 스크롤 활성화)
    html += `<div style="display: flex; flex-direction: column; flex: 1; min-height: 0; max-height: calc(80vh - 120px);">`;

    // 테이블 래퍼 (세로 + 가로 스크롤)
    html += `<div id="table-scroll-container" style="flex: 1; overflow-y: auto; overflow-x: auto; max-height: calc(80vh - 150px);">`;
    html += `<div id="table-inner" style="min-width: max-content;">`;
    html += '<table class="detail-table" id="three-days-table" style="min-width: max-content; font-size: 12px; border-collapse: collapse;">';

    // 헤더
    html += '<thead><tr>';
    columns.forEach(col => {
        let colLabel = col;
        if (col === 'crawl_datetime') colLabel = '수집시간';
        else if (col === 'product_url') colLabel = 'URL';
        html += `<th style="white-space: nowrap; padding: 8px 12px; position: sticky; top: 0; background: #f8f9fa; border-bottom: 2px solid #e5e7eb; z-index: 1;">${colLabel}</th>`;
    });
    html += '</tr></thead>';

    // 바디 - item별 배경색 구분
    html += '<tbody id="three-days-tbody">';
    let currentItem = '';
    let itemColorIndex = 0;
    const itemColors = ['#ffffff', '#f3f4f6'];
    items.forEach(row => {
        if (row.item !== currentItem) {
            currentItem = row.item;
            itemColorIndex = 1 - itemColorIndex;
        }
        html += buildRowHtml(row, columns, itemColors[itemColorIndex]);
    });
    // 마지막 item과 colorIndex 저장 (append용)
    threeDaysState.lastItem = currentItem;
    threeDaysState.lastColorIndex = itemColorIndex;
    html += '</tbody></table></div></div>';

    // 하단 고정 가로 스크롤바
    html += `<div id="horizontal-scroll" style="overflow-x: auto; overflow-y: hidden; flex-shrink: 0; border-top: 1px solid #e5e7eb; background: #fafafa;">
        <div id="scroll-spacer" style="height: 1px;"></div>
    </div>`;

    html += '</div>';

    AppModal.setBody('detail', html);

    // 스크롤 이벤트 및 동기화 설정
    setTimeout(() => {
        setupScrollSync();
        setupInfiniteScroll();
    }, 100);
}

// 행 HTML 생성 (배경색 포함)
function buildRowHtml(row, columns, bgColor = '#ffffff') {
    let html = `<tr style="background: ${bgColor};">`;
    columns.forEach(col => {
        let val = row[col];
        let style = 'white-space: nowrap; padding: 6px 10px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid #e5e7eb;';

        if (val === null || val === undefined || val === '') {
            val = '<span style="color: #dc2626;">-</span>';
        } else if (col === 'product_url') {
            val = `<a href="${safeUrl(String(val))}" target="_blank" style="color: #2563eb; text-decoration: none;">링크</a>`;
        } else if (col === 'id') {
            style += ' color: #6b7280; font-size: 11px;';
            val = esc(String(val));
        } else if (typeof val === 'string' && val.length > 50) {
            val = esc(val.substring(0, 50)) + '...';
        } else {
            val = esc(String(val));
        }

        if (col === 'item') {
            style += ' font-weight: 500;';
        }
        if (col === 'crawl_datetime') {
            style += ' font-size: 11px; color: #6b7280;';
        }

        html += `<td style="${style}">${val}</td>`;
    });
    html += '</tr>';
    return html;
}

// 추가 행 append (item별 배경색 유지)
function append3DaysRows(items) {
    const tbody = document.getElementById('three-days-tbody');
    if (!tbody) return;

    const itemColors = ['#ffffff', '#f3f4f6'];
    let currentItem = threeDaysState.lastItem || '';
    let colorIndex = threeDaysState.lastColorIndex || 0;

    items.forEach(row => {
        if (row.item !== currentItem) {
            currentItem = row.item;
            colorIndex = 1 - colorIndex;
        }
        tbody.insertAdjacentHTML('beforeend', buildRowHtml(row, threeDaysState.columns, itemColors[colorIndex]));
    });

    // 상태 업데이트
    threeDaysState.lastItem = currentItem;
    threeDaysState.lastColorIndex = colorIndex;

    // 스크롤바 너비 업데이트
    const tableInner = document.getElementById('table-inner');
    const scrollSpacer = document.getElementById('scroll-spacer');
    if (tableInner && scrollSpacer) {
        scrollSpacer.style.width = tableInner.scrollWidth + 'px';
    }
}

// 로드 상태 업데이트
function updateLoadStatus() {
    const statusEl = document.getElementById('load-status');
    if (statusEl) {
        let text = `<strong>로드:</strong> ${threeDaysState.loadedCount} / ${threeDaysState.totalCount}건`;
        if (!threeDaysState.hasMore) {
            text += ' (전체)';
        } else if (threeDaysState.isLoading) {
            text += ' <span style="color: #3b82f6;">(로딩중...)</span>';
        }
        statusEl.innerHTML = text;
    }
}

// 가로 스크롤 동기화 설정
function setupScrollSync() {
    const tableInner = document.getElementById('table-inner');
    const scrollSpacer = document.getElementById('scroll-spacer');
    const horizontalScroll = document.getElementById('horizontal-scroll');
    const tableContainer = document.getElementById('table-scroll-container');

    if (tableInner && scrollSpacer && horizontalScroll && tableContainer) {
        scrollSpacer.style.width = tableInner.scrollWidth + 'px';

        tableContainer.style.scrollbarWidth = 'none';
        tableContainer.style.msOverflowStyle = 'none';

        const existingStyle = document.getElementById('hide-horizontal-scrollbar');
        if (!existingStyle) {
            const style = document.createElement('style');
            style.id = 'hide-horizontal-scrollbar';
            style.textContent = '#table-scroll-container::-webkit-scrollbar { height: 0; width: 0; }';
            document.head.appendChild(style);
        }

        horizontalScroll.addEventListener('scroll', function() {
            tableContainer.scrollLeft = this.scrollLeft;
        });

        tableContainer.addEventListener('scroll', function() {
            horizontalScroll.scrollLeft = this.scrollLeft;
        });
    }
}

// 무한스크롤 설정
function setupInfiniteScroll() {
    const tableContainer = document.getElementById('table-scroll-container');
    if (!tableContainer) return;

    tableContainer.addEventListener('scroll', function() {
        const { scrollTop, scrollHeight, clientHeight } = this;

        // 하단 100px 남았을 때 추가 로드
        if (scrollHeight - scrollTop - clientHeight < 100) {
            load3DaysData(false);
        }
    });
}

// 페이지 로드 시 필드 누락 데이터 로드
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(loadAllRetailersMissing, 500);
});

// 리테일러별 필드 목록 (CSV 기반)
const retailerFields = {
    tv: {
        Amazon: ['product_url', 'screen_size', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'number_of_units_purchased_past_month', 'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity', 'retailer_membership_discounts', 'rank_1', 'rank_2', 'summarized_review_content', 'detailed_review_content', 'main_rank', 'bsr_rank'],
        Bestbuy: ['product_url', 'screen_size', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'detailed_review_content', 'main_rank', 'bsr_rank', 'savings', 'offer', 'pick_up_availability', 'shipping_availability', 'delivery_availability', 'estimated_annual_electricity_use', 'retailer_sku_name_similar', 'top_mentions', 'recommendation_intent', 'promotion_type'],
        Walmart: ['product_url', 'screen_size', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity', 'retailer_membership_discounts', 'detailed_review_content', 'main_rank', 'bsr_rank', 'savings', 'offer', 'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status', 'inventory_status', 'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts']
    },
    hhp: {
        Amazon: ['product_url', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'main_rank', 'bsr_rank', 'detailed_review_content', 'country', 'product', 'hhp_carrier', 'hhp_storage', 'hhp_color', 'number_of_units_purchased_past_month', 'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity', 'bundle', 'trade_in', 'retailer_membership_discounts', 'rank_1', 'rank_2', 'summarized_review_content'],
        Bestbuy: ['product_url', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'main_rank', 'bsr_rank', 'detailed_review_content', 'country', 'product', 'hhp_carrier', 'hhp_storage', 'hhp_color', 'trade_in', 'savings', 'offer', 'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status', 'promotion_type', 'retailer_sku_name_similar', 'top_mentions', 'recommendation_intent', 'trend_rank'],
        Walmart: ['product_url', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'final_sku_price', 'original_sku_price', 'main_rank', 'bsr_rank', 'detailed_review_content', 'hhp_carrier', 'hhp_storage', 'hhp_color', 'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity', 'retailer_membership_discounts', 'savings', 'offer', 'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status', 'retailer_sku_name_similar', 'inventory_status', 'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts']
    }
};

// 필드 목록 로드
function loadFieldList() {
    const productLine = currentFieldMissingPL || 'tv';
    const retailer = document.getElementById('field-missing-retailer').value;
    const fieldSelect = document.getElementById('field-missing-field');

    const fields = retailerFields[productLine]?.[retailer] || [];

    fieldSelect.innerHTML = '<option value="">-- 필드 선택 --</option>';
    fields.forEach(field => {
        fieldSelect.innerHTML += `<option value="${esc(field)}">${esc(field)}</option>`;
    });
}

// 리테일러 변경 시 필드 목록 업데이트
document.getElementById('field-missing-retailer')?.addEventListener('change', loadFieldList);

// 3일치 전체보기
async function showFieldMissing3Days() {
    const date = document.getElementById('target-date').value;
    const productLine = currentFieldMissingPL || 'tv';
    const retailer = document.getElementById('field-missing-retailer').value;
    const field = document.getElementById('field-missing-field').value;

    if (!field) {
        alert('필드를 선택하세요');
        return;
    }

    AppModal.setTitle('detail', `${field} - 3일치 전체 데이터 (${retailer})`);
    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    AppModal.open('detail');

    try {
        const data = await fetchAPI(`/layer3/api/field-missing-detail-all/?date=${date}&type=${productLine}&retailer=${retailer}&column=${field}`);
        renderFieldMissing3Days(data, field);
    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
    }
}

// 3일치 전체 데이터 렌더링
function renderFieldMissing3Days(data, fieldName) {
    const items = data.data || [];
    if (items.length === 0) {
        AppModal.setBody('detail', '<p>데이터가 없습니다.</p>');
        return;
    }

    let html = `<div style="margin-bottom: 12px; color: var(--text-secondary); font-size: 13px;">총 ${items.length}건 (최대 500건)</div>`;
    html += '<table class="detail-table"><thead><tr>';
    html += '<th>No.</th><th>Item</th><th>Page Type</th><th>수집일시</th><th>' + fieldName + '</th>';
    html += '</tr></thead><tbody>';

    items.forEach((row, idx) => {
        const value = row[fieldName];
        const isEmpty = value === null || value === '' || value === undefined;
        const valueStyle = isEmpty ? 'color: #c62828; font-weight: bold;' : '';
        const displayValue = isEmpty ? '(없음)' : (String(value).length > 50 ? String(value).substring(0, 50) + '...' : value);

        html += '<tr>';
        html += `<td>${idx + 1}</td>`;
        html += `<td>${row.item || '-'}</td>`;
        html += `<td>${row.page_type || '-'}</td>`;
        html += `<td>${row.crawl_datetime || '-'}</td>`;
        html += `<td style="${valueStyle}">${displayValue}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    AppModal.setBody('detail', html);
}

// 필드 누락 탐지 데이터 로드
async function loadFieldMissing() {
    const date = document.getElementById('target-date').value;
    const productLine = currentFieldMissingPL || 'tv';
    const retailer = document.getElementById('field-missing-retailer').value;

    document.getElementById('field-missing-list').innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-secondary);">데이터를 불러오는 중...</div>';

    try {
        const data = await fetchAPI(`/layer3/api/field-missing/?date=${date}&type=${productLine}&retailer=${retailer}`);
        renderFieldMissing(data);
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('field-missing-list').innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-secondary);">데이터 로드 실패</div>';
    }
}

// 필드 누락 탐지 결과 렌더링
function renderFieldMissing(data) {
    // Summary 업데이트
    const totalMissing = data.total_missing_cases || 0;
    const problemFields = data.problem_fields_count || 0;
    document.getElementById('field-missing-total').textContent = totalMissing.toLocaleString();
    document.getElementById('field-missing-fields').textContent = problemFields;

    // 상태 배지 업데이트
    const statusBadge = document.getElementById('field-missing-status');
    if (totalMissing === 0) {
        statusBadge.className = 'status-badge ok';
        statusBadge.textContent = 'OK';
    } else if (totalMissing < 10) {
        statusBadge.className = 'status-badge warning';
        statusBadge.textContent = 'WARNING';
    } else {
        statusBadge.className = 'status-badge critical';
        statusBadge.textContent = 'CRITICAL';
    }

    const missingFields = data.missing_fields || [];

    if (missingFields.length === 0) {
        document.getElementById('field-missing-list').innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-secondary);">필드 누락이 감지되지 않았습니다.</div>';
        return;
    }

    let html = '';
    missingFields.forEach((field, idx) => {
        html += `
            <div class="check-item" style="cursor: pointer;" onclick="showFieldMissingDetail('${escJs(field.retailer)}', '${escJs(field.field_name)}')">
                <div class="check-info">
                    <div class="check-name">
                        ${esc(field.field_name)}
                        <span class="threshold-badge">${esc(field.retailer)}</span>
                    </div>
                    <div class="check-description">직전 2일 값 있었으나 오늘 누락된 케이스</div>
                </div>
                <div class="check-stats">
                    <div class="check-stat">
                        <div class="value" style="color: var(--color-critical);">${field.missing_count || 0}</div>
                        <div class="label">누락 건수</div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-rules" onclick="event.stopPropagation(); showFieldMissingDetailAll('${escJs(field.retailer)}', '${escJs(field.field_name)}')">전체보기</button>
                        <button class="btn-rules" style="background: #fef3c7; color: #d97706;" onclick="event.stopPropagation(); showFieldMissingDetailProblem('${escJs(field.retailer)}', '${escJs(field.field_name)}')">문제만</button>
                    </div>
                </div>
            </div>
        `;
    });

    document.getElementById('field-missing-list').innerHTML = html;
}

// 필드 누락 상세 - 전체 데이터
async function showFieldMissingDetailAll(retailer, fieldName) {
    const date = document.getElementById('target-date').value;
    const productLine = currentFieldMissingPL || 'tv';

    AppModal.setTitle('detail', `${fieldName} - 전체 데이터 (${retailer})`);
    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    AppModal.open('detail');

    try {
        const data = await fetchAPI(`/layer3/api/field-missing-detail-all/?date=${date}&type=${productLine}&retailer=${retailer}&field=${fieldName}`);
        renderFieldMissingDetailAll(data, fieldName);
    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
    }
}

// 필드 누락 상세 - 문제 데이터만
async function showFieldMissingDetailProblem(retailer, fieldName) {
    const date = document.getElementById('target-date').value;
    const productLine = currentFieldMissingPL || 'tv';

    AppModal.setTitle('detail', `${fieldName} - 문제 데이터 (${retailer})`);
    AppModal.setBody('detail', '<p>데이터를 불러오는 중...</p>');
    AppModal.open('detail');

    try {
        const data = await fetchAPI(`/layer3/api/field-missing-detail-problem/?date=${date}&type=${productLine}&retailer=${retailer}&field=${fieldName}`);
        renderFieldMissingDetailProblem(data, fieldName);
    } catch (error) {
        console.error('Error:', error);
        AppModal.setBody('detail', '<p>데이터 로드 실패</p>');
    }
}

// 클릭시 기본 동작
function showFieldMissingDetail(retailer, fieldName) {
    if (window.LAYER3 && window.LAYER3.section === 'field_missing') {
        showFieldMissingDetailInline(retailer, fieldName);
    } else {
        showFieldMissingDetailProblem(retailer, fieldName);
    }
}

// 전체 데이터 모달 렌더링
function renderFieldMissingDetailAll(data, fieldName) {
    const items = data.items || [];
    if (items.length === 0) {
        AppModal.setBody('detail', '<p>데이터가 없습니다.</p>');
        return;
    }

    let html = '<table class="detail-table"><thead><tr>';
    html += '<th>No.</th><th>Item</th><th>Retailer</th><th>수집일시</th><th>' + fieldName + '</th>';
    html += '</tr></thead><tbody>';

    items.forEach((row, idx) => {
        const value = row.field_value;
        const isEmpty = value === null || value === '' || value === 'NULL';
        const valueStyle = isEmpty ? 'color: #c62828; font-weight: bold;' : '';
        const displayValue = isEmpty ? '(없음)' : value;

        html += '<tr>';
        html += `<td>${idx + 1}</td>`;
        html += `<td>${row.item || '-'}</td>`;
        html += `<td>${row.account_name || '-'}</td>`;
        html += `<td>${row.crawl_datetime || '-'}</td>`;
        html += `<td style="${valueStyle}">${displayValue}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    AppModal.setBody('detail', html);
}

// 문제 데이터 모달 렌더링
function renderFieldMissingDetailProblem(data, fieldName) {
    const items = data.items || [];
    if (items.length === 0) {
        AppModal.setBody('detail', '<p>문제 데이터가 없습니다.</p>');
        return;
    }

    let html = '<table class="detail-table"><thead><tr>';
    html += '<th>No.</th><th>Item</th><th>Retailer</th><th>직전 값</th><th>오늘 값</th>';
    html += '</tr></thead><tbody>';

    items.forEach((row, idx) => {
        html += '<tr>';
        html += `<td>${idx + 1}</td>`;
        html += `<td>${row.item || '-'}</td>`;
        html += `<td>${row.account_name || '-'}</td>`;
        html += `<td style="color: #2e7d32;">${row.prev_value || '-'}</td>`;
        html += `<td style="color: #c62828; font-weight: bold;">(없음)</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    AppModal.setBody('detail', html);
}

// 검증 규칙 데이터
function getValidationRules(checkName) {
    const rulesData = {
        'TV 논리적 일관성': [
            {
                title: 'star_rating ↔ count_of_star_ratings 일관성',
                description: 'star_rating(별점)이 존재하는데 count_of_star_ratings(리뷰 수)가 NULL 또는 0인 경우 오류로 판정합니다.',
                example: '오류: star_rating=4.5, count_of_star_ratings=NULL'
            },
            {
                title: 'page_type ↔ 순위 필드 일관성',
                description: 'page_type에 따라 해당 순위 필드가 존재해야 합니다. main→main_rank, bsr→bsr_rank, promotion→promotion_position',
                example: '오류: page_type=main, main_rank=NULL / page_type=bsr, bsr_rank=NULL'
            },
            {
                title: 'promotion_position ↔ promotion_type 일관성 (Bestbuy)',
                description: 'promotion_position이 있는데 promotion_type이 NULL인 경우 오류로 판정합니다. 프로모션 페이지에 노출된 상품은 promotion_type이 있어야 합니다.',
                example: '오류: promotion_position=1, promotion_type=NULL'
            },
            {
                title: 'final_sku_price ↔ original_sku_price 비교',
                description: '할인 가격이 원래 가격보다 높은 경우 오류입니다. 월 할부 가격($X/month)은 제외합니다.',
                example: '오류: final=$1,299, original=$999'
            },
            {
                title: '할인율 90% 이상 검증',
                description: '두 가격 필드 간 할인율이 90% 이상인 경우 비정상적인 가격 관계로 판정합니다.',
                example: '오류: final=$99, original=$999 (90% 할인)'
            },
            {
                title: 'count_of_reviews ↔ detailed_review_content 일관성',
                description: '리테일러별 형식으로 검증합니다. Amazon: "N-" 형식, Bestbuy: "|" 구분자 개수, Walmart: "reviewN" 형식',
                example: 'Amazon: 5- / Bestbuy: 구분자 19개=리뷰 20개 / Walmart: review5'
            }
        ],
        'HHP 논리적 일관성': [
            {
                title: 'star_rating ↔ count_of_star_ratings 일관성',
                description: 'star_rating(별점)이 존재하는데 count_of_star_ratings(리뷰 수)가 NULL 또는 0인 경우 오류로 판정합니다.',
                example: '오류: star_rating=4.5, count_of_star_ratings=NULL'
            },
            {
                title: 'page_type ↔ 순위 필드 일관성',
                description: 'page_type에 따라 해당 순위 필드가 존재해야 합니다. main→main_rank, bsr→bsr_rank, trend→trend_rank(Bestbuy)',
                example: '오류: page_type=main, main_rank=NULL / page_type=trend, trend_rank=NULL'
            },
            {
                title: 'promotion_position ↔ promotion_type 일관성 (Bestbuy)',
                description: 'promotion_position이 있는데 promotion_type이 NULL인 경우 오류로 판정합니다. 프로모션 페이지에 노출된 상품은 promotion_type이 있어야 합니다.',
                example: '오류: promotion_position=1, promotion_type=NULL'
            },
            {
                title: 'final_sku_price ↔ original_sku_price 비교',
                description: '할인 가격이 원래 가격보다 높은 경우 오류입니다. 월 할부 가격($X/month)은 제외합니다.',
                example: '오류: final=$1,299, original=$999'
            },
            {
                title: '할인율 90% 이상 검증',
                description: '두 가격 필드 간 할인율이 90% 이상인 경우 비정상적인 가격 관계로 판정합니다.',
                example: '오류: final=$99, original=$999 (90% 할인)'
            },
            {
                title: 'count_of_reviews ↔ detailed_review_content 일관성',
                description: 'HHP는 "reviewN" 형식으로 검증합니다. 리뷰 20개 이상이면 review20, 5개면 review5가 있어야 합니다.',
                example: '오류: count_of_reviews=5, review5=없음 / count_of_reviews=452, review20=없음'
            }
        ]
    };

    return rulesData[checkName] || [];
}

// =============================================
// 사이드바 — 하위 항목 클릭 (전 섹션 공통)
function onSubitemClick(parentSection, checkName) {
    const section = (window.LAYER3 && window.LAYER3.section) || 'dashboard';
    const date = document.getElementById('target-date') ? document.getElementById('target-date').value : '';
    const dateParam = date ? `?date=${date}` : '';

    // 해당 섹션 페이지가 아니면 이동
    if (section !== parentSection) {
        const sep = dateParam ? '&' : '?';
        window.location.href = `/dx/layer3/${parentSection.replace('_', '-')}/${dateParam}${sep}focus=${encodeURIComponent(checkName)}`;
        return;
    }

    // 필드 누락: 탭 전환
    if (parentSection === 'field_missing') {
        switchFieldMissingTab(checkName.toLowerCase());
        return;
    }

    // 인라인 상세보기 (시계열/크로스필드/카테고리별 특성 공통)
    const categoryName = SECTION_CATEGORY_MAP[parentSection];
    if (categoryName) {
        showDetail(categoryName, checkName);
        return;
    }
}

// ============================================================
// 누락필드 인라인 상세 뷰 + 셀 수정 / 정상 처리
// ============================================================

async function showFieldMissingDetailInline(retailer, fieldName) {
    var date = document.getElementById('target-date').value;
    var productLine = currentFieldMissingPL || 'tv';
    var days = 3;

    try {
        var data = await fetchAPI('/layer3/api/field-missing-detail-by-field/?date=' + date + '&product_line=' + productLine + '&retailer=' + encodeURIComponent(retailer) + '&field=' + encodeURIComponent(fieldName) + '&days=' + days);
        if (data.status !== 'success') {
            showToast(data.message || '데이터 로드 실패', 'error');
            return;
        }
        _fmRenderInlineView(data, retailer, fieldName, productLine, date, days);
    } catch (e) {
        console.error(e);
        showToast('데이터 로드 실패', 'error');
    }
}

function _fmRenderInlineView(data, retailer, fieldName, productLine, date, days) {
    var tableName = data.table_name || (productLine === 'tv' ? 'tv_retail_com' : 'hhp_retail_com');
    var dateCol = productLine === 'tv' ? 'crawl_datetime' : 'crawl_strdatetime';
    var editableCols = new Set(data.editable_columns || []);
    var normalReviews = data.normal_reviews || {};
    var columns = data.columns || [];
    var rawRows = data.data || [];
    var plDisplay = (productLine || 'tv').toUpperCase();
    var _wn = ['일','월','화','수','목','금','토'][new Date(date).getDay()];
    var dateDisplay = date + '(' + _wn + ')';

    // 컬럼 정의: API가 반환한 전체 컬럼
    var allColumns = [{ key: '_no', label: 'No', width: 50, fixed: true }];
    columns.forEach(function(col) {
        var w = 120;
        if (col === 'id') w = 80;
        else if (col === 'item') w = 140;
        else if (col === dateCol) w = 150;
        else if (col === 'product_url') w = 80;
        allColumns.push({ key: col, label: col, width: w });
    });

    // 기본 표시 컬럼 (default_columns 기반)
    var defaultCols = data.default_columns || columns;
    var defaultColSet = {};
    defaultCols.forEach(function(c) { defaultColSet[c] = true; });
    var defaultVisibleKeys = ['_no'];
    defaultCols.forEach(function(c) { defaultVisibleKeys.push(c); });

    // 데이터 변환
    var tableRows = rawRows.map(function(row, idx) {
        var r = { _no: idx + 1 };
        columns.forEach(function(col) {
            var val = row[col];
            if (col === 'product_url') {
                var url = safeUrl(val);
                r[col] = url ? '<a href="' + esc(url) + '" target="_blank" style="color:#1976d2;">링크</a>' : '-';
            } else {
                r[col] = val !== null && val !== undefined ? String(val) : '-';
            }
        });
        r._rowId = row.id;
        r._rowDate = (row[dateCol] || '').substring(0, 10);
        return r;
    });

    // Item 목록 토글
    var missingItems = [];
    var seen = {};
    rawRows.forEach(function(row) {
        var rd = (row[dateCol] || '').substring(0, 10);
        if (rd === date && !seen[row.item]) {
            var fv = row[fieldName];
            if (fv === null || fv === undefined || fv === '') {
                missingItems.push(row.item);
                seen[row.item] = true;
            }
        }
    });
    var retailerSafe = retailer.replace(/[^a-zA-Z0-9]/g, '');
    var itemListDisplay = missingItems.join(', ');
    var itemQueryHtml = '<div class="item-toggle-section">'
        + '<div class="item-toggle-header" onclick="var c=this.nextElementSibling;c.style.display=c.style.display===\'none\'?\'\':\'none\';this.querySelector(\'.toggle-arrow\').textContent=c.style.display===\'none\'?\'\\u25b8\':\'\\u25be\';">'
        + '<span class="toggle-arrow">▸</span> Item 목록 (' + missingItems.length + '개)'
        + '</div>'
        + '<div class="item-toggle-content" style="display:none;">'
        + '<div class="item-copy-header"><span class="item-copy-title">누락 Item (' + missingItems.length + '개)</span>'
        + '<button class="btn-copy" onclick="copyQueryToClipboard(document.getElementById(\'fm-item-list-' + retailerSafe + '\'))">복사</button></div>'
        + '<div id="fm-item-list-' + retailerSafe + '" class="item-copy-content">' + esc(itemListDisplay) + '</div>'
        + '</div></div>';

    // 컨테이너 HTML
    var containerHtml = '<div class="detail-view-wrapper">'
        + '<div id="fm-detail-item-query">' + itemQueryHtml + '</div>'
        + '<div id="fm-detail-filter-bar"></div>'
        + '<div id="fm-detail-action-bar"></div>'
        + '<div id="fm-detail-table-area"></div>'
        + '<div id="fm-detail-pagination"></div>'
        + '</div>';

    var daysInputHtml = '<div style="display:flex;align-items:center;gap:6px;margin-right:12px;">'
        + '<label style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">일수:</label>'
        + '<input type="number" id="fm-detail-days" value="' + days + '" min="1" max="30" style="width:50px;padding:3px 6px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;font-size:12px;text-align:center;" onkeydown="if(event.key===\'Enter\')reloadFmDays()">'
        + '<button onclick="reloadFmDays()" style="padding:3px 10px;font-size:12px;border:1px solid var(--border-color,#e2e8f0);border-radius:4px;background:var(--page-color,#0d9488);color:#fff;cursor:pointer;white-space:nowrap;">조회</button></div>';

    var titleText = fieldName + ' (' + (data.missing_item_count || 0) + '건)';
    var subtitleText = plDisplay + ' Retail | ' + retailer;
    var wrapper = '<div class="inline-detail-view">'
        + '<div class="inline-detail-header"><div>'
        + '<div class="inline-detail-title">' + esc(titleText) + '</div>'
        + '<div class="inline-detail-subtitle">' + esc(subtitleText) + '</div>'
        + '</div><div style="display:flex;align-items:center;">' + daysInputHtml + '<div class="inline-detail-date">' + dateDisplay + '</div></div></div>'
        + '<div id="fm-detail-body">' + containerHtml + '</div>'
        + '</div>';

    ViewStack.push('<div class="inline-detail"><button class="btn-back" onclick="ViewStack.pop()">← 뒤로가기</button>' + wrapper + '</div>');

    // 전역 상태 저장
    window._fmCurrentRetailer = retailer;
    window._fmCurrentField = fieldName;
    window._fmCurrentPL = productLine;
    window._fmDate = date;
    window._fmTableName = tableName;

    // FilterBar 옵션
    var filterCols = [];
    columns.forEach(function(col) {
        if (col !== 'product_url') filterCols.push({ value: col, label: col });
    });

    window._fmDetailState = {
        allData: tableRows,
        filteredData: null,
        allColumns: allColumns,
        visibleKeys: defaultVisibleKeys.slice(),
        editableCols: editableCols,
        normalReviews: normalReviews,
        sortState: [],
        table: null,
        filterBar: null,
        pager: null,
        fieldName: fieldName,
        dateCol: dateCol
    };

    window._fmDetailState.filterBar = new FilterBar('#fm-detail-filter-bar', {
        sticky: false,
        padding: '8px 12px',
        controls: [
            { type: 'select', key: 'fmFilterCol', label: '항목', width: 'auto', options: filterCols },
            { type: 'input', key: 'fmFilterVal', placeholder: '검색어 입력...', onEnter: function() { _fmApplyFilter(); } }
        ],
        onSearch: function() { _fmApplyFilter(); },
        onReset: function() { _fmClearFilter(); },
        columnSelector: {
            columns: allColumns.map(function(c) { return { key: c.key, label: c.label }; }),
            fixed: ['_no'],
            defaultVisible: defaultVisibleKeys,
            onUpdate: function(selected) {
                window._fmDetailState.visibleKeys = selected;
                _fmRebuildTable();
            }
        },
        right: [
            { type: 'button', label: '정렬 초기화', style: 'outline', size: 'fb', onClick: function() { window._fmDetailState.sortState = []; _fmRebuildTable(); } }
        ]
    }).render();

    _fmRebuildTable();
    setTimeout(function() { _fmBindEditEvents(); }, 100);
}

// N일치 재조회
window.reloadFmDays = function() {
    var daysEl = document.getElementById('fm-detail-days');
    var days = daysEl ? parseInt(daysEl.value, 10) : 1;
    if (isNaN(days) || days < 1) days = 1;
    if (days > 30) days = 30;

    var retailer = window._fmCurrentRetailer;
    var fieldName = window._fmCurrentField;
    var productLine = window._fmCurrentPL;
    var date = window._fmDate;

    fetchAPI('/layer3/api/field-missing-detail-by-field/?date=' + date + '&product_line=' + productLine + '&retailer=' + encodeURIComponent(retailer) + '&field=' + encodeURIComponent(fieldName) + '&days=' + days)
        .then(function(data) {
            if (data.status !== 'success') { showToast(data.message || '재조회 실패', 'error'); return; }
            var st = window._fmDetailState;
            var dateCol = st.dateCol;
            var columns = data.columns || [];
            var rawRows = data.data || [];
            var targetDate = window._fmDate;

            var tableRows = rawRows.map(function(row, idx) {
                var r = { _no: idx + 1 };
                columns.forEach(function(col) {
                    var val = row[col];
                    if (col === 'product_url') {
                        var url = safeUrl(val);
                        r[col] = url ? '<a href="' + esc(url) + '" target="_blank" style="color:#1976d2;">링크</a>' : '-';
                    } else {
                        r[col] = val !== null && val !== undefined ? String(val) : '-';
                    }
                });
                r._rowId = row.id;
                r._rowDate = (row[dateCol] || '').substring(0, 10);
                return r;
            });

            st.allData = tableRows;
            st.filteredData = null;
            st.editableCols = new Set(data.editable_columns || []);
            st.normalReviews = data.normal_reviews || {};
            _fmRebuildTable();
            setTimeout(function() { _fmBindEditEvents(); }, 100);
        })
        .catch(function(e) { console.error(e); showToast('재조회 실패', 'error'); });
};

// CommonTable 재구성
function _fmRebuildTable() {
    var st = window._fmDetailState;
    if (!st) return;

    var visibleCols = st.allColumns.filter(function(c) { return st.visibleKeys.indexOf(c.key) >= 0; });
    st._visibleCols = visibleCols;

    var ctColumns = visibleCols.map(function(c) {
        return { key: c.key, label: c.label, width: c.width, sortable: c.key !== '_no', align: c.key === '_no' ? 'center' : undefined };
    });

    var el = document.getElementById('fm-detail-table-area');
    if (!el) return;
    el.innerHTML = '';

    st.table = new CommonTable('#fm-detail-table-area', {
        variant: 'detail', columns: ctColumns, vlines: true, section: true, showTotalCount: true,
        padding: '6px 12px', reorder: true, fixedColumns: ['_no'], multiSort: true,
        onSort: function(sortArr) { st.sortState = sortArr; _fmSortAndRender(); }
    }).render();

    var pageSize = 15;
    st.pager = new Pagination('#fm-detail-pagination', {
        pageSize: pageSize, showInfo: true,
        onPageChange: function(page) { _fmRenderPage(page); }
    });

    _fmSortAndRender();
}

function _fmSortAndRender() {
    var st = window._fmDetailState;
    if (!st) return;
    var dataArr = st.filteredData || st.allData;

    if (st.sortState && st.sortState.length > 0) {
        dataArr = dataArr.slice().sort(function(a, b) {
            for (var i = 0; i < st.sortState.length; i++) {
                var s = st.sortState[i];
                var va = a[s.key] || '', vb = b[s.key] || '';
                var cmp = String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: 'base' });
                if (cmp !== 0) return s.dir === 'asc' ? cmp : -cmp;
            }
            return 0;
        });
    }
    st._sortedData = dataArr;
    _fmRenderPage(1);
}

function _fmRenderPage(page) {
    var st = window._fmDetailState;
    if (!st || !st.table) return;

    var dataArr = st._sortedData || st.allData;
    var pageSize = 15;
    var start = (page - 1) * pageSize;
    var pageData = dataArr.slice(start, start + pageSize);
    pageData.forEach(function(r, i) { r._no = start + i + 1; });

    var visibleCols = st._visibleCols || st.allColumns;
    var targetDate = window._fmDate || '';
    var targetField = st.fieldName || '';

    // item 컬럼 rowspan 계산
    var itemSpanMap = {};  // index -> rowspan count
    var itemSkipSet = {};  // index -> true (skip item td)
    var hasItemCol = visibleCols.some(function(c) { return c.key === 'item'; });
    if (hasItemCol) {
        var i = 0;
        while (i < pageData.length) {
            var curItem = pageData[i].item;
            var spanCount = 1;
            while (i + spanCount < pageData.length && pageData[i + spanCount].item === curItem) {
                itemSkipSet[i + spanCount] = true;
                spanCount++;
            }
            if (spanCount > 1) itemSpanMap[i] = spanCount;
            i += spanCount;
        }
    }

    st.table.renderBody(pageData, function(row, rowIdx) {
        var tr = '<tr>';
        var rowId = row._rowId;
        var isTargetDate = row._rowDate === targetDate;
        visibleCols.forEach(function(c) {
            // item 컬럼 rowspan 처리
            if (c.key === 'item') {
                if (itemSkipSet[rowIdx]) return; // 이미 rowspan으로 병합됨
                var span = itemSpanMap[rowIdx];
                var spanAttr = span ? ' rowspan="' + span + '"' : '';
                var val = row[c.key];
                var displayVal = val !== null && val !== undefined ? String(val) : '-';
                tr += '<td' + spanAttr + ' style="vertical-align:middle;">' + esc(displayVal) + '</td>';
                return;
            }

            var val = row[c.key];
            var displayVal = val !== null && val !== undefined ? String(val) : '-';

            if (c.key === '_no') {
                tr += '<td style="text-align:center;">' + displayVal + '</td>';
                return;
            }
            if (c.key === 'product_url') {
                tr += '<td>' + displayVal + '</td>';
                return;
            }

            var nrKey = rowId + '_' + c.key;
            if (isTargetDate && st.normalReviews[nrKey]) {
                var nr = st.normalReviews[nrKey];
                var tip = '정상 처리됨';
                if (nr.reason) tip += ' | 사유: ' + nr.reason;
                if (nr.memo) tip += ' | 메모: ' + nr.memo;
                tr += '<td class="cell-normal" data-row-id="' + rowId + '" data-col="' + esc(c.key) + '" data-normal-key="' + nrKey + '" title="' + esc(tip) + '">' + esc(displayVal) + '<span class="normal-badge">정상</span></td>';
            } else if (isTargetDate && st.editableCols.has(c.key) && rowId) {
                // 누락필드 특유: 타겟 날짜 NULL 셀 빨간 배경
                var isNull = displayVal === '-' || displayVal === '';
                var cellStyle = (isNull && c.key === targetField) ? ' style="background:#fee2e2;"' : '';
                tr += '<td data-editable="true" data-row-id="' + rowId + '" data-col="' + esc(c.key) + '"' + cellStyle + '>' + esc(displayVal) + '</td>';
            } else if (isTargetDate && rowId) {
                var isNull2 = displayVal === '-' || displayVal === '';
                var cellStyle2 = (isNull2 && c.key === targetField) ? ' style="background:#fee2e2;"' : '';
                tr += '<td data-row-id="' + rowId + '" data-col="' + esc(c.key) + '"' + cellStyle2 + '>' + esc(displayVal) + '</td>';
            } else {
                tr += '<td>' + esc(displayVal) + '</td>';
            }
        });
        tr += '</tr>';
        return tr;
    });

    if (st.pager) st.pager.render(dataArr.length, page);
    var countEl = document.querySelector('#fm-detail-table-area .ct-count');
    if (countEl) {
        var suffix = st.filteredData ? ' (필터 적용)' : '';
        countEl.innerHTML = '총 <strong>' + dataArr.length.toLocaleString() + '</strong>건' + suffix;
    }
}

// 필터
function _fmApplyFilter() {
    var st = window._fmDetailState;
    if (!st) return;
    var colEl = document.getElementById('fmFilterCol');
    var valEl = document.getElementById('fmFilterVal');
    if (!colEl || !valEl) return;
    var col = colEl.value, keyword = (valEl.value || '').trim().toLowerCase();
    if (!keyword) { _fmClearFilter(); return; }
    st.filteredData = st.allData.filter(function(r) { return String(r[col] || '').toLowerCase().indexOf(keyword) >= 0; });
    _fmSortAndRender();
}
function _fmClearFilter() {
    var st = window._fmDetailState;
    if (!st) return;
    st.filteredData = null;
    var valEl = document.getElementById('fmFilterVal');
    if (valEl) valEl.value = '';
    _fmSortAndRender();
}

// ============================================================
// 누락필드 셀 수정 / 정상 처리
// ============================================================
var fmPendingEdits = {};

function _fmBindEditEvents() {
    var container = document.getElementById('fm-detail-table-area');
    if (!container) return;
    var tableEl = container.querySelector('table');
    if (!tableEl) return;
    if (tableEl._fmEditBound) return;
    tableEl._fmEditBound = true;

    // 클릭: 셀 선택 / 정상처리 바
    tableEl.addEventListener('click', function(e) {
        var td = e.target.closest('td[data-editable]');
        var normalTd = !td ? e.target.closest('td.cell-normal') : null;
        var reviewTd = (!td && !normalTd) ? e.target.closest('td[data-row-id]') : null;
        var prev = tableEl.querySelector('.cell-selected');
        if (prev) prev.classList.remove('cell-selected');
        _fmHideReviewBar();
        // 현재 보고 있는 필드와 다른 컬럼은 정상처리 불가
        var targetTd = td || reviewTd;
        var colMatch = true;
        if (targetTd && window._fmCurrentField) {
            var clickedCol = targetTd.getAttribute('data-col');
            if (clickedCol && clickedCol !== window._fmCurrentField) colMatch = false;
        }
        if (td) {
            td.classList.add('cell-selected');
            window._fmSelectedCell = td;
            if (colMatch) _fmShowReviewBar(td, 'normal');
        } else if (normalTd) {
            window._fmSelectedCell = null;
            // cell-normal은 무시 (정상처리 완료된 셀)
        } else if (reviewTd) {
            reviewTd.classList.add('cell-selected');
            window._fmSelectedCell = null;
            if (colMatch) _fmShowReviewBar(reviewTd, 'normal');
        } else {
            window._fmSelectedCell = null;
        }
    });

    // 테이블 외부 클릭
    document.addEventListener('click', function(e) {
        if (!e.target.closest('#fm-detail-table-area') && !e.target.closest('#fm-review-bar')) {
            var sel = tableEl.querySelector('.cell-selected');
            if (sel) sel.classList.remove('cell-selected');
            window._fmSelectedCell = null;
            _fmHideReviewBar();
        }
    });

    // 더블클릭: 직접 입력
    tableEl.addEventListener('dblclick', function(e) {
        var td = e.target.closest('td[data-editable]');
        if (!td) return;
        if (td.querySelector('.cell-edit-overlay')) return;
        var currentVal = td.textContent.trim();
        if (currentVal === '-') currentVal = '';
        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'cell-edit-overlay';
        input.value = currentVal;
        input.style.width = td.offsetWidth + 'px';
        input.style.height = td.offsetHeight + 'px';
        input.style.position = 'absolute';
        input.style.left = td.offsetLeft + 'px';
        input.style.top = td.offsetTop + 'px';
        input.style.zIndex = '100';
        td.style.position = 'relative';
        td.appendChild(input);
        input.focus();
        input.select();
        input.addEventListener('blur', function() { _fmApplyEdit(td, input.value); input.remove(); });
        input.addEventListener('keydown', function(ev) { if (ev.key === 'Enter') { _fmApplyEdit(td, input.value); input.remove(); } else if (ev.key === 'Escape') { input.remove(); } });
    });

    // Ctrl+V 붙여넣기
    tableEl.addEventListener('paste', function(e) {
        var td = e.target.closest('td[data-editable]');
        if (!td) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text').trim();
        _fmApplyEdit(td, text);
    });
}

function _fmApplyEdit(td, newVal) {
    var rowId = td.getAttribute('data-row-id');
    var col = td.getAttribute('data-col');
    if (!rowId || !col) return;
    var key = rowId + '_' + col;
    var original = fmPendingEdits[key] ? fmPendingEdits[key].original : td.textContent.trim();
    if (original === '-') original = '';
    // 값이 변경되지 않았으면 무시
    if (newVal.trim() === original) {
        delete fmPendingEdits[key];
        td.classList.remove('cell-pending');
        _fmUpdateSaveButton();
        return;
    }
    if (!fmPendingEdits[key]) {
        fmPendingEdits[key] = { rowId: rowId, col: col, original: original };
    }
    fmPendingEdits[key].newVal = newVal;
    td.textContent = newVal || '-';
    td.classList.add('cell-pending');
    _fmUpdateSaveButton();
}

function _fmUpdateSaveButton() {
    var bar = document.getElementById('fm-detail-action-bar');
    if (!bar) return;
    var count = Object.keys(fmPendingEdits).length;
    if (count === 0) { bar.innerHTML = ''; return; }
    bar.innerHTML = '<div class="detail-edit-actions">'
        + '<span class="edit-actions-info">' + count + '건 변경됨</span>'
        + '<div style="display:flex;gap:8px;">'
        + '<button class="btn-cancel-edits" onclick="_fmCancelAllEdits()">취소</button>'
        + '<button class="btn-save-edits" onclick="_fmSaveAllEdits()">저장</button>'
        + '</div></div>';
}

window._fmCancelAllEdits = function() {
    Object.keys(fmPendingEdits).forEach(function(key) {
        var edit = fmPendingEdits[key];
        var tds = document.querySelectorAll('td[data-row-id="' + edit.rowId + '"][data-col="' + edit.col + '"]');
        tds.forEach(function(td) { td.textContent = edit.original; td.classList.remove('cell-pending'); });
    });
    fmPendingEdits = {};
    _fmUpdateSaveButton();
};

window._fmSaveAllEdits = function() {
    var edits = Object.values(fmPendingEdits);
    if (edits.length === 0) return;
    _fmShowMemoDialog(function(memo) {
        var promises = edits.map(function(edit) {
            return fetch('/dx/layer3/api/update-cell/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({
                    table_name: window._fmTableName,
                    row_id: parseInt(edit.rowId),
                    column_name: edit.col,
                    new_value: edit.newVal,
                    crawl_date: window._fmDate,
                    memo: memo,
                    correction_type: 'field_missing'
                })
            }).then(function(r) { return r.json(); });
        });
        Promise.all(promises).then(function(results) {
            console.log('fm save results:', results);
            var failedResults = results.filter(function(r) { return !r.success; });
            if (failedResults.length > 0) console.warn('fm save failures:', failedResults);
            var successCount = results.filter(function(r) { return r.success; }).length;
            showToast(successCount + '건 저장 완료', 'success');
            document.querySelectorAll('td.cell-pending').forEach(function(td) { td.classList.remove('cell-pending'); td.classList.add('cell-saved'); });
            fmPendingEdits = {};
            _fmUpdateSaveButton();
            setTimeout(function() { document.querySelectorAll('td.cell-saved').forEach(function(td) { td.classList.remove('cell-saved'); }); }, 2000);
        }).catch(function(e) { console.error(e); showToast('저장 실패', 'error'); });
    });
};

function _fmShowMemoDialog(callback) {
    var overlay = document.createElement('div');
    overlay.className = 'memo-dialog-overlay';
    overlay.innerHTML = '<div class="memo-dialog">'
        + '<div class="memo-dialog-title">수정 메모</div>'
        + '<div class="memo-dialog-field"><textarea class="memo-dialog-input" id="fm-memo-input" rows="3" placeholder="수정 사유를 입력하세요 (선택)"></textarea></div>'
        + '<div class="memo-dialog-buttons">'
        + '<button class="memo-dialog-cancel" id="fm-memo-cancel">취소</button>'
        + '<button class="memo-dialog-confirm" id="fm-memo-confirm">저장</button>'
        + '</div></div>';
    document.body.appendChild(overlay);
    requestAnimationFrame(function() { overlay.classList.add('show'); });
    document.getElementById('fm-memo-cancel').onclick = function() { overlay.remove(); };
    document.getElementById('fm-memo-confirm').onclick = function() {
        var memo = document.getElementById('fm-memo-input').value.trim();
        overlay.remove();
        callback(memo);
    };
}

// 정상처리 바
function _fmShowReviewBar(td, mode) {
    _fmHideReviewBar();
    var bar = document.getElementById('fm-detail-action-bar');
    if (!bar) return;
    if (Object.keys(fmPendingEdits).length > 0) return;
    var rowId = td.getAttribute('data-row-id');
    var col = td.getAttribute('data-col');
    if (!rowId) return;

    var html = '<div class="null-review-bar" id="fm-review-bar">'
        + '<span class="null-review-info">' + esc(col) + ' (ID: ' + rowId + ')</span>'
        + '<button class="btn-null-normal" onclick="_fmShowReviewDialog(\'' + rowId + '\',\'' + esc(col) + '\')">정상 처리</button>'
        + '</div>';
    bar.innerHTML = html;
}

function _fmHideReviewBar() {
    var bar = document.getElementById('fm-review-bar');
    if (bar) bar.remove();
}

window._fmShowReviewDialog = function(rowId, col) {
    fetch('/dx/layer3/api/review-reasons/?check_type=field_missing')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var reasons = (data.reasons || []).map(function(r) { return typeof r === 'object' ? r.text : r; });
            var overlay = document.createElement('div');
            overlay.className = 'memo-dialog-overlay';
            var reasonOpts = '<option value="">선택하세요</option>';
            reasons.forEach(function(r) { reasonOpts += '<option value="' + esc(r) + '">' + esc(r) + '</option>'; });
            overlay.innerHTML = '<div class="memo-dialog">'
                + '<div class="memo-dialog-title">정상 처리</div>'
                + '<div class="memo-dialog-field"><label class="memo-dialog-label">이유 (필수)</label><select class="memo-dialog-select" id="fm-review-reason">' + reasonOpts + '</select></div>'
                + '<div class="memo-dialog-field"><label class="memo-dialog-label">메모 (선택)</label><textarea class="memo-dialog-input" id="fm-review-memo" rows="2"></textarea></div>'
                + '<div class="memo-dialog-buttons">'
                + '<button class="memo-dialog-cancel" id="fm-rev-cancel">취소</button>'
                + '<button class="memo-dialog-confirm" id="fm-rev-confirm">확인</button>'
                + '</div></div>';
            document.body.appendChild(overlay);
            requestAnimationFrame(function() { overlay.classList.add('show'); });
            document.getElementById('fm-rev-cancel').onclick = function() { overlay.remove(); };
            document.getElementById('fm-rev-confirm').onclick = function() {
                var reason = document.getElementById('fm-review-reason').value;
                var memo = document.getElementById('fm-review-memo').value.trim();
                if (!reason) { showToast('이유를 선택해주세요', 'warning'); return; }
                overlay.remove();
                _fmSubmitReview(rowId, col, 'normal', reason, memo, '');
            };
        });
};

window._fmSubmitReview = function(rowId, col, status, reason, memo, normalKey) {
    fetch('/dx/layer3/api/review/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({
            table_name: window._fmTableName,
            record_id: parseInt(rowId),
            column_name: col,
            status: status,
            reason: reason || '',
            memo: memo || '',
            crawl_date: window._fmDate,
            retailer: window._fmCurrentRetailer || '',
            correction_type: 'field_missing'
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) { showToast(data.error || '처리 실패', 'error'); return; }
        var st = window._fmDetailState;
        var nk = rowId + '_' + col;
        st.normalReviews[nk] = { reason: reason, memo: memo, created_id: '' };
        showToast('정상 처리 완료', 'success');
        _fmHideReviewBar();
        _fmRenderPage(st.pager ? st.pager.currentPage || 1 : 1);
        setTimeout(function() { _fmBindEditEvents(); }, 100);
    })
    .catch(function(e) { console.error(e); showToast('처리 실패', 'error'); });
};

