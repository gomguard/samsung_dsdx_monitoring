/**
 * 공통 버튼 컴포넌트
 *
 * 파일 위치: static/js/buttons.js
 * 스타일: static/css/common.css (.app-btn, .app-icon-btn)
 *
 * ============================================================
 * 1. 텍스트 버튼 (AppButton)
 * ============================================================
 *
 * 컨테이너에 삽입:
 *    AppButton('#container', '출력', 'openReport', { icon: 'print', style: 'outline' });
 *
 * HTML 문자열 반환:
 *    const html = AppButton.html('삭제', 'deleteItem', { icon: 'delete', style: 'danger' });
 *
 * 옵션:
 *   icon   - 아이콘 이름 (print, plus, edit, delete, copy, download, search, refresh, back, power)
 *   style  - 버튼 스타일   기본: outline
 *            용도별: save, cancel, delete
 *            색상별: primary, outline, danger, success, teal
 *   size   - 버튼 크기 (sm, md)   기본: md
 *   href   - 링크 URL (지정 시 <a> 태그로 생성, 미지정 시 <button> 태그)
 *
 * ============================================================
 * 2. 아이콘 버튼 (AppButton.icon / AppButton.iconHtml)
 * ============================================================
 *
 * 컨테이너에 삽입:
 *    AppButton.icon('#actions', 'edit', 'goEdit(3)', { color: 'blue' });
 *
 * HTML 문자열 반환 (테이블 렌더링 등):
 *    AppButton.iconHtml('edit', `goEdit(${id})`, { color: 'blue' })
 *    AppButton.iconHtml('power', `toggle(${id})`, { color: 'yellow' })
 *    AppButton.iconHtml('delete', `remove(${id})`, { color: 'red' })
 *
 * 옵션:
 *   color  - blue, yellow, red, green, purple   기본: blue
 *   href   - 링크 URL (지정 시 <a> 태그로 생성)
 *
 * ============================================================
 */

var AppButton = (function() {

    var ICONS = {
        print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>',
        plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
        delete: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
        copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
        download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
        refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
        back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>',
        power: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>'
    };

    // 텍스트 버튼 HTML
    function buildHtml(label, fnName, opts) {
        opts = opts || {};
        var style = opts.style || 'outline';
        var size = opts.size || 'md';
        var iconHtml = opts.icon && ICONS[opts.icon] ? ICONS[opts.icon] : '';
        var cls = 'app-btn app-btn-' + style + ' app-btn-' + size;
        var content = (iconHtml ? iconHtml + ' ' : '') + label;

        if (opts.href) {
            return '<a href="' + opts.href + '" class="' + cls + '">' + content + '</a>';
        }

        var onclick = fnName ? ' onclick="' + fnName + '()"' : '';
        return '<button class="' + cls + '"' + onclick + '>' + content + '</button>';
    }

    // 아이콘별 기본 색상
    var ICON_COLORS = {
        edit: 'blue',
        delete: 'red',
        power: 'yellow',
        plus: 'green',
        copy: 'blue',
        download: 'blue',
        search: 'blue',
        refresh: 'blue',
        print: 'blue',
        back: 'blue'
    };

    // 아이콘 전용 버튼 HTML
    //   style: 'ghost' — 배경 없는 인라인 아이콘 (테이블 셀 내 복사 등)
    function buildIconHtml(iconName, fnExpr, opts) {
        opts = opts || {};
        var iconHtml = ICONS[iconName] || '';
        var title = opts.title ? ' title="' + opts.title + '"' : '';
        var onclick = fnExpr ? ' onclick="' + fnExpr + '"' : '';

        if (opts.style === 'ghost') {
            var cls = 'app-icon-btn-ghost';
            if (opts.href) {
                return '<a href="' + opts.href + '" class="' + cls + '"' + title + '>' + iconHtml + '</a>';
            }
            return '<button class="' + cls + '"' + onclick + title + '>' + iconHtml + '</button>';
        }

        var color = opts.color || ICON_COLORS[iconName] || 'blue';
        var cls = 'app-icon-btn app-icon-btn-' + color;

        if (opts.href) {
            return '<a href="' + opts.href + '" class="' + cls + '"' + title + '>' + iconHtml + '</a>';
        }

        return '<button class="' + cls + '"' + onclick + title + '>' + iconHtml + '</button>';
    }

    // 텍스트 버튼 — 컨테이너 삽입
    function appButton(container, label, fnName, opts) {
        var el = typeof container === 'string' ? document.querySelector(container) : container;
        if (el) {
            el.insertAdjacentHTML('beforeend', buildHtml(label, fnName, opts));
        }
    }

    appButton.html = buildHtml;

    // 아이콘 버튼 — 컨테이너 삽입
    appButton.icon = function(container, iconName, fnExpr, opts) {
        var el = typeof container === 'string' ? document.querySelector(container) : container;
        if (el) {
            el.insertAdjacentHTML('beforeend', buildIconHtml(iconName, fnExpr, opts));
        }
    };

    // 아이콘 버튼 — HTML 문자열 반환
    appButton.iconHtml = buildIconHtml;

    return appButton;
})();
