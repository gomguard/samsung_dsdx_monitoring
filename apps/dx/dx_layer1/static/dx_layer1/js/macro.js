function renderMacroCheck(check, checkIdx) {
    var statusClass = getStatusClass(check.status);
    var isTargetDate = check.is_target_date;
    var isDst = check.is_dst || false;
    var kstLabel = isDst ? 'KST(DST)' : 'KST';
    var usTime = check.us_time ? check.us_time.split(' ')[1] : '';
    var krTime = check.kr_time || '';
    var scheduleLabel = check.schedule_label || '';
    var nextTargetDate = check.next_target_date || '';

    var scheduleHeader = '';
    if (isTargetDate && usTime) {
        scheduleHeader = '<div class="time-slot-item" style="margin-bottom: 16px;">'
            + '<div class="time-slot-header" style="cursor: default;">'
            + '<div class="time-slot-info">'
            + '<span class="time-slot-name">수집 시간</span>'
            + '<span class="time-slot-time">'
            + '<span class="utc">US(NY) ' + usTime + '</span>'
            + '<span class="kst">' + kstLabel + ' ' + krTime + '</span>'
            + '</span>'
            + (scheduleLabel ? '<span style="margin-left: 12px; font-size: 12px; color: var(--text-secondary);">(' + esc(scheduleLabel) + ')</span>' : '')
            + '</div>'
            + '</div>'
            + '</div>';
    } else if (!isTargetDate) {
        scheduleHeader = '<div class="time-slot-item" style="margin-bottom: 16px;">'
            + '<div class="time-slot-header" style="cursor: default;">'
            + '<div class="time-slot-info">'
            + '<span class="time-slot-name">다음 분석일</span>'
            + '<span class="time-slot-time">'
            + '<span class="kst">' + nextTargetDate + '</span>'
            + '</span>'
            + (scheduleLabel ? '<span style="margin-left: 12px; font-size: 12px; color: var(--text-secondary);">(' + esc(scheduleLabel) + ')</span>' : '')
            + '</div>'
            + '</div>'
            + '</div>';
    }

    var cardHtml = '';
    if (isTargetDate) {
        var detailUrl = '/dx/layer1/macro/?check_type=' + encodeURIComponent(check.check_type) + '&date=' + getSelectedDate();
        cardHtml = '<div class="sentiment-two-column show no-side-padding no-bg">'
            + '<a class="sentiment-column ' + statusClass + '" href="' + detailUrl + '" style="cursor: pointer; text-decoration: none; color: inherit; display: block;" title="클릭하여 원본 데이터 보기">'
            + '<div class="sentiment-column-header">'
            + '<span class="sentiment-column-title">수집량</span>'
            + '<div class="sentiment-column-stats">'
            + '<span class="sentiment-column-count">' + (check.actual || 0).toLocaleString() + '건</span>'
            + getStatusBadge(check.status)
            + '</div>'
            + '</div>'
            + '</a>'
            + '</div>';
    }

    var contentHtml = '<div class="time-slots-container" id="time-slots-' + checkIdx + '">'
        + scheduleHeader
        + cardHtml
        + '</div>';

    var statsHtml;
    if (!isTargetDate) {
        statsHtml = '<span class="status-badge pending"><span class="status-dot"></span>분석대상일 아님</span>';
    } else if (check.status === 'PENDING') {
        statsHtml = '<span class="status-badge pending"><span class="status-dot"></span>대기중</span>';
    } else {
        statsHtml = '<div class="check-stat">'
            + '<div class="value ' + statusClass + '">' + (check.actual || 0).toLocaleString() + '건</div>'
            + '<div class="label">수집건수</div>'
            + '</div>'
            + getStatusBadge(check.status);
    }

    return '<div class="check-item">'
        + '<div class="check-main" onclick="toggleTimeSlots(this, ' + checkIdx + ')">'
        + '<div class="check-info">'
        + '<div class="check-name"><span class="toggle-icon">▶</span>' + esc(check.name) + '</div>'
        + '<div class="check-description">' + (isTargetDate ? esc(check.description) : '분석대상일 아님') + '</div>'
        + '</div>'
        + '<div class="check-stats">' + statsHtml + '</div>'
        + '</div>'
        + contentHtml
        + '</div>';
}

// 렌더러 등록
var macroTypes = [
    'macro_capital_stock', 'macro_net_interest', 'macro_potential_gdp',
    'macro_gdp_ppp_nominal', 'macro_gdp_ppp_real', 'macro_disposable_income_real',
    'macro_cpi', 'macro_disposable_income_nominal', 'macro_household_debt', 'macro_rpi'
];
macroTypes.forEach(function(t) { L1.renderers[t] = renderMacroCheck; });

// 상세 페이지 로직 (macro 페이지에서만 실행)
if (typeof RawDataView !== 'undefined' && window.location.pathname.indexOf('/macro/') >= 0) {
    var rawView = new RawDataView({
        apiUrl: '/dx/layer1/macro/api/raw-data/',
        backUrl: '/dx/layer1/macro/',
        title: function(p) { return (p.check_type || 'Macro') + ' 원본 데이터'; },
        urlParams: ['check_type']
    });

    async function loadSectionData() {
        if (rawView.checkUrlAndShow()) return;

        var params = new URLSearchParams(window.location.search);
        var checkType = params.get('check_type');
        if (!checkType) {
            document.getElementById('section-content').innerHTML = '<div class="check-item"><div class="check-main"><div class="check-info"><div class="check-name">check_type 파라미터가 필요합니다.</div></div></div></div>';
            return;
        }

        try {
            var selectedDate = getSelectedDate();
            var response = await fetch('/dx/layer1/api/stats/?date=' + selectedDate + '&check_type=' + checkType);
            if (!response.ok) throw new Error('HTTP ' + response.status);
            var data = await response.json();

            var check = data.checks ? data.checks.find(function(c) { return c.check_type === checkType; }) : null;
            var checkIdx = check ? data.checks.indexOf(check) : 0;
            if (!check) check = { name: checkType, description: '데이터 없음', check_type: checkType, status: 'PENDING', is_target_date: false };

            var container = document.getElementById('section-content');
            container.innerHTML = renderMacroCheck(check, checkIdx);
            expandSectionContent();
        } catch (error) {
            console.error('Load failed:', error);
            L1.renderError('section-content', error.message);
        }
    }

    function loadAllData() { loadSectionData(); }
    L1.initLayer1Page();
}
