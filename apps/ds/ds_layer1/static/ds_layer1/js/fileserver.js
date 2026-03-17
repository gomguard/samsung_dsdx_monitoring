/**
 * DS Layer 1 — fileserver 페이지 JS
 * 국가별 파일 탐색기 + backup 이동
 */

(function() {

const API_URL = '/ds/layer1/api/fileserver-browse/';
const MOVE_URL = '/ds/layer1/api/fileserver-move/';
const ICON_FOLDER = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>';
const ICON_FILE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';

// URL 파라미터에서 초기값 읽기
const urlParams = new URLSearchParams(location.search);
const initCountry = urlParams.get('country') || '';
const today = formatLocalDate(new Date());
const _rawDate = urlParams.get('date') || getPersistedDate();
const _isFutureDate = _rawDate > today;
const initDate = _isFutureDate ? today : _rawDate;

let filterBar;
let currentCountry = '';
let currentDateFolder = '';

// ── 뒤로가기 ──
window.goBack = function() {
    if (currentCountry) {
        showCountries();
    } else {
        location.href = '/ds/layer1/';
    }
};

// ── 초기화 ──
async function init() {
    if (initCountry) {
        currentCountry = initCountry;
        showCountryDetail(initCountry, initDate);
    } else {
        showCountries();
    }
    if (_isFutureDate) {
        showToast('오늘 이후 날짜는 조회할 수 없습니다.', 'warning');
    }
}

// ── Level 1: 국가 폴더 목록 (파일 탐색기 스타일) ──
async function showCountries() {
    currentCountry = '';
    updateBackLink();
    updateUrl();

    document.getElementById('filterBar').innerHTML = '';

    const container = document.getElementById('content');
    container.innerHTML = '<div class="status-message"><div class="loading-spinner"></div> 불러오는 중...</div>';

    try {
        const res = await fetch(API_URL);
        const data = await res.json();
        const countries = data.countries || [];

        if (countries.length === 0) {
            container.innerHTML = '<div class="status-message">국가 폴더가 없습니다.</div>';
            return;
        }

        let html = `
            <div class="explorer">
                <div class="explorer-header">
                    <div class="explorer-title">/uploads/</div>
                    <div class="explorer-count">${countries.length}개 폴더</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th class="col-icon"></th>
                            <th class="col-name">파일명</th>
                            <th class="col-type">파일 유형</th>
                            <th class="col-modified">최종 수정</th>
                        </tr>
                    </thead>
                    <tbody>`;

        countries.forEach(c => {
            html += `
                        <tr class="row-folder" onclick="enterCountry('${esc(c.name)}')">
                            <td class="col-icon">${ICON_FOLDER}</td>
                            <td class="col-name">${esc(c.name)}</td>
                            <td class="col-type">파일 폴더</td>
                            <td class="col-modified">${esc(c.modified)}</td>
                        </tr>`;
        });

        html += '</tbody></table></div>';
        container.innerHTML = html;
    } catch (e) {
        console.error('국가 목록 조회 실패:', e);
        container.innerHTML = '<div class="status-message">조회에 실패했습니다.</div>';
    }
}

// ── 국가 진입 ──
window.enterCountry = function(country) {
    currentCountry = country;
    showCountryDetail(country, getPersistedDate());
};

// ── Level 2: 국가 내부 (날짜폴더 + backup) ──
function showCountryDetail(country, date) {
    currentCountry = country;
    updateBackLink();

    filterBar = new FilterBar('#filterBar', {
        sticky: true,
        controls: [
            { type: 'date', key: 'browseDate', label: '조회 날짜', value: date, max: formatLocalDate(new Date()) },
            { type: 'button', label: '조회', style: 'primary', onClick: () => loadFiles() },
            { type: 'button', label: '전날', style: 'outline', onClick: () => { filterBar.prevDay(); loadFiles(); } },
            { type: 'button', label: '다음날', style: 'outline', onClick: () => {
                const before = filterBar.getValue('browseDate');
                filterBar.nextDay();
                if (filterBar.getValue('browseDate') === before) {
                    showToast('오늘 이후 날짜는 조회할 수 없습니다.', 'warning');
                    return;
                }
                loadFiles();
            }},
        ]
    }).render();


    loadFiles();
}

// ── 파일 목록 조회 ──
async function loadFiles() {
    const date = filterBar.getValue('browseDate');
    updateUrl();

    const container = document.getElementById('content');
    container.innerHTML = '<div class="status-message"><div class="loading-spinner"></div> 조회 중...</div>';

    try {
        const res = await fetch(`${API_URL}?country=${currentCountry}&date=${date}`);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<div class="status-message">${esc(data.error)}</div>`;
            return;
        }

        renderFileExplorer(data);
    } catch (e) {
        console.error('조회 실패:', e);
        container.innerHTML = '<div class="status-message">조회에 실패했습니다.</div>';
    }
}

// ── 파일 탐색기 렌더링 ──
function renderFileExplorer(data) {
    currentDateFolder = data.date_folder;
    hideMoveBar();

    const container = document.getElementById('content');
    const ICON_ARROW = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>';

    const folders = [
        { id: 'date', name: data.date_folder, files: data.date_files, label: null, checkable: true },
        { id: 'backup', name: 'backup', files: data.backup_files, label: `${data.date_folder} 기준`, checkable: false },
    ];

    let html = `
        <div class="explorer">
            <div class="explorer-header">
                <div class="explorer-title">uploads/${esc(currentCountry)}/</div>
                <div class="explorer-count">${folders.length}개 폴더</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th class="col-check"></th>
                        <th class="col-toggle"></th>
                        <th class="col-icon"></th>
                        <th class="col-name">파일명</th>
                        <th class="col-size">크기</th>
                        <th class="col-type">파일 유형</th>
                        <th class="col-modified">최종 수정</th>
                    </tr>
                </thead>`;

    folders.forEach(folder => {
        const count = folder.files ? folder.files.length : 0;
        const folderId = 'folder-' + folder.id;

        html += `
                <tbody>
                    <tr class="row-folder" onclick="toggleFolder('${folderId}', this)">
                        <td class="col-check"></td>
                        <td class="col-toggle">${ICON_ARROW}</td>
                        <td class="col-icon">${ICON_FOLDER}</td>
                        <td class="col-name">${esc(folder.name)}/</td>
                        <td class="col-size"></td>
                        <td class="col-type">파일 폴더</td>
                        <td class="col-modified">${count}개 파일${folder.label ? ' (' + esc(folder.label) + ')' : ''}</td>
                    </tr>
                </tbody>`;

        // 파일 행 (토글)
        html += `<tbody id="${folderId}" class="file-rows">`;
        if (count === 0) {
            html += `
                    <tr class="row-file">
                        <td></td>
                        <td></td>
                        <td></td>
                        <td class="col-name" colspan="4" style="color:var(--text-secondary);">파일이 없습니다.</td>
                    </tr>`;
        } else {
            folder.files.forEach(f => {
                const ext = f.name.split('.').pop().toUpperCase();
                const checkbox = folder.checkable
                    ? `<input type="checkbox" class="file-check" data-name="${esc(f.name)}" onchange="updateMoveBar()">`
                    : '';
                html += `
                    <tr class="row-file">
                        <td class="col-check">${checkbox}</td>
                        <td></td>
                        <td class="col-icon">${ICON_FILE}</td>
                        <td class="col-name">${esc(f.name)}</td>
                        <td class="col-size">${formatFileSize(f.size)}</td>
                        <td class="col-type">${esc(ext)} 파일</td>
                        <td class="col-modified">${esc(f.modified)}</td>
                    </tr>`;
            });
        }
        html += '</tbody>';
    });

    html += '</table></div>';
    container.innerHTML = html;
}

window.toggleFolder = function(folderId, folderRow) {
    const tbody = document.getElementById(folderId);
    const isOpen = tbody.classList.toggle('open');
    folderRow.classList.toggle('open', isOpen);
};

// ── 체크박스 ──
window.updateMoveBar = function() {
    const checked = document.querySelectorAll('.file-check:checked');
    const bar = document.getElementById('moveBar');
    const count = document.getElementById('moveCount');

    if (checked.length > 0) {
        bar.classList.add('visible');
        count.textContent = `${checked.length}개 선택`;
    } else {
        bar.classList.remove('visible');
    }
};

function hideMoveBar() {
    document.getElementById('moveBar').classList.remove('visible');
}

// ── 백업 이동 ──
window.moveToBackup = async function() {
    const checked = document.querySelectorAll('.file-check:checked');
    if (checked.length === 0) return;

    const files = Array.from(checked).map(cb => cb.dataset.name);

    const confirmed = await showConfirm(
        `${files.length}개 파일을 backup 폴더로 이동하시겠습니까?\n\n${files.join('\n')}`,
        'warning'
    );
    if (!confirmed) return;

    try {
        const res = await fetch(MOVE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                country: currentCountry,
                date_folder: currentDateFolder,
                files: files,
            })
        });
        const data = await res.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        if (data.moved && data.moved.length > 0) {
            showToast(`${data.moved.length}개 파일 이동 완료`, 'success');
        }
        if (data.skipped && data.skipped.length > 0) {
            showToast(`${data.skipped.length}개 파일 이미 존재하여 건너뜀`, 'warning');
        }
        if (data.failed && data.failed.length > 0) {
            showToast(`${data.failed.length}개 파일 이동 실패`, 'error');
        }

        // 새로고침
        loadFiles();
    } catch (e) {
        console.error('이동 실패:', e);
        showToast('파일 이동에 실패했습니다.', 'error');
    }
};

// ── 유틸 ──
function updateBackLink() {
    document.getElementById('backLabel').textContent = currentCountry ? '국가 목록' : 'DS Layer 1';
}

function updateUrl() {
    let url = location.pathname;
    if (currentCountry) {
        const date = filterBar ? filterBar.getValue('browseDate') : initDate;
        url += `?country=${currentCountry}&date=${date}`;
    }
    history.replaceState(null, '', url);
}

// ── 시작 ──
document.addEventListener('DOMContentLoaded', init);

})();
