/**
 * 포맷팅 및 상태 처리 함수
 *
 * - formatNumber(num)              : 숫자 천단위 콤마 (1234567 → "1,234,567")
 * - formatDate(dateString)         : 한국식 날짜 ("2026. 01. 31.")
 * - formatDateTime(dateString)     : 한국식 날짜+시간 ("2026. 01. 31. 오후 3:30")
 * - formatLocalDate(date)          : YYYY-MM-DD 문자열 ("2026-01-31")
 * - getStatusClass(status)         : 상태별 CSS 클래스 (ok, warning, critical, pending)
 * - getStatusLabel(status)         : 상태별 한글 라벨 (정상, 주의, 위험, 대기)
 */

function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(num);
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

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

function formatLocalDate(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function getStatusClass(status) {
    switch (status.toUpperCase()) {
        case 'OK':       return 'ok';
        case 'WARNING':  return 'warning';
        case 'CRITICAL': return 'critical';
        case 'PENDING':  return 'pending';
        default:         return '';
    }
}

function getStatusLabel(status) {
    switch (status.toUpperCase()) {
        case 'OK':       return '정상';
        case 'WARNING':  return '주의';
        case 'CRITICAL': return '위험';
        case 'PENDING':  return '대기';
        default:         return status;
    }
}
