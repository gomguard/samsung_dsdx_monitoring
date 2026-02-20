/**
 * 세션 타이머
 * (의존: ui.js — showConfirm)
 *
 * 1시간 자동 만료, 사용자 활동(클릭/키입력/스크롤) 감지 시 리셋
 */
(function() {
    const SESSION_DURATION = 60 * 60;
    const WARNING_THRESHOLD = 10 * 60;
    const CRITICAL_THRESHOLD = 5 * 60;

    let remainingSeconds = SESSION_DURATION;
    let lastActivity = Date.now();

    const countdownEl = document.getElementById('session-countdown');
    const timerContainer = document.querySelector('.session-timer');

    if (!countdownEl || !timerContainer) return;

    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    function updateTimer() {
        remainingSeconds--;

        if (remainingSeconds <= 0) {
            countdownEl.textContent = '00:00';
            showConfirm('세션이 만료되었습니다. 다시 로그인해주세요.', 'warning').then(function() {
                window.location.href = '/accounts/logout/';
            });
            return;
        }

        countdownEl.textContent = formatTime(remainingSeconds);

        timerContainer.classList.remove('warning', 'critical');
        if (remainingSeconds <= CRITICAL_THRESHOLD) {
            timerContainer.classList.add('critical');
        } else if (remainingSeconds <= WARNING_THRESHOLD) {
            timerContainer.classList.add('warning');
        }
    }

    function resetTimer() {
        remainingSeconds = SESSION_DURATION;
        lastActivity = Date.now();
        timerContainer.classList.remove('warning', 'critical');
        countdownEl.textContent = formatTime(remainingSeconds);
    }

    const activityEvents = ['click', 'keypress', 'scroll'];
    let activityTimeout;

    activityEvents.forEach(event => {
        document.addEventListener(event, function() {
            if (activityTimeout) return;
            activityTimeout = setTimeout(() => {
                activityTimeout = null;
            }, 500);
            resetTimer();
        }, { passive: true });
    });

    setInterval(updateTimer, 1000);
    countdownEl.textContent = formatTime(remainingSeconds);
})();
