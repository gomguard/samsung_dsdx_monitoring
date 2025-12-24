/**
 * 5단계 방어 체계 모니터링 시스템 - 공통 JavaScript
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
