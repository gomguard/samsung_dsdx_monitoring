/**
 * Layer 4 도구 모음
 */

(function() {
    'use strict';

    var REVIEW_COUNT = 20;
    var focusHandlers = {};

    // ── 리뷰 변환 ────────────────────────────────
    focusHandlers['리뷰 변환'] = function() {
        document.getElementById('tools-review-converter').style.display = '';

        // 입력란 20개 생성
        var container = document.getElementById('review-inputs');
        var html = '';
        for (var i = 1; i <= REVIEW_COUNT; i++) {
            html += '<div class="review-row" data-idx="' + i + '" draggable="true">'
                + '<span class="review-drag-handle" title="드래그하여 이동">⠿</span>'
                + '<span class="review-label">review' + i + '</span>'
                + '<textarea class="review-input" id="review-input-' + i + '" rows="2" placeholder="리뷰 ' + i + ' 입력..."></textarea>'
                + '</div>';
        }
        container.innerHTML = html;

        // 드래그 앤 드롭
        var dragIdx = null;
        container.addEventListener('dragstart', function(e) {
            var row = e.target.closest('.review-row');
            if (!row) return;
            dragIdx = parseInt(row.dataset.idx);
            row.classList.add('review-dragging');
            e.dataTransfer.effectAllowed = 'move';
        });
        container.addEventListener('dragend', function(e) {
            var row = e.target.closest('.review-row');
            if (row) row.classList.remove('review-dragging');
            dragIdx = null;
            container.querySelectorAll('.review-row').forEach(function(r) { r.classList.remove('review-drag-over'); });
        });
        container.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            var row = e.target.closest('.review-row');
            container.querySelectorAll('.review-row').forEach(function(r) { r.classList.remove('review-drag-over'); });
            if (row && parseInt(row.dataset.idx) !== dragIdx) row.classList.add('review-drag-over');
        });
        container.addEventListener('drop', function(e) {
            e.preventDefault();
            var row = e.target.closest('.review-row');
            if (!row || dragIdx === null) return;
            var dropIdx = parseInt(row.dataset.idx);
            if (dropIdx === dragIdx) return;

            var values = [];
            for (var i = 1; i <= REVIEW_COUNT; i++) {
                values.push(document.getElementById('review-input-' + i).value);
            }
            var removed = values.splice(dragIdx - 1, 1)[0];
            values.splice(dropIdx - 1, 0, removed);
            for (var i = 0; i < REVIEW_COUNT; i++) {
                document.getElementById('review-input-' + (i + 1)).value = values[i];
            }
            container.querySelectorAll('.review-row').forEach(function(r) { r.classList.remove('review-drag-over'); });
        });

        var outputEl = document.getElementById('review-output');
        var outputSection = document.getElementById('review-output-section');

        document.getElementById('review-convert-btn').onclick = function() {
            // 빈 칸 검증: 연속으로 입력되어야 함 (중간에 빈 칸 불가)
            var lastFilled = 0;
            for (var i = REVIEW_COUNT; i >= 1; i--) {
                if (document.getElementById('review-input-' + i).value.trim()) { lastFilled = i; break; }
            }
            if (lastFilled === 0) return;

            var gap = 0;
            for (var i = 1; i <= lastFilled; i++) {
                if (!document.getElementById('review-input-' + i).value.trim()) { gap = i; break; }
            }
            if (gap) {
                showToast('review' + gap + '이(가) 비어 있습니다. 중간에 빈 리뷰 없이 연속으로 입력해주세요.', 'error');
                document.getElementById('review-input-' + gap).focus();
                return;
            }

            var parts = [];
            for (var i = 1; i <= lastFilled; i++) {
                var text = document.getElementById('review-input-' + i).value.trim();
                text = text.replace(/[\r\n\t]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
                parts.push('review' + i + ' - ' + text);
            }

            outputEl.value = parts.join(' ||| ');
            outputSection.style.display = '';
        };

        document.getElementById('review-clear-btn').onclick = function() {
            for (var i = 1; i <= REVIEW_COUNT; i++) {
                var el = document.getElementById('review-input-' + i);
                if (el) el.value = '';
            }
            outputEl.value = '';
            outputSection.style.display = 'none';
            // 역변환 초기화
            var reverseInput = document.getElementById('review-reverse-input');
            if (reverseInput) reverseInput.value = '';
            var reverseBody = document.getElementById('review-reverse-body');
            var reverseArrow = document.getElementById('review-reverse-arrow');
            if (reverseBody) { reverseBody.style.display = 'none'; }
            if (reverseArrow) { reverseArrow.style.transform = ''; }
        };

        document.getElementById('review-copy-btn').onclick = function() {
            var text = outputEl.value;
            if (!text) return;
            var btn = this;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function() {
                    btn.textContent = '복사됨';
                    setTimeout(function() { btn.textContent = '복사'; }, 1500);
                });
            } else {
                outputEl.select();
                document.execCommand('copy');
                btn.textContent = '복사됨';
                setTimeout(function() { btn.textContent = '복사'; }, 1500);
            }
        };

        // 역변환 토글
        document.getElementById('review-reverse-toggle').onclick = function() {
            var body = document.getElementById('review-reverse-body');
            var arrow = document.getElementById('review-reverse-arrow');
            var open = body.style.display === 'none';
            body.style.display = open ? '' : 'none';
            arrow.style.transform = open ? 'rotate(90deg)' : '';
        };

        // 역변환
        document.getElementById('review-reverse-btn').onclick = function() {
            var raw = (document.getElementById('review-reverse-input').value || '').trim();
            if (!raw) return;

            var segments = raw.split('|||');
            // 초기화
            for (var i = 1; i <= REVIEW_COUNT; i++) {
                document.getElementById('review-input-' + i).value = '';
            }

            var filled = 0;
            for (var i = 0; i < segments.length; i++) {
                var seg = segments[i].trim();
                if (!seg) continue;
                // "review1 - ..." 또는 "review 1 - ..." 패턴에서 텍스트만 추출
                var text = seg.replace(/^review\s*\d+\s*-\s*/i, '').trim();
                if (!text) continue;
                filled++;
                if (filled > REVIEW_COUNT) break;
                document.getElementById('review-input-' + filled).value = text;
            }

            if (filled > 0) {
                showToast(filled + '개 리뷰가 입력란에 분배되었습니다.', 'success');
                document.getElementById('review-input-1').scrollIntoView({ behavior: 'smooth' });
            } else {
                showToast('변환할 리뷰를 찾을 수 없습니다.', 'error');
            }
        };
    };

    // ── HTML 파서 ────────────────────────────────
    focusHandlers['HTML 파서'] = function() {
        document.getElementById('tools-html-parser').style.display = '';

        var outputEl = document.getElementById('parser-output');
        var outputSection = document.getElementById('parser-output-section');
        var countEl = document.getElementById('parser-count');

        function copyHandler(btn, textEl) {
            var text = textEl.value;
            if (!text) return;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function() {
                    btn.textContent = '복사됨';
                    setTimeout(function() { btn.textContent = '복사'; }, 1500);
                });
            } else {
                textEl.select();
                document.execCommand('copy');
                btn.textContent = '복사됨';
                setTimeout(function() { btn.textContent = '복사'; }, 1500);
            }
        }

        document.getElementById('parser-run-btn').onclick = function() {
            var xpath = (document.getElementById('parser-xpath').value || '').trim();
            var html = (document.getElementById('parser-html').value || '').trim();

            if (!xpath) { showToast('XPath를 입력해주세요.', 'error'); return; }
            if (!html) { showToast('HTML을 입력해주세요.', 'error'); return; }

            try {
                var parser = new DOMParser();
                var doc = parser.parseFromString(html, 'text/html');

                var result = doc.evaluate(xpath, doc, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                var texts = [];
                for (var i = 0; i < result.snapshotLength; i++) {
                    var node = result.snapshotItem(i);
                    var text = (node.textContent || '').trim();
                    // 줄바꿈, 탭, 연속 공백 → 단일 공백
                    text = text.replace(/[\r\n\t]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
                    if (text) texts.push(text);
                }

                if (texts.length === 0) {
                    showToast('XPath에 매칭되는 요소가 없습니다.', 'warning');
                    outputSection.style.display = 'none';
                    return;
                }

                var parts = texts.map(function(t, i) {
                    return 'review' + (i + 1) + ' - ' + t;
                });

                outputEl.value = parts.join(' ||| ');
                countEl.textContent = '(' + texts.length + '개)';
                outputSection.style.display = '';
                showToast(texts.length + '개 리뷰가 추출되었습니다.', 'success');
            } catch (e) {
                showToast('XPath 오류: ' + e.message, 'error');
            }
        };

        document.getElementById('parser-clear-btn').onclick = function() {
            document.getElementById('parser-xpath').value = '';
            document.getElementById('parser-html').value = '';
            outputEl.value = '';
            countEl.textContent = '';
            outputSection.style.display = 'none';
        };

        document.getElementById('parser-copy-btn').onclick = function() {
            copyHandler(this, outputEl);
        };
    };

    // ── 초기화 ────────────────────────────────
    function getActiveFocus() {
        var params = new URLSearchParams(window.location.search);
        return params.get('focus') || '리뷰 변환';
    }

    L4._sectionInit['tools'] = function() {
        var focus = getActiveFocus();
        var handler = focusHandlers[focus];
        if (handler) handler();
    };

    L4._sectionHandler['tools'] = function() {};

})();
