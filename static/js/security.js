/**
 * 보안 및 API 헬퍼 함수
 *
 * - esc(str)           : HTML 특수문자 이스케이프 (XSS 방어)
 * - escJs(str)         : JS 문자열 리터럴 이스케이프 (onclick 등)
 * - safeUrl(url)       : 안전한 URL 반환 (javascript: 차단)
 * - getCsrfToken()     : Django CSRF 쿠키에서 토큰 읽기 (POST 요청용)
 * - fetchAPI(url)      : API 호출 헬퍼 (GET 요청, JSON 응답)
 */

// HTML 이스케이프 (XSS 방어)
function esc(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// JS 문자열 리터럴 이스케이프 (onclick 등에서 사용)
function escJs(str) {
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// 안전한 URL 반환 (javascript: 등 차단)
function safeUrl(url) {
    if (!url) return '';
    const trimmed = url.trim();
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed;
    return '';
}

// CSRF 토큰 (Django POST 요청용)
function getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + '=')) {
            return cookie.substring(name.length + 1);
        }
    }
    return '';
}

// API 호출 헬퍼 (GET 요청)
async function fetchAPI(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}
