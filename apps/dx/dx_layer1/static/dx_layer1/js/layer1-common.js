// ============================================================
// Layer1 Common Utilities
// ============================================================
var L1 = (function() {

    // TV/HHP 카테고리 정렬 순서
    var sortOrder = ['TV', 'HHP'];

    /**
     * 시간 헤더 HTML 생성 (US/KST, DST 라벨)
     * @param {Object} options
     * @param {string} options.usTime - US(NY) 시간 (예: '04:00', '2026-01-06 01:00')
     * @param {string} options.krTime - KST 시간 (예: '2026-01-05 18:00')
     * @param {string} [options.krTimeEnd] - KST 종료 시간 (Retail 오후용)
     * @param {boolean} [options.isDst] - DST 여부
     * @param {string} [options.detailLink] - 추가 설명 링크/텍스트
     * @param {string} [options.label] - 시간 라벨 (기본: '수집 시간')
     * @returns {string} HTML 문자열
     */
    function buildTimeHeader(options) {
        var usTime = options.usTime || '';
        var krTime = options.krTime || '';
        var isDst = options.isDst || false;
        var label = options.label || '수집 시간';
        var kstLabel = isDst ? 'KST(DST)' : 'KST';

        var timeSpans = '<span class="utc">US(NY) ' + usTime + '</span>' +
            '<span class="kst">' + kstLabel + ' ' + krTime + '</span>';

        // krTimeEnd가 있으면 Retail 스타일 (오전/오후 가로 배치)
        if (options.krTimeEnd) {
            var usTimeAm = usTime;
            var usTimePm = options.usTimePm || '';
            timeSpans = '<span class="utc">[오전] US(NY) ' + usTimeAm + ' ' + kstLabel + ' ' + krTime + '</span>' +
                '<span class="utc">[오후] US(NY) ' + usTimePm + ' ' + kstLabel + ' ' + options.krTimeEnd + '</span>';
        }

        var detailHtml = '';
        if (options.detailLink) {
            detailHtml = '<span style="margin-left: 12px; font-size: 12px; color: var(--text-secondary);">' + options.detailLink + '</span>';
        }

        // krTimeEnd가 있으면 flex-direction: row 스타일 적용
        var timeStyle = options.krTimeEnd
            ? ' style="display: flex; flex-direction: row; align-items: center; gap: 24px;"'
            : '';

        return '<div class="time-slot-item" style="margin-bottom: 16px;">' +
            '<div class="time-slot-header" style="cursor: default;">' +
                '<div class="time-slot-info">' +
                    '<span class="time-slot-name">' + label + '</span>' +
                    '<span class="time-slot-time"' + timeStyle + '>' +
                        timeSpans +
                    '</span>' +
                    detailHtml +
                '</div>' +
            '</div>' +
        '</div>';
    }

    /**
     * TV/HHP 순서로 카테고리 배열 정렬
     * @param {Array} categories - 카테고리 객체 배열
     * @param {string} [nameKey] - 카테고리 이름 키 (기본: 'name', market 계열은 'category')
     * @returns {Array} 정렬된 새 배열
     */
    function sortCategories(categories, nameKey) {
        var key = nameKey || 'name';
        return [].concat(categories).sort(function(a, b) {
            var aIdx = sortOrder.indexOf(a[key]);
            var bIdx = sortOrder.indexOf(b[key]);
            if (aIdx === -1 && bIdx === -1) return 0;
            if (aIdx === -1) return 1;
            if (bIdx === -1) return -1;
            return aIdx - bIdx;
        });
    }

    /**
     * 에러 메시지 렌더링
     * @param {string} containerId - 컨테이너 요소 ID
     * @param {string} message - 에러 메시지
     */
    function renderError(containerId, message) {
        var container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = '<div class="check-item"><div class="check-main">' +
                '<div class="check-info">' +
                    '<div class="check-name">데이터 로드 실패</div>' +
                    '<div class="check-description">' + esc(message) + '</div>' +
                '</div></div></div>';
        }
    }

    /**
     * window.onload 공통 초기화
     * @param {Object} options
     * @param {Array} [options.modals] - 생성할 모달 목록 [{name, style}]
     * @param {Object} [options.filterBarOptions] - initFilterBar에 전달할 옵션
     * @param {Function} [options.onLoad] - 초기화 후 호출할 함수
     */
    function initLayer1Page(options) {
        options = options || {};

        window.onload = function() {
            // 모달 생성
            if (options.modals && options.modals.length > 0) {
                options.modals.forEach(function(modal) {
                    AppModal.create(modal.name, { style: modal.style });
                });
            }

            // URL date 파라미터가 있으면 FilterBar 날짜로 설정
            var urlDate = new URLSearchParams(window.location.search).get('date');
            if (urlDate) localStorage.setItem('monitoringSelectedDate', urlDate);

            // FilterBar 초기화
            initFilterBar(options.filterBarOptions);

            // 데이터 로딩
            if (typeof loadAllData === 'function') {
                loadAllData();
            }

            // 추가 초기화 콜백
            if (typeof options.onLoad === 'function') {
                options.onLoad();
            }
        };
    }

    return {
        sortOrder: sortOrder,
        buildTimeHeader: buildTimeHeader,
        sortCategories: sortCategories,
        renderError: renderError,
        initLayer1Page: initLayer1Page
    };

})();
