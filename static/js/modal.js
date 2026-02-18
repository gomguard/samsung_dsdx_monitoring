/**
 * AppModal — 공통 팝업 컴포넌트
 *
 * 사용법:
 *   // 생성 (페이지 초기화 시 1회)
 *   AppModal.create('detail', { style: 'wide' });
 *
 *   // 열기/닫기
 *   AppModal.open('detail');
 *   AppModal.close('detail');
 *
 *   // 제목/바디 설정
 *   AppModal.setTitle('detail', '제목 텍스트');
 *   AppModal.setBody('detail', '<p>HTML 내용</p>');
 *
 *   // 제목/바디 읽기
 *   const title = AppModal.getTitle('detail');
 *   const bodyEl = AppModal.getBody('detail');  // DOM element 반환
 *
 * 스타일 옵션: 'wide' | 'form' | 'compact'
 */
const AppModal = (() => {
    const instances = {};

    function create(id, options) {
        if (instances[id]) return instances[id];

        const style = (options && options.style) || 'wide';

        const overlay = document.createElement('div');
        overlay.className = 'app-modal app-modal--' + style;

        overlay.innerHTML =
            '<div class="app-modal__content">' +
                '<div class="app-modal__header">' +
                    '<h3 class="app-modal__title"></h3>' +
                    '<button class="app-modal__close">&times;</button>' +
                '</div>' +
                '<div class="app-modal__body"></div>' +
            '</div>';

        // 오버레이 클릭 시 닫기
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) close(id);
        });

        // X 버튼 클릭 시 닫기
        overlay.querySelector('.app-modal__close').addEventListener('click', function () {
            close(id);
        });

        document.body.appendChild(overlay);
        instances[id] = { el: overlay, style: style };
        return instances[id];
    }

    function open(id) {
        var inst = instances[id];
        if (inst) inst.el.classList.add('show');
    }

    function close(id) {
        var inst = instances[id];
        if (inst) inst.el.classList.remove('show');
    }

    function setTitle(id, text) {
        var inst = instances[id];
        if (inst) inst.el.querySelector('.app-modal__title').textContent = text;
    }

    function getTitle(id) {
        var inst = instances[id];
        return inst ? inst.el.querySelector('.app-modal__title').textContent : '';
    }

    function setBody(id, html) {
        var inst = instances[id];
        if (inst) inst.el.querySelector('.app-modal__body').innerHTML = html;
    }

    function getBody(id) {
        var inst = instances[id];
        return inst ? inst.el.querySelector('.app-modal__body') : null;
    }

    return { create: create, open: open, close: close, setTitle: setTitle, getTitle: getTitle, setBody: setBody, getBody: getBody };
})();
