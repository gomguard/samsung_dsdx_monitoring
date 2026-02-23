/**
 * ButtonBar — 버튼바 공통 컴포넌트
 *
 * CSS: static/css/button-bar.css
 * 버튼: buttons.js의 AppButton 사용
 *
 * ============================================================
 * 사용법
 * ============================================================
 *
 * const bar = new ButtonBar('#container', {
 *     align: 'right',         // 정렬 (right | left | center | between) 기본: right
 *     margin: '0 0 12px 0',   // 외부 여백 (기본: '0 0 12px 0')
 *     buttons: [
 *         { id: 'btnPrint', label: '출력', icon: 'print', style: 'outline', onClick: () => openReport() },
 *         { id: 'btnDelete', label: '삭제', icon: 'delete', style: 'danger', onClick: () => deleteItems() },
 *     ]
 * }).render();
 *
 * // between 모드: position으로 좌/우 그룹 분리
 * const bar = new ButtonBar('#container', {
 *     align: 'between',
 *     buttons: [
 *         { id: 'btnLeft', label: '왼쪽', position: 'left', onClick: () => {} },
 *         { id: 'btnRight', label: '오른쪽', position: 'right', onClick: () => {} },
 *     ]
 * }).render();
 *
 * bar.show('btnPrint');       // 특정 버튼 표시
 * bar.hide('btnPrint');       // 특정 버튼 숨김
 * bar.toggle('btnPrint', true/false);  // 토글
 * bar.showBar();              // 바 전체 표시
 * bar.hideBar();              // 바 전체 숨김
 * bar.toggleBar(true/false);  // 바 전체 토글
 * bar.getButton('btnPrint');  // 버튼 DOM 반환
 *
 * ============================================================
 * 버튼 옵션
 * ============================================================
 *
 * id       - 버튼 식별자 (show/hide 제어용)
 * label    - 버튼 텍스트
 * icon     - 아이콘 이름 (buttons.js ICONS 참조: print, edit, delete, copy 등)
 * style    - 버튼 스타일 (outline, primary, save, cancel, delete, danger 등)
 * size     - 버튼 크기 (sm, md) 기본: sm
 * onClick  - 클릭 핸들러
 * href     - 링크 URL (지정 시 <a> 태그)
 * hidden   - true면 초기 숨김
 * position - between 모드 전용: 'left' | 'right' (기본: 'left')
 *
 * ============================================================
 */

class ButtonBar {
    constructor(container, options) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;
        this.options = Object.assign({
            align: 'right',
            margin: '0 0 12px 0',
            buttons: []
        }, options || {});
        this._buttons = {};
    }

    render() {
        if (!this.container) return this;

        var alignCls = 'bb-' + this.options.align;
        var el = document.createElement('div');
        el.className = 'bb ' + alignCls;
        if (this.options.margin) el.style.margin = this.options.margin;
        this._el = el;

        var self = this;
        if (this.options.align === 'between') {
            var leftGroup = document.createElement('div');
            leftGroup.className = 'bb-group';
            var rightGroup = document.createElement('div');
            rightGroup.className = 'bb-group';
            this.options.buttons.forEach(function(cfg) {
                var btn = self._createButton(cfg);
                if (cfg.id) { btn.id = cfg.id; self._buttons[cfg.id] = btn; }
                if (cfg.hidden) btn.style.display = 'none';
                (cfg.position === 'right' ? rightGroup : leftGroup).appendChild(btn);
            });
            el.appendChild(leftGroup);
            el.appendChild(rightGroup);
        } else {
            this.options.buttons.forEach(function(cfg) {
                var btn = self._createButton(cfg);
                if (cfg.id) { btn.id = cfg.id; self._buttons[cfg.id] = btn; }
                if (cfg.hidden) btn.style.display = 'none';
                el.appendChild(btn);
            });
        }

        this.container.appendChild(el);
        return this;
    }

    _createButton(cfg) {
        var style = cfg.style || 'outline';
        var size = cfg.size || 'sm';
        var cls = 'app-btn app-btn-' + size + ' app-btn-' + style;
        var iconHtml = cfg.icon && AppButton.getIcon ? AppButton.getIcon(cfg.icon) : '';
        var content = (iconHtml ? iconHtml + ' ' : '') + (cfg.label || '');

        var tag = cfg.href ? 'a' : 'button';
        var el = document.createElement(tag);
        el.className = cls;
        el.innerHTML = content;
        if (cfg.href) el.href = cfg.href;
        if (cfg.onClick) el.addEventListener('click', cfg.onClick);
        return el;
    }

    show(id) {
        var btn = this._buttons[id];
        if (btn) btn.style.display = '';
        return this;
    }

    hide(id) {
        var btn = this._buttons[id];
        if (btn) btn.style.display = 'none';
        return this;
    }

    toggle(id, visible) {
        var btn = this._buttons[id];
        if (btn) btn.style.display = visible ? '' : 'none';
        return this;
    }

    showBar() {
        if (this._el) this._el.style.display = '';
        return this;
    }

    hideBar() {
        if (this._el) this._el.style.display = 'none';
        return this;
    }

    toggleBar(visible) {
        if (this._el) this._el.style.display = visible ? '' : 'none';
        return this;
    }

    getButton(id) {
        return this._buttons[id] || null;
    }
}
