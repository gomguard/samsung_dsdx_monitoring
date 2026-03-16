/**
 * 날짜 유지 및 검증 함수
 * (의존: format.js — formatLocalDate, ui.js — showToast)
 *
 * - getPersistedDate()             : 저장된 조회 날짜 반환 (URL파라미터 > sessionStorage > 어제)
 * - setPersistedDate(dateStr)      : 조회 날짜를 sessionStorage에 저장
 * - validateQueryDate(dateStr)     : 미래 날짜 여부 체크 (미래면 false + 토스트)
 * - date input 자동 보정            : 년도 4자리 제한, 8자리 숫자 자동 포맷
 */

const DATE_STORAGE_KEY = 'monitoring_target_date';

function getPersistedDate() {
    // 1. URL 파라미터 확인
    const urlParams = new URLSearchParams(window.location.search);
    const urlDate = urlParams.get('date');
    if (urlDate && /^\d{4}-\d{2}-\d{2}$/.test(urlDate)) {
        setPersistedDate(urlDate);
        return urlDate;
    }

    // 2. sessionStorage 확인
    const storedDate = sessionStorage.getItem(DATE_STORAGE_KEY);
    if (storedDate && /^\d{4}-\d{2}-\d{2}$/.test(storedDate)) {
        return storedDate;
    }

    // 3. 기본값: 어제
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return formatLocalDate(yesterday);
}

function setPersistedDate(dateStr) {
    if (dateStr && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        sessionStorage.setItem(DATE_STORAGE_KEY, dateStr);
    }
}

function validateQueryDate(dateStr, inputId) {
    const defaultDate = getPersistedDate();

    if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        showToast('날짜 형식이 맞지 않습니다. YYYY-MM-DD 형식으로 입력하세요.', 'warning');
        if (inputId) document.getElementById(inputId).value = defaultDate;
        return false;
    }

    const today = formatLocalDate(new Date());
    if (dateStr > today) {
        showToast('오늘 이후 날짜로는 조회할 수 없습니다.', 'warning');
        if (inputId) document.getElementById(inputId).value = defaultDate;
        return false;
    }
    return true;
}

/**
 * 전날/다음날 이동 (공통)
 * @param {string} inputId - date input 엘리먼트 ID (기본: 'targetDate')
 * @param {function} callback - 날짜 변경 후 호출할 함수
 */
function setPrevDay(inputId, callback) {
    var id = inputId || 'targetDate';
    var input = document.getElementById(id);
    var date = new Date(input.value);
    date.setDate(date.getDate() - 1);
    input.value = formatLocalDate(date);
    if (callback) callback();
}

function setNextDay(inputId, callback) {
    var id = inputId || 'targetDate';
    var input = document.getElementById(id);
    var current = new Date(input.value);
    current.setDate(current.getDate() + 1);
    var nextStr = formatLocalDate(current);
    var todayStr = formatLocalDate(new Date());
    if (nextStr > todayStr) {
        showToast('오늘 이후 날짜로는 조회할 수 없습니다.', 'warning');
        return;
    }
    input.value = nextStr;
    if (callback) callback();
}

// 날짜 입력 필드 자동 보정 (년도 4자리 제한)
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[type="date"]').forEach(input => {
        if (!input.hasAttribute('max')) {
            input.max = '9999-12-31';
        }
        input.addEventListener('input', function() {
            const raw = this.value.replace(/-/g, '');
            if (/^\d{8}$/.test(raw)) {
                this.value = `${raw.substring(0,4)}-${raw.substring(4,6)}-${raw.substring(6,8)}`;
            } else if (this.value) {
                const parts = this.value.split('-');
                if (parts[0] && parts[0].length > 4) {
                    parts[0] = parts[0].substring(0, 4);
                    this.value = parts.join('-');
                }
            }
        });
    });
});
