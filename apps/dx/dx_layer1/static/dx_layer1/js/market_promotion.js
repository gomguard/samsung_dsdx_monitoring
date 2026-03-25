function renderMarketPromotionCheck(check, checkIdx) {
    const hasRetailers = check.retailers && check.retailers.length > 0;
    const statusClass = getStatusClass(check.status);
    const isTargetDate = check.is_target_date;
    const isDst = check.is_dst || false;
    const kstLabel = isDst ? 'KST(DST)' : 'KST';

    // US(NY) 시간과 KST 날짜+시간 형식: US(NY) 18:00 KST 2026-01-05 08:00
    const usTime = check.us_time ? check.us_time.split(' ')[1] : '18:00';
    const krTime = check.kr_time || '';

    // 수집률 표시
    const rateDisplay = `${check.rate || 0}%`;

    // 다음 분석일 정보
    const nextTargetDate = check.next_target_date || '';

    // 스케줄 헤더 (Market Competitor Event와 동일한 스타일)
    let scheduleHeader = '';
    if (isTargetDate) {
        // 분석대상일: 수집 시간 표시
        scheduleHeader = `
            <div class="time-slot-item" style="margin-bottom: 16px;">
                <div class="time-slot-header" style="cursor: default;">
                    <div class="time-slot-info">
                        <span class="time-slot-name">수집 시간</span>
                        <span class="time-slot-time">
                            <span class="utc">US(NY) ${usTime}</span>
                            <span class="kst">${kstLabel} ${krTime}</span>
                        </span>
                        <span style="margin-left: 12px; font-size: 12px; color: var(--text-secondary);">(매주 월요일)</span>
                    </div>
                </div>
            </div>
        `;
    } else {
        // 분석대상일 아님: 다음 분석일 표시
        scheduleHeader = `
            <div class="time-slot-item" style="margin-bottom: 16px;">
                <div class="time-slot-header" style="cursor: default;">
                    <div class="time-slot-info">
                        <span class="time-slot-name">다음 분석일</span>
                        <span class="time-slot-time">
                            <span class="kst">${nextTargetDate}</span>
                        </span>
                        <span style="margin-left: 12px; font-size: 12px; color: var(--text-secondary);">(매주 월요일)</span>
                    </div>
                </div>
            </div>
        `;
    }

    let contentHtml = '';
    const isPending = check.status === 'PENDING';
    const isCollecting = check.status === 'COLLECTING';

    let detailContentHtml = '';
    if (isTargetDate && hasRetailers) {
        detailContentHtml = `
                <div class="sentiment-two-column show no-side-padding no-bg">
                    ${check.retailers.map(r => {
                        const retailerStatusClass = getStatusClass(r.status);
                        var detailUrl = '/dx/layer1/market-promotion/?retailer=' + encodeURIComponent(r.retailer) + '&date=' + getSelectedDate();
                        return `
                            <a class="sentiment-column ${retailerStatusClass}"
                                 style="cursor: pointer; text-decoration: none; color: inherit; display: block;"
                                 href="${detailUrl}"
                                 title="클릭하여 ${r.retailer} 데이터 보기">
                                <div class="sentiment-column-header">
                                    <span class="sentiment-column-title">${r.retailer}</span>
                                    <div class="sentiment-column-stats">
                                        <span class="sentiment-column-count">${r.collected.toLocaleString()}/${r.expected.toLocaleString()}</span>
                                        <span class="sentiment-column-rate ${retailerStatusClass}">${r.rate || 0}%</span>
                                        ${getStatusBadge(r.status)}
                                    </div>
                                </div>
                            </a>
                        `;
                    }).join('')}
                </div>`;
    }

    contentHtml = `
        <div class="time-slots-container" id="time-slots-${checkIdx}">
            ${scheduleHeader}
            ${detailContentHtml}
        </div>
    `;

    // 분석률 또는 분석대상일 아님 표시
    let statsHtml;
    if (!isTargetDate) {
        // 분석대상일 아님
        statsHtml = `
            <span class="status-badge pending">
                <span class="status-dot"></span>
                분석대상일 아님
            </span>
        `;
    } else if (isPending) {
        // 분석대상일이지만 수집 시작 전
        statsHtml = `
            <span class="status-badge pending">
                <span class="status-dot"></span>
                대기중
            </span>
        `;
    } else {
        // 수집 중이거나 완료
        statsHtml = `
            <div class="check-stat">
                <div class="value ${statusClass}">${rateDisplay}</div>
                <div class="label">수집률</div>
            </div>
            ${getStatusBadge(check.status)}
        `;
    }

    return `
        <div class="check-item">
            <div class="check-main" onclick="toggleTimeSlots(this, ${checkIdx})">
                <div class="check-info">
                    <div class="check-name">
                        <span class="toggle-icon">▶</span>
                        ${esc(check.name)}
                    </div>
                    <div class="check-description">${isTargetDate ? esc(check.description) : '분석대상일 아님'}</div>
                </div>
                ${isTargetDate ? `
                <div class="check-criteria">
                    <span class="criteria-item ok">정상: 100%</span>
                    <span class="criteria-item critical">심각: 100% 미만</span>
                </div>
                ` : ''}
                <div class="check-stats">
                    ${statsHtml}
                </div>
            </div>
            ${contentHtml}
        </div>
    `;
}

// ============================================================
// Raw Data View
// ============================================================

var rawView = new RawDataView({
    apiUrl: '/dx/layer1/market-promotion/api/raw-data/',
    backUrl: '/dx/layer1/market-promotion/',
    title: function(p) { return 'Market Promotion - ' + p.retailer; },
    urlParams: ['retailer']
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

        var response = await fetch('/dx/layer1/api/stats/?date=' + selectedDate + '&check_type=market_promotion');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();
        currentStatsData = data;

        var check = data.checks ? data.checks.find(function(c) { return c.check_type === 'market_promotion'; }) : null;
        var checkIdx = check ? data.checks.indexOf(check) : 0;
        if (!check) check = { name: 'Market Promotion', description: '데이터 없음', check_type: 'market_promotion', status: 'PENDING', retailers: [], is_target_date: false };

        var container = document.getElementById('section-content');
        var html = renderMarketPromotionCheck(check, checkIdx);
        html = html.replace('<div class="check-item">', '<div class="check-item" data-check-type="market_promotion">');
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

L1.renderers.market_promotion = renderMarketPromotionCheck;
