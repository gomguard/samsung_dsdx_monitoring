/**
 * 공통 버튼 컴포넌트
 *
 * JS: static/js/buttons.js
 * CSS: static/css/buttons.css
 *
 * ============================================================
 * 1. HTML 클래스 직접 사용
 * ============================================================
 *
 * 구조: .app-btn + 크기 + 스타일
 *
 *   <button class="app-btn app-btn-md app-btn-primary">조회</button>
 *   <button class="app-btn app-btn-md app-btn-outline">전날</button>
 *   <button class="app-btn app-btn-sm app-btn-save">저장</button>
 *   <button class="app-btn app-btn-sm app-btn-cancel">취소</button>
 *
 * 크기:
 *   app-btn-md   padding: 10px 20px,  font: 14px  (기본)
 *   app-btn-sm   padding: 6px 12px,  font: 12px
 *
 * 스타일 (--page-color 연동):
 *   app-btn-primary   배경: --page-color, 글자: 흰색
 *   app-btn-outline   테두리: --page-color, hover 시 배경 채움
 *
 * 스타일 (고정 색상):
 *   app-btn-save      보라 #7c3aed  (저장)
 *   app-btn-cancel    흰색 테두리    (취소)
 *   app-btn-delete    연빨강         (삭제)
 *   app-btn-danger    연빨강         (위험)
 *   app-btn-success   연초록         (성공)
 *   app-btn-teal      청록 #0d9488   (DX 전용)
 *
 * --page-color 설정 (각 페이지 <style>):
 *   :root { --page-color: {{ layer.color }}; }
 *   기본값: #7c3aed (common.css :root)
 *
 * ============================================================
 * 2. JS — 텍스트 버튼 (AppButton)
 * ============================================================
 *
 * 컨테이너에 삽입:
 *    AppButton('#container', '출력', 'openReport', { icon: 'print', style: 'outline' });
 *
 * HTML 문자열 반환:
 *    AppButton.html('삭제', 'deleteItem', { icon: 'delete', style: 'danger' });
 *
 * 옵션 (프리셋):
 *   icon    - 아이콘 이름 (print, plus, edit, delete, copy, download, search, refresh, back, power)
 *   style   - 버튼 스타일 (primary, outline, save, cancel, delete, danger, success, teal)  기본: outline
 *   size    - 버튼 크기 (sm, md)   기본: md
 *   href    - 링크 URL (지정 시 <a> 태그로 생성, 미지정 시 <button> 태그)
 *
 * 옵션 (커스텀 — 지정 시 프리셋 위에 덮어씀):
 *   bg      - 배경색 (예: '#6366f1')  → 미지정 시 프리셋 색상
 *   color   - 글자색 (예: '#fff')     → bg 지정 시 기본 '#fff'
 *   border  - 테두리 (예: '1px solid #6366f1')  → bg 지정 시 기본 배경색
 *   padding - 크기   (예: '8px 16px') → 미지정 시 size 프리셋
 *
 * ============================================================
 * 3. JS — 아이콘 버튼 (AppButton.icon / AppButton.iconHtml)
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
 *   color  - blue, yellow, red, green, purple   기본: 아이콘별 자동
 *   style  - 'ghost' 지정 시 배경 없는 인라인 아이콘 (테이블 셀 내 복사 등)
 *   size   - 'sm' 지정 시 24x24 (기본: 32x32)
 *   bg     - 배경색 (예: '#6b7280') → solid 스타일 (진한 배경 + 흰색 아이콘)
 *   title  - 툴팁 텍스트
 *   href   - 링크 URL (지정 시 <a> 태그로 생성)
 *
 * ============================================================
 * 4. JS — 아이콘 버튼 로딩 상태 관리
 * ============================================================
 *
 * 로딩 시작 (스피너 교체 + disabled):
 *    AppButton.setLoading(btn)
 *    AppButton.setLoading('button[data-retailer="amazon"]')
 *
 * 로딩 해제 (아이콘 복구 + enabled):
 *    AppButton.clearLoading(btn, 'camera')
 *    AppButton.clearLoading(btn, 'check', { disabled: true, bg: 'transparent', color: '#10b981' })
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
        power: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>',
        document: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>',
        check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>',
        minus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        spinner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: icon-spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="30" stroke-dashoffset="10"/></svg>'
    };

    // 텍스트 버튼 HTML
    function buildHtml(label, fnName, opts) {
        opts = opts || {};
        var style = opts.style || 'outline';
        var size = opts.size || 'md';
        var iconHtml = opts.icon && ICONS[opts.icon] ? ICONS[opts.icon] : '';
        var cls = 'app-btn app-btn-' + size + ' app-btn-' + style;
        var content = (iconHtml ? iconHtml + ' ' : '') + label;

        // 커스텀 인라인 스타일 조합
        var inlineStyles = [];
        if (opts.bg)      inlineStyles.push('background:' + opts.bg);
        if (opts.color)   inlineStyles.push('color:' + opts.color);
        if (opts.border)  inlineStyles.push('border:' + opts.border);
        if (opts.padding) inlineStyles.push('padding:' + opts.padding);
        if (opts.radius)   inlineStyles.push('border-radius:' + opts.radius);
        if (opts.fontSize) inlineStyles.push('font-size:' + opts.fontSize);
        if (opts.bg && !opts.color)  inlineStyles.push('color:#fff');
        if (opts.bg && !opts.border) inlineStyles.push('border-color:' + opts.bg);
        var styleAttr = inlineStyles.length ? ' style="' + inlineStyles.join(';') + '"' : '';

        // hover (bg 커스텀 시 opacity)
        var hoverAttr = opts.bg ? ' onmouseenter="this.style.opacity=\'0.85\'" onmouseleave="this.style.opacity=\'\'"' : '';

        if (opts.href) {
            return '<a href="' + opts.href + '" class="' + cls + '"' + styleAttr + hoverAttr + '>' + content + '</a>';
        }

        var onclick = fnName ? ' onclick="' + fnName + (fnName.indexOf('(') >= 0 ? '' : '()') + '"' : '';
        var id = opts.id ? ' id="' + opts.id + '"' : '';
        var disabled = opts.disabled ? ' disabled' : '';
        return '<button class="' + cls + '"' + id + styleAttr + hoverAttr + onclick + disabled + '>' + content + '</button>';
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
    //   style:    'ghost' — 배경 없는 인라인 아이콘 (테이블 셀 내 복사 등)
    //   size:     'sm'    — 24x24 (기본: 32x32),  숫자 지정 시 커스텀 (예: 28 → 28x28)
    //   bg:       '#6b7280' — 진한 배경 + 흰색 아이콘 (solid)
    //   disabled: true    — 비활성화
    //   cls:      'my-cls' — 추가 클래스 (셀렉터용)
    //   id:       'myBtn'  — id 속성
    //   data:     { retailer: 'amazon' } — data-* 속성
    function buildIconHtml(iconName, fnExpr, opts) {
        opts = opts || {};
        var iconHtml = ICONS[iconName] || iconName;
        var title = opts.title ? ' title="' + opts.title + '"' : '';
        var onclick = fnExpr ? ' onclick="' + fnExpr + '"' : '';
        var disabled = opts.disabled ? ' disabled' : '';
        var id = opts.id ? ' id="' + opts.id + '"' : '';

        // data-* 속성
        var dataAttrs = '';
        if (opts.data) {
            for (var key in opts.data) {
                dataAttrs += ' data-' + key + '="' + opts.data[key] + '"';
            }
        }

        if (opts.style === 'ghost') {
            var cls = 'app-icon-btn-ghost';
            if (opts.cls) cls += ' ' + opts.cls;
            if (opts.href) {
                return '<a href="' + opts.href + '" class="' + cls + '"' + title + id + dataAttrs + '>' + iconHtml + '</a>';
            }
            return '<button class="' + cls + '"' + onclick + title + disabled + id + dataAttrs + '>' + iconHtml + '</button>';
        }

        var cls = 'app-icon-btn';
        if (opts.size === 'sm') cls += ' app-icon-btn-sm';

        // bg 옵션: solid 스타일 (진한 배경 + 흰색 아이콘)
        //   bg + color 동시 지정 시 → 배경+아이콘 색상 모두 커스텀
        var inlineStyles = [];
        if (typeof opts.size === 'number') {
            inlineStyles.push('width:' + opts.size + 'px');
            inlineStyles.push('height:' + opts.size + 'px');
        }
        if (opts.bg) {
            cls += ' app-icon-btn-solid';
            inlineStyles.push('background:' + opts.bg);
            if (opts.color) inlineStyles.push('color:' + opts.color);
        } else {
            var color = opts.color || ICON_COLORS[iconName] || 'blue';
            cls += ' app-icon-btn-' + color;
        }
        var styleAttr = inlineStyles.length ? ' style="' + inlineStyles.join(';') + '"' : '';
        if (opts.cls) cls += ' ' + opts.cls;

        if (opts.href) {
            return '<a href="' + opts.href + '" class="' + cls + '"' + styleAttr + title + id + dataAttrs + '>' + iconHtml + '</a>';
        }

        return '<button class="' + cls + '"' + styleAttr + onclick + title + disabled + id + dataAttrs + '>' + iconHtml + '</button>';
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

    // 아이콘 SVG 접근 (외부에서 ICONS 참조용)
    appButton.getIcon = function(name) { return ICONS[name] || ''; };

    // 아이콘 버튼 로딩 상태 설정
    //   btn: DOM 요소 또는 selector
    //   AppButton.setLoading(btn)          — 스피너로 교체 + disabled
    //   AppButton.clearLoading(btn, icon)  — 원래 아이콘 복구 + enabled
    //   AppButton.clearLoading(btn, icon, { disabled: true, bg: '...', color: '...' })
    appButton.setLoading = function(btn) {
        var el = typeof btn === 'string' ? document.querySelector(btn) : btn;
        if (!el) return;
        el._prevIcon = el.innerHTML;
        el.innerHTML = ICONS.spinner;
        el.disabled = true;
    };

    appButton.clearLoading = function(btn, iconName, opts) {
        var el = typeof btn === 'string' ? document.querySelector(btn) : btn;
        if (!el) return;
        opts = opts || {};
        el.innerHTML = iconName ? (ICONS[iconName] || iconName) : (el._prevIcon || '');
        el.disabled = !!opts.disabled;
        if (opts.bg) el.style.background = opts.bg;
        if (opts.color) el.style.color = opts.color;
        if (opts.title) el.title = opts.title;
    };

    return appButton;
})();
