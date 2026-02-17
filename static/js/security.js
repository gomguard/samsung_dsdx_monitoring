/**
 * 보안 헬퍼 함수
 *
 * - esc(str)       : HTML 특수문자 이스케이프 (XSS 방어)
 * - escJs(str)     : JS 문자열 리터럴 이스케이프 (onclick 등)
 * - safeUrl(url)   : 안전한 URL 반환 (javascript: 차단)
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
