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
 * bar.reset();                // 모든 컨트롤을 default 값으로 초기화
 *
 * 조회 / 해제 버튼 (onSearch, onReset 옵션):
 *   onSearch 지정 시 "조회" 버튼 자동 추가 (searchLabel로 라벨 변경 가능)
 *   onReset 지정 시 "해제" 버튼 자동 추가 (resetLabel로 라벨 변경 가능)
 *   해제 클릭 시 모든 컨트롤을 default로 복원 후 onReset 콜백 호출
 *
 *   new FilterBar('#el', {
 *       controls: [
 *           { type: 'select', key: 'status', default: 'active', options: [...] },
 *       ],
 *       onSearch: () => applyFilter(),    // "조회" 버튼 자동 생성
 *       onReset: () => applyFilter(),     // "해제" 버튼 자동 생성
 *   }).render();
 *
 * ============================================================
 * 컨트롤 타입
 * ============================================================
 *
 * date   : { type: 'date', key, label, value, default, showWeekday: true }
 * button : { type: 'button', label, style, size, bg, color, border, padding, onClick }
 * select : { type: 'select', key, label, default, options: [{value, label}], onChange }
 * input  : { type: 'input', key, label, placeholder, value, default, onEnter }
 * toggle : { type: 'toggle', options: ['A','B'], default: 0, onClick: (label, index) => {} }
 * custom : { type: 'custom', html: '<div>...</div>' }
 *
 * ============================================================
 * 컬럼 선택 (columnSelector 옵션)
 * ============================================================
 *
 * new FilterBar('#el', {
 *     controls: [...],
 *     columnSelector: {
 *         columns: [{key, label}, ...],          // 전체 컬럼 목록
 *         fixed: ['id'],                          // 체크 해제/이동 불가
 *         defaultVisible: ['id', 'item', ...],    // 기본 표시 (null → 전체)
 *         onUpdate: function(visibleColumns) {}    // 변경 콜백
 *     }
 * }).render();
 *
 * bar.getVisibleColumns();   // 표시 순서대로 visible 컬럼 [{key, label}, ...]
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
        this._defaults = {};
        this.barEl = null;
        this._colState = null;
        this._colCloseHandler = null;
        this._colDragItem = null;

        if (options.columnSelector) {
            this._initColState(options.columnSelector);
        }
    }

    render() {
        const bar = document.createElement('div');
        bar.className = 'fb';
        if (this.options.sticky) bar.classList.add('fb-sticky');
        if (this.options.plain) bar.classList.add('fb-plain');
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

        // onSearch 지정 시 "조회" 버튼 자동 추가
        if (this.options.onSearch) {
            left.appendChild(this._createButton({
                label: this.options.searchLabel || '조회',
                style: 'primary', size: 'fb',
                onClick: this.options.onSearch
            }));
        }

        // onReset 지정 시 "해제" 버튼 자동 추가
        if (this.options.onReset) {
            var self = this;
            left.appendChild(this._createButton({
                label: this.options.resetLabel || '해제',
                style: 'cancel', size: 'fb',
                onClick: function() { self.reset(); }
            }));
        }

        bar.appendChild(left);

        // 우측 컨트롤
        var hasRight = (this.options.right && this.options.right.length > 0) || this._colState;
        if (hasRight) {
            const right = document.createElement('div');
            right.className = 'fb-right';
            if (this.options.gap) right.style.gap = this.options.gap + 'px';
            // columnSelector 옵션이 있으면 '컬럼 선택' 버튼 먼저 추가
            if (this._colState) {
                var self = this;
                var colBtn = this._createButton({
                    label: '컬럼 선택', style: 'outline', size: 'fb',
                    onClick: function() { self._toggleColDropdown(colBtn); }
                });
                right.appendChild(colBtn);
            }
            (this.options.right || []).forEach(ctrl => {
                right.appendChild(this._createControl(ctrl));
            });
            bar.appendChild(right);
        }

        this.container.innerHTML = '';
        this.container.appendChild(bar);
        this.barEl = bar;

        // default 값이 지정된 컨트롤에 초기값 적용
        for (var key in this._defaults) {
            if (this._defaults[key] && this.elements[key]) {
                this.elements[key].value = this._defaults[key];
            }
        }

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

        if (ctrl.key) {
            this.elements[ctrl.key] = input;
            this._defaults[ctrl.key] = ctrl.default !== undefined ? ctrl.default : (ctrl.value || '');
        }

        // 요일 표시 옵션
        if (ctrl.showWeekday) {
            const weekdayEl = document.createElement('span');
            weekdayEl.className = 'fb-weekday';
            wrapper.appendChild(weekdayEl);

            const weekdays = ['일', '월', '화', '수', '목', '금', '토'];
            const self = this;
            function updateWeekday() {
                var val = input.value;
                if (!val) { weekdayEl.textContent = ''; return; }
                var d = new Date(val + 'T00:00:00');
                var day = d.getDay();
                weekdayEl.textContent = '(' + weekdays[day] + ')';
                weekdayEl.className = 'fb-weekday' + (day === 0 || day === 6 ? ' fb-weekday-weekend' : '');
            }
            input.addEventListener('change', updateWeekday);
            this._weekdayUpdater = updateWeekday;
            updateWeekday();
        }

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

        if (ctrl.key) {
            this.elements[ctrl.key] = input;
            this._defaults[ctrl.key] = ctrl.default !== undefined ? ctrl.default : (ctrl.value || '');
        }

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
        if (ctrl.width && ctrl.width !== 'auto') {
            select.style.width = typeof ctrl.width === 'number' ? ctrl.width + 'px' : ctrl.width;
        }
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

        // autoWidth: 선택된 옵션 텍스트에 맞춰 너비 동적 조정
        if (ctrl.width === 'auto') {
            var measure = document.createElement('span');
            measure.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font-size:14px;';
            document.body.appendChild(measure);
            function fitSelect() {
                var text = select.options[select.selectedIndex];
                measure.textContent = text ? text.textContent : '';
                select.style.width = (measure.offsetWidth + 50) + 'px';
            }
            select.addEventListener('change', fitSelect);
            fitSelect();
        }

        if (ctrl.key) {
            this.elements[ctrl.key] = select;
            var defaultVal = ctrl.default !== undefined ? ctrl.default
                : (ctrl.options && ctrl.options.length > 0 ? ctrl.options[0].value : '');
            this._defaults[ctrl.key] = defaultVal;
        }

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
        input.dispatchEvent(new Event('change'));
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
        input.dispatchEvent(new Event('change'));
        return this;
    }

    reset() {
        for (var key in this._defaults) {
            var el = this.elements[key];
            if (el) el.value = this._defaults[key];
        }
        if (this.options.onReset) this.options.onReset();
        return this;
    }

    // ── 컬럼 선택 ─────────────────────────────────

    _initColState(opt) {
        var all = opt.columns || [];
        var fixedKeys = opt.fixed || [];
        var order = all.map(function(c) { return c.key; });
        var hidden = new Set();

        if (opt.defaultVisible) {
            var dvSet = {};
            opt.defaultVisible.forEach(function(k) { dvSet[k] = true; });
            all.forEach(function(c) {
                if (!dvSet[c.key] && fixedKeys.indexOf(c.key) < 0) {
                    hidden.add(c.key);
                }
            });
        }

        this._colState = {
            all: all,
            fixed: fixedKeys,
            order: order,
            hidden: hidden,
            onUpdate: opt.onUpdate || null
        };
    }

    getVisibleColumns() {
        if (!this._colState) return [];
        var s = this._colState;
        var colMap = {};
        s.all.forEach(function(c) { colMap[c.key] = c; });
        return s.order
            .filter(function(k) { return !s.hidden.has(k); })
            .map(function(k) { return colMap[k]; })
            .filter(Boolean);
    }

    /**
     * 외부에서 컬럼 순서 변경 (테이블 헤더 드래그 후 동기화용)
     * @param {string[]} keyOrder - 새 순서의 key 배열
     */
    reorderColumns(keyOrder) {
        if (!this._colState) return;
        var s = this._colState;
        var existing = new Set(s.order);
        // keyOrder에 있는 것만 순서 적용, 나머지(fixed 등)는 원래 위치 유지
        var newOrder = [];
        var fixedSet = new Set(s.fixed || []);
        // fixed 컬럼은 원래 순서대로 앞에
        s.order.forEach(function(k) {
            if (fixedSet.has(k)) newOrder.push(k);
        });
        // 나머지는 keyOrder 순서대로
        keyOrder.forEach(function(k) {
            if (existing.has(k) && !fixedSet.has(k)) newOrder.push(k);
        });
        // keyOrder에 없지만 원래 있던 컬럼 (혹시 누락 방지)
        s.order.forEach(function(k) {
            if (newOrder.indexOf(k) === -1) newOrder.push(k);
        });
        s.order = newOrder;
    }

    _toggleColDropdown(anchorBtn) {
        var dropdownId = 'fb-col-dropdown';
        var existing = document.getElementById(dropdownId);
        if (existing) {
            existing.remove();
            this._removeColCloseHandler();
            return;
        }

        var self = this;
        var s = this._colState;
        var colMap = {};
        s.all.forEach(function(c) { colMap[c.key] = c; });

        var dropdown = document.createElement('div');
        dropdown.id = dropdownId;
        dropdown.className = 'fb-col-dropdown';
        dropdown.addEventListener('click', function(e) { e.stopPropagation(); });

        // 전체 선택/해제
        var actions = document.createElement('div');
        actions.className = 'fb-col-actions';
        var btnAll = document.createElement('button');
        btnAll.className = 'app-btn app-btn-sm app-btn-outline';
        btnAll.textContent = '전체 선택';
        btnAll.addEventListener('click', function() { self._setAllCols(true); });
        var btnNone = document.createElement('button');
        btnNone.className = 'app-btn app-btn-sm app-btn-outline';
        btnNone.textContent = '전체 해제';
        btnNone.addEventListener('click', function() { self._setAllCols(false); });
        actions.appendChild(btnAll);
        actions.appendChild(btnNone);
        dropdown.appendChild(actions);

        // 컬럼 목록
        var list = document.createElement('div');
        list.className = 'fb-col-list';

        s.order.forEach(function(key) {
            var col = colMap[key];
            if (!col) return;
            var isFixed = s.fixed.indexOf(key) >= 0;

            var item = document.createElement('div');
            item.className = 'fb-col-item' + (isFixed ? ' col-fixed' : '');
            item.dataset.colKey = key;

            // 드래그 핸들
            var handle = document.createElement('span');
            handle.className = 'drag-handle';
            handle.textContent = '\u2807';
            if (!isFixed) {
                handle.draggable = true;
            }
            item.appendChild(handle);

            // 체크박스
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !s.hidden.has(key);
            cb.disabled = isFixed;
            cb.addEventListener('change', function() {
                if (this.checked) {
                    s.hidden.delete(key);
                } else {
                    s.hidden.add(key);
                }
                self._fireColUpdate();
            });
            item.appendChild(cb);

            // 라벨
            var label = document.createElement('span');
            label.textContent = col.label;
            item.appendChild(label);

            list.appendChild(item);
        });

        dropdown.appendChild(list);

        // 앵커에 붙이기
        var anchor = anchorBtn.parentElement || anchorBtn;
        anchor.style.position = 'relative';
        anchor.appendChild(dropdown);

        // 드래그 초기화
        this._initColDrag(list);

        // 외부 클릭 시 닫기
        this._colCloseHandler = function(e) {
            var dd = document.getElementById(dropdownId);
            if (dd && !dd.contains(e.target) && !anchorBtn.contains(e.target)) {
                dd.remove();
                self._removeColCloseHandler();
            }
        };
        setTimeout(function() { document.addEventListener('click', self._colCloseHandler); }, 0);
    }

    _setAllCols(visible) {
        var s = this._colState;
        s.hidden.clear();
        if (!visible) {
            s.order.forEach(function(key) {
                if (s.fixed.indexOf(key) < 0) s.hidden.add(key);
            });
        }
        var dd = document.getElementById('fb-col-dropdown');
        if (dd) {
            dd.querySelectorAll('input[type="checkbox"]').forEach(function(cb) {
                if (!cb.disabled) cb.checked = visible;
            });
        }
        this._fireColUpdate();
    }

    _initColDrag(listEl) {
        var self = this;
        var items = listEl.querySelectorAll('.fb-col-item:not(.col-fixed)');

        items.forEach(function(item) {
            var handle = item.querySelector('.drag-handle');
            if (!handle || !handle.draggable) return;

            handle.addEventListener('dragstart', function(e) {
                self._colDragItem = item;
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            });

            handle.addEventListener('dragend', function() {
                item.classList.remove('dragging');
                listEl.querySelectorAll('.drag-over').forEach(function(el) { el.classList.remove('drag-over'); });
                self._colDragItem = null;
            });

            item.addEventListener('dragover', function(e) {
                e.preventDefault();
                if (self._colDragItem && self._colDragItem !== item && !item.classList.contains('col-fixed')) {
                    listEl.querySelectorAll('.drag-over').forEach(function(el) { el.classList.remove('drag-over'); });
                    item.classList.add('drag-over');
                }
            });

            item.addEventListener('dragleave', function() {
                item.classList.remove('drag-over');
            });

            item.addEventListener('drop', function(e) {
                e.preventDefault();
                item.classList.remove('drag-over');
                if (!self._colDragItem || self._colDragItem === item) return;
                var fromKey = self._colDragItem.dataset.colKey;
                var toKey = item.dataset.colKey;
                self._reorderCol(fromKey, toKey);
            });
        });
    }

    _reorderCol(fromKey, toKey) {
        var order = this._colState.order;
        var fromPos = order.indexOf(fromKey);
        var toPos = order.indexOf(toKey);
        if (fromPos === -1 || toPos === -1) return;

        order.splice(fromPos, 1);
        toPos = order.indexOf(toKey);
        order.splice(toPos, 0, fromKey);

        // 드롭다운 닫기
        var dd = document.getElementById('fb-col-dropdown');
        if (dd) {
            dd.remove();
            this._removeColCloseHandler();
        }
        this._fireColUpdate();

        // 드롭다운 다시 열기
        var colBtn = this.barEl ? this.barEl.querySelector('.fb-right .app-btn:last-child') : null;
        if (colBtn) this._toggleColDropdown(colBtn);
    }

    _fireColUpdate() {
        if (this._colState && this._colState.onUpdate) {
            this._colState.onUpdate(this.getVisibleColumns());
        }
    }

    _removeColCloseHandler() {
        if (this._colCloseHandler) {
            document.removeEventListener('click', this._colCloseHandler);
            this._colCloseHandler = null;
        }
    }
}
