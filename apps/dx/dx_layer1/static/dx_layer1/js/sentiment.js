// ============================================================
// Sentiment Render Functions
// ============================================================
function renderSentimentRetailer(r, category, period) {
    const rStatusClass = getStatusClass(r.status);
    const inner = '<span class="sentiment-retailer-name">' + r.name + '</span>' +
        '<div class="sentiment-retailer-stats">' +
            '<span class="sentiment-retailer-count">' + r.analyzed.toLocaleString() + '/' + r.target.toLocaleString() + '건</span>' +
            '<span class="sentiment-retailer-rate ' + rStatusClass + '">' + r.rate + '%</span>' +
            getStatusBadge(r.status) +
        '</div>';
    if (r.analyzed === 0) {
        return '<div class="sentiment-retailer-item ' + rStatusClass + '" style="cursor: pointer;" onclick="showToast(\'조회된 데이터가 없습니다.\', \'info\')">' + inner + '</div>';
    }
    const detailUrl = '/dx/layer1/sentiment/?category=' + encodeURIComponent(category) +
        '&retailer=' + encodeURIComponent(r.name) +
        '&period=' + encodeURIComponent(period) +
        '&date=' + getSelectedDate();
    return '<a class="sentiment-retailer-item ' + rStatusClass + '" href="' + detailUrl + '" style="cursor: pointer; text-decoration: none; color: inherit;">' + inner + '</a>';
}

function renderSentimentSlot(slot, category) {
    const slotStatusClass = getStatusClass(slot.status);
    const hasRetailers = slot.retailers && slot.retailers.length > 0;
    const period = slot.time;  // '오전' 또는 '오후'
    const retailersHtml = hasRetailers
        ? slot.retailers.map(r => renderSentimentRetailer(r, category, period)).join('')
        : '<div style="color: var(--text-secondary); padding: 8px;">데이터 없음</div>';

    return '<div class="sentiment-column">' +
        '<div class="sentiment-column-header">' +
            '<span class="sentiment-column-title">' + slot.time + ' (' + slot.target.toLocaleString() + '건)</span>' +
            '<div class="sentiment-column-stats">' +
                '<span class="sentiment-column-count">' + slot.analyzed.toLocaleString() + '/' + slot.target.toLocaleString() + '</span>' +
                '<span class="sentiment-column-rate ' + slotStatusClass + '">' + slot.rate + '%</span>' +
                getStatusBadge(slot.status) +
            '</div>' +
        '</div>' +
        '<div class="sentiment-retailer-list">' + retailersHtml + '</div>' +
    '</div>';
}

function renderSentimentCategory(cat, checkIdx, catIdx) {
    const catStatusClass = getStatusClass(cat.status);
    const hasTimeSlots = cat.time_slots && cat.time_slots.length > 0;
    const category = cat.name;  // 'TV' 또는 'HHP'

    let timeSlotsHtml = '';
    if (hasTimeSlots) {
        timeSlotsHtml = '<div class="sentiment-two-column" id="sentiment-cat-' + checkIdx + '-' + catIdx + '">' +
            cat.time_slots.map(slot => renderSentimentSlot(slot, category)).join('') +
        '</div>';
    }

    return '<div class="sentiment-category-item">' +
        '<div class="sentiment-category-header" onclick="toggleSentimentCategory(this, ' + checkIdx + ', ' + catIdx + ')">' +
            '<div class="sentiment-category-info">' +
                '<span class="toggle-icon-small">▶</span>' +
                '<span class="sentiment-category-name">' + cat.name + '</span>' +
            '</div>' +
            '<div class="sentiment-category-stats">' +
                '<span class="sentiment-category-count">' + cat.analyzed.toLocaleString() + '/' + cat.target.toLocaleString() + '</span>' +
                '<span class="sentiment-category-rate ' + catStatusClass + '">' + cat.rate + '%</span>' +
                getStatusBadge(cat.status) +
            '</div>' +
        '</div>' +
        timeSlotsHtml +
    '</div>';
}

function renderSentimentCheck(check, checkIdx) {
    const hasCategories = check.categories && check.categories.length > 0;
    const statusClass = getStatusClass(check.status);

    // US(NY) 시간과 KST 날짜+시간 형식: US(NY) 2026-01-06 01:00 KST 2026-01-06 15:00
    // 감성분석은 다음날 실행되므로 날짜 포함해서 표시
    const usTime = check.us_time || '';
    const krTime = check.kr_time || '';
    const isDst = check.is_dst || false;
    const kstLabel = isDst ? 'KST(DST)' : 'KST';

    const timeHeader = '<div class="time-slot-item" style="margin-bottom: 16px;">' +
        '<div class="time-slot-header" style="cursor: default;">' +
            '<div class="time-slot-info">' +
                '<span class="time-slot-name">분석 시간</span>' +
                '<span class="time-slot-time">' +
                    '<span class="utc">US(NY) ' + usTime + '</span>' +
                    '<span class="kst">' + kstLabel + ' ' + krTime + '</span>' +
                '</span>' +
            '</div>' +
        '</div>' +
    '</div>';

    let categoriesHtml = '';
    if (hasCategories) {
        categoriesHtml = '<div class="time-slots-container" id="time-slots-' + checkIdx + '">' +
            timeHeader +
            '<div class="sentiment-categories">' +
                check.categories.map((cat, catIdx) => renderSentimentCategory(cat, checkIdx, catIdx)).join('') +
            '</div>' +
        '</div>';
    } else {
        var defaultCats = ['TV', 'HHP'];
        var defaultRets = ['Amazon', 'Bestbuy', 'Walmart'];
        categoriesHtml = '<div class="time-slots-container" id="time-slots-' + checkIdx + '">' +
            timeHeader +
            '<div class="sentiment-categories">' +
                defaultCats.map(function(catName) {
                    return '<div class="sentiment-category-item">' +
                        '<div class="sentiment-category-header">' +
                            '<div class="sentiment-category-info">' +
                                '<span class="toggle-icon-small">▶</span>' +
                                '<span class="sentiment-category-name">' + catName + '</span>' +
                            '</div>' +
                            '<div class="sentiment-category-stats">' +
                                '<span class="sentiment-category-count">0/0</span>' +
                                '<span class="sentiment-category-rate pending">0%</span>' +
                                '<span class="status-badge pending"><span class="status-dot"></span>대기중</span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="sentiment-two-column">' +
                            ['오전', '오후'].map(function(period) {
                                return '<div class="sentiment-column pending">' +
                                    '<div class="sentiment-column-header">' +
                                        '<span class="sentiment-column-title">' + period + ' (0건)</span>' +
                                        '<div class="sentiment-column-stats">' +
                                            '<span class="sentiment-column-count">0/0</span>' +
                                            '<span class="sentiment-column-rate pending">0%</span>' +
                                            '<span class="status-badge pending"><span class="status-dot"></span>대기중</span>' +
                                        '</div>' +
                                    '</div>' +
                                    '<div class="sentiment-retailer-list">' +
                                        defaultRets.map(function(ret) {
                                            return '<div class="sentiment-retailer-item pending">' +
                                                '<span class="sentiment-retailer-name">' + ret + '</span>' +
                                                '<div class="sentiment-retailer-stats">' +
                                                    '<span class="sentiment-retailer-count">0/0건</span>' +
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
                    '<div class="label">분석률</div>' +
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
    apiUrl: '/dx/layer1/sentiment/api/raw-data/',
    backUrl: '/dx/layer1/sentiment/',
    title: function(p) { return p.category + ' Sentiment - ' + p.retailer + ' (' + p.period + ')'; },
    urlParams: ['category', 'retailer', 'period']
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

        var response = await fetch('/dx/layer1/api/stats/?date=' + selectedDate + '&check_type=sentiment');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();
        currentStatsData = data;

        var check = data.checks ? data.checks.find(function(c) { return c.check_type === 'sentiment'; }) : null;
        var checkIdx = check ? data.checks.indexOf(check) : 0;
        if (!check) check = { name: 'Retail 감성분석', description: '데이터 없음', check_type: 'sentiment', status: 'PENDING', categories: [] };

        var container = document.getElementById('section-content');
        var html = renderSentimentCheck(check, checkIdx);
        html = html.replace('<div class="check-item">', '<div class="check-item" data-check-type="sentiment">');
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
