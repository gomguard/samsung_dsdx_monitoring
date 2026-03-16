/**
 * DS Layer 1 — index 엔트리포인트
 * FilterBar 초기화 + DOMContentLoaded + 탭 전환 + ESC 핸들러
 *
 * 로드 순서: collection.js → fileserver-tab.js → detail-modal.js → batch-modal.js → index.js
 * 템플릿에서 window.DS_L1_CONFIG = { isStaff: boolean } 전달 필요
 */

// ── FilterBar 초기화 ──
const collectionControls = [
    { type: 'date', key: 'targetDate', label: '조회 날짜' },
    { type: 'button', label: '조회', style: 'primary', onClick: () => loadData() },
    { type: 'button', label: '전날', style: 'outline', onClick: () => setPrevDay() },
    { type: 'button', label: '다음날', style: 'outline', onClick: () => setNextDay() },
];

if (DS_L1_CONFIG.isStaff) {
    collectionControls.push(
        { type: 'button', label: '배치관리', bg: '#6366f1', onClick: () => openBatchModal() }
    );
}

const collectionBar = new FilterBar('#collectionFilterBar', {
    sticky: true,
    controls: collectionControls,
    right: [
        { type: 'toggle', options: ['최종', '전체'], onClick: (label, index) => {
            currentBatchView = index === 0 ? 'final' : 'all';
            loadData();
        }}
    ]
}).render();

const fileserverBar = new FilterBar('#fileserverFilterBar', {
    sticky: true,
    controls: [
        { type: 'date', key: 'fileserverDate', label: '조회 날짜' },
        { type: 'button', label: '조회', style: 'primary', onClick: () => loadFileserverData() },
        { type: 'button', label: '전날', style: 'outline', onClick: () => setPrevDayFileserver() },
        { type: 'button', label: '다음날', style: 'outline', onClick: () => setNextDayFileserver() },
    ],
}).render();

// ── 페이지 초기화 ──
document.addEventListener('DOMContentLoaded', function() {
    const initialDate = getPersistedDate();
    document.getElementById('targetDate').value = initialDate;
    document.getElementById('fileserverDate').value = initialDate;

    loadData();
});

// ── 탭 전환 ──
function setMainTab(tab) {
    currentMainTab = tab;
    document.getElementById('tabCollection').classList.toggle('active', tab === 'collection');
    document.getElementById('tabFileserver').classList.toggle('active', tab === 'fileserver');
    document.getElementById('collectionTabContent').classList.toggle('hidden', tab !== 'collection');
    document.getElementById('fileserverTabContent').classList.toggle('hidden', tab !== 'fileserver');

    if (tab === 'fileserver' && !fileserverData) {
        loadFileserverData();
    }
}

// ── ESC 키로 모달 닫기 ──
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
        closeBatchModal();
    }
});
