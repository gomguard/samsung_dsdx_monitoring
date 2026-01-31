/**
 * 5단계 방어 체계 모니터링 시스템 - 공통 JavaScript
 *
 * ============================================================
 * 함수 목록
 * ============================================================
 *
 * [포맷팅]
 * - formatNumber(num)              : 숫자를 천단위 콤마 포맷으로 변환 (예: 1234567 → "1,234,567")
 * - formatDate(dateString)         : 날짜를 한국식 포맷으로 변환 (예: "2026. 01. 31.")
 * - formatDateTime(dateString)     : 날짜+시간을 한국식 포맷으로 변환 (예: "2026. 01. 31. 오후 3:30")
 * - formatLocalDate(date)          : Date 객체를 YYYY-MM-DD 문자열로 변환 (예: "2026-01-31")
 *
 * [상태 처리]
 * - getStatusClass(status)         : 상태값에 따른 CSS 클래스 반환 (ok, warning, critical, pending)
 * - getStatusLabel(status)         : 상태값을 한글 라벨로 변환 (정상, 주의, 위험, 대기)
 *
 * [UI 헬퍼]
 * - showLoading(container)         : 컨테이너에 로딩 스피너 표시
 * - showError(container, message)  : 컨테이너에 에러 메시지 표시
 * - showToast(message, type, duration) : 화면 중앙에 토스트 알림 표시
 *                                    type: 'success' | 'error' | 'warning' | 'info'
 *                                    duration: 표시 시간(ms), 기본 3000
 *
 * [API]
 * - fetchAPI(url)                  : API 호출 헬퍼 (GET 요청, JSON 응답)
 *
 * [날짜 유지]
 * - getPersistedDate()             : 저장된 조회 날짜 반환 (URL파라미터 > sessionStorage > 어제)
 * - setPersistedDate(dateStr)      : 조회 날짜를 sessionStorage에 저장
 * - validateQueryDate(dateStr)     : 미래 날짜 여부 체크 (미래면 false + 토스트)
 *
 * [세션]
 * - 세션 타이머 (IIFE)              : 자동 세션 만료 관리 (1시간), 활동 감지 시 리셋
 *
 * ============================================================
 */

// 숫자 포맷팅
function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(num);
}

// API 호출 헬퍼
async function fetchAPI(url) {
    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API fetch error:', error);
        throw error;
    }
}

// 상태에 따른 클래스 반환
function getStatusClass(status) {
    switch (status.toUpperCase()) {
        case 'OK':
            return 'ok';
        case 'WARNING':
            return 'warning';
        case 'CRITICAL':
            return 'critical';
        case 'PENDING':
            return 'pending';
        default:
            return '';
    }
}

// 상태 한글 변환
function getStatusLabel(status) {
    switch (status.toUpperCase()) {
        case 'OK':
            return '정상';
        case 'WARNING':
            return '주의';
        case 'CRITICAL':
            return '위험';
        case 'PENDING':
            return '대기';
        default:
            return status;
    }
}

// 로딩 표시
function showLoading(container) {
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <span style="margin-left: 12px;">로딩 중...</span>
        </div>
    `;
}

// 에러 표시
function showError(container, message) {
    container.innerHTML = `
        <div class="loading" style="color: var(--color-critical);">
            ${message || '데이터를 불러올 수 없습니다.'}
        </div>
    `;
}

// 날짜 포맷팅
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// 시간 포맷팅
function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 로컬 날짜 포맷팅 (YYYY-MM-DD)
function formatLocalDate(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

// 조회 날짜 저장 키
const DATE_STORAGE_KEY = 'monitoring_target_date';

// 저장된 조회 날짜 반환 (우선순위: URL파라미터 > sessionStorage > 어제)
function getPersistedDate() {
    // 1. URL 파라미터 확인
    const urlParams = new URLSearchParams(window.location.search);
    const urlDate = urlParams.get('date');
    if (urlDate && /^\d{4}-\d{2}-\d{2}$/.test(urlDate)) {
        setPersistedDate(urlDate); // sessionStorage에도 저장
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

// 조회 날짜를 sessionStorage에 저장
function setPersistedDate(dateStr) {
    if (dateStr && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        sessionStorage.setItem(DATE_STORAGE_KEY, dateStr);
    }
}

// 조회 날짜 유효성 검사 (형식 + 미래 날짜 체크)
// inputId 전달 시 실패하면 디폴트 날짜로 자동 변경
function validateQueryDate(dateStr, inputId) {
    const defaultDate = getPersistedDate();

    // 형식 체크
    if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        showToast('날짜 형식이 맞지 않습니다. YYYY-MM-DD 형식으로 입력하세요.', 'warning');
        if (inputId) document.getElementById(inputId).value = defaultDate;
        return false;
    }

    // 미래 날짜 체크
    const today = formatLocalDate(new Date());
    if (dateStr > today) {
        showToast('오늘 이후 날짜로는 조회할 수 없습니다.', 'warning');
        if (inputId) document.getElementById(inputId).value = defaultDate;
        return false;
    }
    return true;
}

// 날짜 입력 필드 설정 (년도 4자리 제한 + 자동 보정)
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[type="date"]').forEach(input => {
        // 년도 4자리 제한 (max 속성)
        if (!input.hasAttribute('max')) {
            input.max = '9999-12-31';
        }
        input.addEventListener('input', function() {
            // 하이픈 제거한 순수 숫자
            const raw = this.value.replace(/-/g, '');
            // 8자리 숫자면 YYYY-MM-DD로 변환
            if (/^\d{8}$/.test(raw)) {
                this.value = `${raw.substring(0,4)}-${raw.substring(4,6)}-${raw.substring(6,8)}`;
            }
            // 년도가 4자리 초과하면 4자리로 자름
            else if (this.value) {
                const parts = this.value.split('-');
                if (parts[0] && parts[0].length > 4) {
                    parts[0] = parts[0].substring(0, 4);
                    this.value = parts.join('-');
                }
            }
        });
    });
});

// Toast 알림 (화면 중앙)
function showToast(message, type = 'info', duration = 3000) {
    // 기존 토스트 제거
    const existingToast = document.getElementById('commonToast');
    if (existingToast) {
        existingToast.remove();
    }

    // 토스트 생성
    const toast = document.createElement('div');
    toast.id = 'commonToast';
    toast.className = 'common-toast';

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    const colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };

    toast.innerHTML = `
        <span style="margin-right: 8px; font-size: 16px;">${icons[type] || icons.info}</span>
        <span>${message}</span>
    `;

    toast.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) scale(0.9);
        background: ${colors[type] || colors.info};
        color: white;
        padding: 14px 28px;
        border-radius: 12px;
        font-size: 14px;
        font-weight: 500;
        z-index: 10000;
        opacity: 0;
        transition: all 0.3s ease;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: center;
    `;

    document.body.appendChild(toast);

    // 애니메이션
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translate(-50%, -50%) scale(1)';
    });

    // 자동 제거
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translate(-50%, -50%) scale(0.9)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 세션 타이머
(function() {
    const SESSION_DURATION = 60 * 60; // 1시간 (초)
    const WARNING_THRESHOLD = 10 * 60; // 10분 남았을 때 경고
    const CRITICAL_THRESHOLD = 5 * 60; // 5분 남았을 때 위험

    let remainingSeconds = SESSION_DURATION;
    let lastActivity = Date.now();

    const countdownEl = document.getElementById('session-countdown');
    const timerContainer = document.querySelector('.session-timer');

    if (!countdownEl || !timerContainer) return;

    // 시간 포맷팅 (MM:SS)
    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    // 타이머 업데이트
    function updateTimer() {
        remainingSeconds--;

        if (remainingSeconds <= 0) {
            // 세션 만료 - 로그아웃
            countdownEl.textContent = '00:00';
            alert('세션이 만료되었습니다. 다시 로그인해주세요.');
            window.location.href = '/accounts/logout/';
            return;
        }

        countdownEl.textContent = formatTime(remainingSeconds);

        // 스타일 업데이트
        timerContainer.classList.remove('warning', 'critical');
        if (remainingSeconds <= CRITICAL_THRESHOLD) {
            timerContainer.classList.add('critical');
        } else if (remainingSeconds <= WARNING_THRESHOLD) {
            timerContainer.classList.add('warning');
        }
    }

    // 활동 감지 시 타이머 리셋
    function resetTimer() {
        remainingSeconds = SESSION_DURATION;
        lastActivity = Date.now();
        timerContainer.classList.remove('warning', 'critical');
        countdownEl.textContent = formatTime(remainingSeconds);
    }

    // 사용자 활동 감지 (클릭, 키입력, 스크롤)
    const activityEvents = ['click', 'keypress', 'scroll'];
    let activityTimeout;

    activityEvents.forEach(event => {
        document.addEventListener(event, function() {
            // 디바운스: 0.5초 내 연속 이벤트 무시
            if (activityTimeout) return;
            activityTimeout = setTimeout(() => {
                activityTimeout = null;
            }, 500);

            // 서버에 활동 알림 (세션 갱신)
            // SESSION_SAVE_EVERY_REQUEST=True 설정으로 모든 요청에서 세션이 갱신됨
            // 여기서는 클라이언트 타이머만 리셋
            resetTimer();
        }, { passive: true });
    });

    // 1초마다 타이머 업데이트
    setInterval(updateTimer, 1000);

    // 초기 표시
    countdownEl.textContent = formatTime(remainingSeconds);
})();
