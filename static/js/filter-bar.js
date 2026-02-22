/**
 * FilterBar — 필터바 공통 컴포넌트
 *
 * CSS: static/css/filter-bar.css
 * 버튼: common.css의 .app-btn 사용 (--page-color 연동)
 *
 * ============================================================
 * 사용법
 * ============================================================
 *
 * const bar = new FilterBar('#container', {
 *     sticky: true,           // 상단 고정 (기본: true)
 *     fit: false,             // true: 콘텐츠 너비만큼, false: 한 줄 전체 (기본: false)
 *     padding: '10px 20px',   // 필터바 내부 여백 (기본: '16px 24px', CSS)
 *     gap: 12,                // 컨트롤 간격 px (기본: 10, CSS)
 *     before: [               // 필터 좌측 독립 영역 (네비게이션 등, 구분선으로 분리)
 *         { type: 'button', label: '뒤로', icon: 'back', bg: '#6b7280', href: '/page/' },
 *     ],
 *     controls: [
 *         { type: 'date', key: 'targetDate', label: '조회 날짜' },
 *         { type: 'button', label: '조회', style: 'primary', onClick: () => loadData() },
 *         { type: 'button', label: '전날', style: 'outline', onClick: () => bar.prevDay() },
 *         { type: 'button', label: '다음날', style: 'outline', onClick: () => bar.nextDay() },
 *     ],
 *     right: [
 *         { type: 'toggle', options: ['최종', '전체'], onClick: (label, index) => {} }
 *     ]
 * }).render();
 *
 * bar.getDate();               // '2026-02-21'
 * bar.setDate('2026-02-20');
 * bar.prevDay();               // 하루 전
 * bar.nextDay();               // 하루 후
 * bar.getValue('key');         // 컨트롤 값 반환
 * bar.setValue('key', 'val');  // 컨트롤 값 설정
 *
 * ============================================================
 * 컨트롤 타입
 * ============================================================
 *
 * date   : { type: 'date', key, label, value }
 * button : { type: 'button', label, style, size, bg, color, border, padding, onClick }
 * select : { type: 'select', key, label, options: [{value, label}], onChange }
 * input  : { type: 'input', key, label, placeholder, value, onEnter }
 * toggle : { type: 'toggle', options: ['A','B'], default: 0, onClick: (label, index) => {} }
 * custom : { type: 'custom', html: '<div>...</div>' }
 *
 * ============================================================
 */

class FilterBar {
    constructor(container, options = {}) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;
        this.options = {
            sticky: true,
            controls: [],
            right: [],
            ...options
        };
        this.elements = {};
        this.barEl = null;
    }

    render() {
        const bar = document.createElement('div');
        bar.className = 'fb';
        if (this.options.sticky) bar.classList.add('fb-sticky');
        if (this.options.fit) bar.classList.add('fb-fit');
        if (this.options.padding) bar.style.padding = this.options.padding;

        // before 영역 (네비게이션 등 필터와 무관한 요소)
        if (this.options.before && this.options.before.length > 0) {
            const before = document.createElement('div');
            before.className = 'fb-before';
            this.options.before.forEach(ctrl => {
                before.appendChild(this._createControl(ctrl));
            });
            bar.appendChild(before);
        }

        // 좌측 컨트롤
        const left = document.createElement('div');
        left.className = 'fb-left';
        if (this.options.gap) left.style.gap = this.options.gap + 'px';
        this.options.controls.forEach(ctrl => {
            left.appendChild(this._createControl(ctrl));
        });
        bar.appendChild(left);

        // 우측 컨트롤
        if (this.options.right && this.options.right.length > 0) {
            const right = document.createElement('div');
            right.className = 'fb-right';
            if (this.options.gap) right.style.gap = this.options.gap + 'px';
            this.options.right.forEach(ctrl => {
                right.appendChild(this._createControl(ctrl));
            });
            bar.appendChild(right);
        }

        this.container.innerHTML = '';
        this.container.appendChild(bar);
        this.barEl = bar;

        return this;
    }

    // ── 컨트롤 생성 ──────────────────────────────

    _createControl(ctrl) {
        var el;
        switch (ctrl.type) {
            case 'date':   el = this._createDate(ctrl);   break;
            case 'button': el = this._createButton(ctrl);  break;
            case 'select': el = this._createSelect(ctrl);  break;
            case 'input':  el = this._createInput(ctrl);  break;
            case 'toggle': el = this._createToggle(ctrl);  break;
            case 'custom': el = this._createCustom(ctrl);  break;
            default:       el = document.createElement('span');
        }
        if (ctrl.ml) el.style.marginLeft = ctrl.ml + 'px';
        return el;
    }

    _createDate(ctrl) {
        const wrapper = document.createElement('div');
        wrapper.className = 'fb-date';

        if (ctrl.label) {
            const label = document.createElement('label');
            label.textContent = ctrl.label;
            wrapper.appendChild(label);
        }

        const input = document.createElement('input');
        input.type = 'date';
        if (ctrl.key) input.id = ctrl.key;
        if (ctrl.value) input.value = ctrl.value;
        if (ctrl.max) input.max = ctrl.max;
        wrapper.appendChild(input);

        if (ctrl.key) this.elements[ctrl.key] = input;

        return wrapper;
    }

    _createInput(ctrl) {
        const wrapper = document.createElement('div');
        wrapper.className = 'fb-input';

        if (ctrl.label) {
            const label = document.createElement('label');
            label.textContent = ctrl.label;
            wrapper.appendChild(label);
        }

        const input = document.createElement('input');
        input.type = 'text';
        if (ctrl.key) input.id = ctrl.key;
        if (ctrl.placeholder) input.placeholder = ctrl.placeholder;
        if (ctrl.value) input.value = ctrl.value;
        if (ctrl.onEnter) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') ctrl.onEnter(input.value);
            });
        }

        wrapper.appendChild(input);
        if (ctrl.key) this.elements[ctrl.key] = input;

        return wrapper;
    }

    _createButton(ctrl) {
        var tag = ctrl.href ? 'a' : 'button';
        const el = document.createElement(tag);
        if (ctrl.href) el.href = ctrl.href;
        if (ctrl.id)   el.id = ctrl.id;

        // .app-btn 공통 클래스 + 프리셋 스타일
        var size = ctrl.size || 'md';
        var style = ctrl.style || 'outline';
        el.className = 'app-btn app-btn-' + size + ' app-btn-' + style;

        // 아이콘 + 라벨
        if (ctrl.icon && typeof AppButton !== 'undefined') {
            el.innerHTML = AppButton.html(ctrl.label, null, { icon: ctrl.icon }).replace(/<[^>]+>([^]*)<\/[^>]+>$/, '$1');
        } else {
            el.textContent = ctrl.label;
        }

        // 커스텀 옵션 (지정 시 프리셋 위에 인라인 스타일로 덮어씀)
        if (ctrl.bg)      el.style.background = ctrl.bg;
        if (ctrl.color)   el.style.color = ctrl.color;
        if (ctrl.border)  el.style.border = ctrl.border;
        if (ctrl.padding) el.style.padding = ctrl.padding;
        if (ctrl.btnWidth) el.style.minWidth = ctrl.btnWidth + 'px';

        // bg 지정 시 기본값: 흰색 글자, 테두리 = 배경색, hover = opacity
        if (ctrl.bg) {
            if (!ctrl.color)  el.style.color = '#fff';
            if (!ctrl.border) el.style.borderColor = ctrl.bg;
            el.addEventListener('mouseenter', function() { el.style.opacity = '0.85'; });
            el.addEventListener('mouseleave', function() { el.style.opacity = ''; });
        }

        if (ctrl.onClick) el.addEventListener('click', ctrl.onClick);

        return el;
    }

    _createSelect(ctrl) {
        const wrapper = document.createElement('div');
        wrapper.className = 'fb-select';

        if (ctrl.label) {
            const label = document.createElement('label');
            label.textContent = ctrl.label;
            wrapper.appendChild(label);
        }

        const select = document.createElement('select');
        if (ctrl.key) select.id = ctrl.key;
        (ctrl.options || []).forEach(opt => {
            const option = document.createElement('option');
            option.value = opt.value;
            option.textContent = opt.label;
            select.appendChild(option);
        });
        if (ctrl.onChange) {
            select.addEventListener('change', () => ctrl.onChange(select.value));
        }
        wrapper.appendChild(select);

        if (ctrl.key) this.elements[ctrl.key] = select;

        return wrapper;
    }

    _createToggle(ctrl) {
        const wrapper = document.createElement('div');
        wrapper.className = 'fb-toggle';
        if (ctrl.gap) wrapper.style.gap = ctrl.gap + 'px';
        const defaultIdx = ctrl.default || 0;
        const size = ctrl.size || 'md';

        function setActive(activeBtn) {
            wrapper.querySelectorAll('button').forEach(b => {
                b.className = 'app-btn app-btn-' + size + ' app-btn-cancel';
            });
            activeBtn.className = 'app-btn app-btn-' + size + ' app-btn-primary';
        }

        (ctrl.options || []).forEach((opt, i) => {
            const btn = document.createElement('button');
            btn.textContent = opt;

            if (i === defaultIdx) {
                btn.className = 'app-btn app-btn-' + size + ' app-btn-primary';
            } else {
                btn.className = 'app-btn app-btn-' + size + ' app-btn-cancel';
            }

            if (ctrl.btnWidth) btn.style.minWidth = ctrl.btnWidth + 'px';

            btn.addEventListener('click', () => {
                setActive(btn);
                if (ctrl.onClick) ctrl.onClick(opt, i);
            });

            wrapper.appendChild(btn);
        });

        return wrapper;
    }

    _createCustom(ctrl) {
        const wrapper = document.createElement('div');
        if (ctrl.html) wrapper.innerHTML = ctrl.html;
        return wrapper.firstElementChild || wrapper;
    }

    // ── 값 접근 ──────────────────────────────────

    getValue(key) {
        const el = this.elements[key];
        return el ? el.value : null;
    }

    setValue(key, val) {
        const el = this.elements[key];
        if (el) el.value = val;
        return this;
    }

    getDate() {
        const input = this.barEl.querySelector('input[type="date"]');
        return input ? input.value : null;
    }

    setDate(val) {
        const input = this.barEl.querySelector('input[type="date"]');
        if (input) input.value = val;
        return this;
    }

    prevDay() {
        const input = this.barEl.querySelector('input[type="date"]');
        if (!input || !input.value) return this;
        const d = new Date(input.value);
        d.setDate(d.getDate() - 1);
        input.value = d.toISOString().slice(0, 10);
        return this;
    }

    nextDay() {
        const input = this.barEl.querySelector('input[type="date"]');
        if (!input || !input.value) return this;
        const d = new Date(input.value);
        d.setDate(d.getDate() + 1);
        const next = d.toISOString().slice(0, 10);
        if (input.max && next > input.max) return this;
        input.value = next;
        return this;
    }
}
