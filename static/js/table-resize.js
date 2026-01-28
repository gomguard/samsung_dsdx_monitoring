/**
 * 테이블 열 크기 조정 공통 모듈
 *
 * 사용법:
 *   enableColumnResize(document.querySelector('.my-table'));
 *   또는
 *   enableColumnResize('.my-table');
 */
function enableColumnResize(tableOrSelector) {
    const table = typeof tableOrSelector === 'string'
        ? document.querySelector(tableOrSelector)
        : tableOrSelector;

    if (!table || !table.querySelector('thead')) return;

    const thead = table.querySelector('thead');
    const ths = thead.querySelectorAll('th');

    ths.forEach(th => {
        // 리사이즈 핸들 생성
        const handle = document.createElement('div');
        handle.className = 'col-resize-handle';
        th.style.position = 'relative';
        th.appendChild(handle);

        let startX, startWidth, thEl;

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            e.stopPropagation();
            thEl = th;
            startX = e.pageX;
            startWidth = th.offsetWidth;

            // 드래그 중 시각 표시
            handle.classList.add('active');

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            const diff = e.pageX - startX;
            const newWidth = Math.max(40, startWidth + diff);
            thEl.style.width = newWidth + 'px';
            thEl.style.minWidth = newWidth + 'px';
        }

        function onMouseUp() {
            handle.classList.remove('active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
    });
}

// CSS 주입 (한 번만)
(function () {
    if (document.getElementById('col-resize-style')) return;
    const style = document.createElement('style');
    style.id = 'col-resize-style';
    style.textContent = `
        .col-resize-handle {
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 5px;
            cursor: col-resize;
            user-select: none;
            z-index: 1;
        }
        .col-resize-handle:hover,
        .col-resize-handle.active {
            background: rgba(139, 92, 246, 0.3);
        }
    `;
    document.head.appendChild(style);
})();
