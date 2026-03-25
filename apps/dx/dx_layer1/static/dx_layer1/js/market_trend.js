// ============================================================
// Market Trend Render Functions
// ============================================================
function renderMarketTrendCategory(cat, checkIdx, catIdx) {
    const catStatusClass = getStatusClass(cat.status);
    const hasItems = cat.items && cat.items.length > 0;

    // Event/News를 2열 레이아웃으로 표시
    let itemsHtml = '';
    if (hasItems) {
        itemsHtml = '<div class="sentiment-two-column no-side-padding" id="market-cat-' + checkIdx + '-' + catIdx + '">' +
            cat.items.map(item => {
                const itemStatusClass = getStatusClass(item.status);
                var detailUrl = '/dx/layer1/market-trend/?category=' + encodeURIComponent(cat.name) + '&content_type=' + encodeURIComponent(item.name) + '&date=' + getSelectedDate();
                return '<a class="sentiment-column ' + itemStatusClass + '" href="' + detailUrl + '" style="cursor: pointer; text-decoration: none; color: inherit; display: block;">' +
                    '<div class="sentiment-column-header">' +
                        '<span class="sentiment-column-title">' + item.name + '</span>' +
                        '<div class="sentiment-column-stats">' +
                            '<span class="sentiment-column-count">' + item.collected.toLocaleString() + '/' + item.expected.toLocaleString() + '</span>' +
                            '<span class="sentiment-column-rate ' + itemStatusClass + '">' + item.rate + '%</span>' +
                            getStatusBadge(item.status) +
                        '</div>' +
                    '</div>' +
                '</a>';
            }).join('') +
        '</div>';
    }

    return '<div class="sentiment-category-item">' +
        '<div class="sentiment-category-header" onclick="toggleMarketCategory(this, ' + checkIdx + ', ' + catIdx + ')">' +
            '<div class="sentiment-category-info">' +
                '<span class="toggle-icon-small">▶</span>' +
                '<span class="sentiment-category-name">' + cat.name + '</span>' +
            '</div>' +
            '<div class="sentiment-category-stats">' +
                '<span class="sentiment-category-count">' + cat.total.toLocaleString() + '/' + cat.expected.toLocaleString() + '</span>' +
                '<span class="sentiment-category-rate ' + catStatusClass + '">' + cat.rate + '%</span>' +
                getStatusBadge(cat.status) +
            '</div>' +
        '</div>' +
        itemsHtml +
    '</div>';
}

function toggleMarketCategory(element, checkIdx, catIdx) {
    const container = document.getElementById('market-cat-' + checkIdx + '-' + catIdx);
    const icon = element.querySelector('.toggle-icon-small');

    if (container) {
        container.classList.toggle('show');
        if (icon) {
            icon.classList.toggle('expanded');
        }
    }
}

function renderMarketTrendCheck(check, checkIdx) {
    const hasCategories = check.categories && check.categories.length > 0;
    const statusClass = getStatusClass(check.status);

    // US(NY) 시간과 KST 날짜+시간 형식: US(NY) 23:00 KST 2026-01-06 13:00
    const usTime = check.us_time ? check.us_time.split(' ')[1] : '23:00';
    const krTime = check.kr_time || '';
    const isDst = check.is_dst || false;
    const kstLabel = isDst ? 'KST(DST)' : 'KST';

    const timeHeader = '<div class="time-slot-item" style="margin-bottom: 16px;">' +
        '<div class="time-slot-header" style="cursor: default;">' +
            '<div class="time-slot-info">' +
                '<span class="time-slot-name">수집 시간</span>' +
                '<span class="time-slot-time">' +
                    '<span class="utc">US(NY) ' + usTime + '</span>' +
                    '<span class="kst">' + kstLabel + ' ' + krTime + '</span>' +
                '</span>' +
            '</div>' +
        '</div>' +
    '</div>';

    let categoriesHtml = '';
    if (hasCategories) {
        // TV, HHP 순서로 정렬
        const sortedCategories = L1.sortCategories(check.categories, 'name');

        // TV/HHP 카드를 2열로 배치 (YouTube와 동일한 구조)
        const categoryCardsHtml = sortedCategories.map(cat => {
            const hasItems = cat.items && cat.items.length > 0;

            // Event/News 아이템들을 세로로 표시 (YouTube의 로그/비디오/댓글과 동일한 스타일)
            let itemsHtml = '';
            if (hasItems) {
                itemsHtml = cat.items.map(item => {
                    const itemStatusClass = getStatusClass(item.status);
                    var itemDetailUrl = '/dx/layer1/market-trend/?category=' + encodeURIComponent(cat.name) + '&content_type=' + encodeURIComponent(item.name) + '&date=' + getSelectedDate();
                    return '<a class="sentiment-retailer-item ' + itemStatusClass + '" href="' + itemDetailUrl + '" style="cursor: pointer; text-decoration: none; color: inherit;">' +
                        '<span class="sentiment-retailer-name">' + item.name + '</span>' +
                        '<div class="sentiment-retailer-stats">' +
                            '<span class="sentiment-retailer-count">' + item.collected.toLocaleString() + '/' + item.expected.toLocaleString() + '</span>' +
                            '<span class="sentiment-retailer-rate ' + itemStatusClass + '">' + item.rate + '%</span>' +
                            getStatusBadge(item.status) +
                        '</div>' +
                    '</a>';
                }).join('');
            }

            // TV/HHP 카드 (YouTube와 동일한 구조)
            return '<div class="sentiment-column">' +
                '<div class="sentiment-column-header">' +
                    '<span class="sentiment-column-title">' + cat.name + '</span>' +
                    '<div class="sentiment-column-stats">' +
                        getStatusBadge(cat.status) +
                    '</div>' +
                '</div>' +
                '<div class="sentiment-retailer-list">' +
                    itemsHtml +
                '</div>' +
            '</div>';
        }).join('');

        categoriesHtml = '<div class="time-slots-container" id="time-slots-' + checkIdx + '">' +
            timeHeader +
            '<div class="sentiment-two-column show no-side-padding">' +
                categoryCardsHtml +
            '</div>' +
        '</div>';
    } else {
        var defaultCategories = ['TV', 'HHP'];
        categoriesHtml = '<div class="time-slots-container" id="time-slots-' + checkIdx + '">' +
            timeHeader +
            '<div class="sentiment-two-column show no-side-padding">' +
                defaultCategories.map(function(catName) {
                    return '<div class="sentiment-column">' +
                        '<div class="sentiment-column-header">' +
                            '<span class="sentiment-column-title">' + catName + '</span>' +
                            '<div class="sentiment-column-stats">' +
                                '<span class="status-badge pending"><span class="status-dot"></span>대기중</span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="sentiment-retailer-list">' +
                            ['Event', 'News'].map(function(itemName) {
                                return '<div class="sentiment-retailer-item pending">' +
                                    '<span class="sentiment-retailer-name">' + itemName + '</span>' +
                                    '<div class="sentiment-retailer-stats">' +
                                        '<span class="sentiment-retailer-count">0/0</span>' +
                                        '<span class="sentiment-retailer-rate pending">0%</span>' +
                                        '<span class="status-badge pending"><span class="status-dot"></span>대기중</span>' +
                                    '</div>' +
                                '</div>';
                            }).join('') +
                        '</div>' +
                    '</div>';
                }).join('') +
            '</div>' +
        '</div>';
    }

    return '<div class="check-item">' +
        '<div class="check-main" onclick="toggleTimeSlots(this, ' + checkIdx + ')">' +
            '<div class="check-info">' +
                '<div class="check-name">' +
                    '<span class="toggle-icon">▶</span>' +
                    check.name +
                '</div>' +
                '<div class="check-description">' + check.description + '</div>' +
            '</div>' +
            '<div class="check-criteria">' +
                '<span class="criteria-item ok">정상: 100%</span>' +
                '<span class="criteria-item critical">심각: 100% 미만</span>' +
            '</div>' +
            '<div class="check-stats">' +
                '<div class="check-stat">' +
                    '<div class="value ' + statusClass + '">' + check.rate + '%</div>' +
                    '<div class="label">수집률</div>' +
                '</div>' +
                getStatusBadge(check.status) +
            '</div>' +
        '</div>' +
        categoriesHtml +
    '</div>';
}

// ============================================================
// Raw Data View
// ============================================================

var rawView = new RawDataView({
    apiUrl: '/dx/layer1/market-trend/api/raw-data/',
    backUrl: '/dx/layer1/market-trend/',
    title: function(p) {
        var t = 'Market Trend - ' + p.category;
        if (p.content_type) t += ' (' + p.content_type + ')';
        return t;
    },
    urlParams: ['category', 'content_type']
});

// ============================================================
// Section Data Loading
// ============================================================
async function loadSectionData() {
    if (rawView.checkUrlAndShow()) return;

    try {
        var selectedDate = getSelectedDate();
        try { currentCheckStatus = await loadCheckStatus(selectedDate); }
        catch (e) { currentCheckStatus = null; }

        var response = await fetch('/dx/layer1/api/stats/?date=' + selectedDate + '&check_type=market_trend');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();
        currentStatsData = data;

        var check = data.checks ? data.checks.find(function(c) { return c.check_type === 'market_trend'; }) : null;
        var checkIdx = check ? data.checks.indexOf(check) : 0;
        if (!check) check = { name: 'Market Trend', description: '데이터 없음', check_type: 'market_trend', status: 'PENDING', categories: [] };

        var container = document.getElementById('section-content');
        var html = renderMarketTrendCheck(check, checkIdx);
        html = html.replace('<div class="check-item">', '<div class="check-item" data-check-type="market_trend">');
        container.innerHTML = html;
        addCheckBadges();
        expandSectionContent();
    } catch (error) {
        console.error('Load failed:', error);
        L1.renderError('section-content', error.message);
    }
}

function loadAllData() { loadSectionData(); }

L1.initLayer1Page();
