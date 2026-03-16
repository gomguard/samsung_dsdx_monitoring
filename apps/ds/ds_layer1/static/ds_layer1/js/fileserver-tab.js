/**
 * DS Layer 1 — 파일서버 탭 (index 페이지 내)
 * 파일서버 용량 조회 + 날짜 이동
 */

// ── 날짜 이동 ──
function setPrevDayFileserver() {
    const dateInput = document.getElementById('fileserverDate');
    const current = new Date(dateInput.value);
    current.setDate(current.getDate() - 1);
    dateInput.value = formatLocalDate(current);
    loadFileserverData();
}

function setNextDayFileserver() {
    const dateInput = document.getElementById('fileserverDate');
    const [year, month, day] = dateInput.value.split('-').map(Number);
    const nextDate = new Date(year, month - 1, day + 1);
    const nextStr = formatLocalDate(nextDate);
    const todayStr = formatLocalDate(new Date());

    if (nextStr > todayStr) {
        showToast('오늘 이후 날짜로는 조회할 수 없습니다.', 'warning');
        return;
    }

    dateInput.value = nextStr;
    loadFileserverData();
}

function goFileserver() {
    const date = document.getElementById('fileserverDate').value;
    location.href = `/ds/layer1/fileserver/?date=${date}`;
}

// ── 데이터 로딩 ──
async function loadFileserverData() {
    let date = document.getElementById('fileserverDate').value;
    if (!validateQueryDate(date, 'fileserverDate')) {
        date = document.getElementById('fileserverDate').value;
    }

    document.getElementById('fileserverLoading').classList.remove('hidden');
    document.getElementById('fileserverContent').innerHTML = '';

    try {
        const response = await fetch(`/ds/layer1/api/fileserver/?date=${date}`);
        fileserverData = await response.json();

        if (fileserverData.error) {
            document.getElementById('fileserverContent').innerHTML = `<div class="loading">${esc(fileserverData.error)}</div>`;
        } else {
            renderFileserverData(fileserverData);
        }
    } catch (error) {
        console.error('Error loading fileserver data:', error);
        document.getElementById('fileserverContent').innerHTML = '<div class="loading">데이터 조회 실패</div>';
    }

    document.getElementById('fileserverLoading').classList.add('hidden');
}

// ── 렌더링 ──
function renderFileserverData(data) {
    document.getElementById('fsTotalCountries').textContent = data.summary.total_countries;
    document.getElementById('fsTotalFiles').textContent = data.summary.total_files;
    document.getElementById('fsTotalSize').textContent = data.summary.total_size.toLocaleString() + ' bytes';

    const container = document.getElementById('fileserverContent');

    if (!data.countries || data.countries.length === 0) {
        container.innerHTML = '<div class="loading">해당 날짜의 파일이 없습니다.</div>';
        return;
    }

    let allFiles = [];
    data.countries.forEach(country => {
        country.files.forEach(file => {
            allFiles.push({
                country_code: country.country_code,
                retailer: country.retailer,
                filename: file.name,
                size: file.size
            });
        });
    });

    let html = `
        <table class="fileserver-table">
            <thead>
                <tr>
                    <th>No</th>
                    <th>국가</th>
                    <th>리테일러</th>
                    <th>파일용량</th>
                    <th>파일명</th>
                </tr>
            </thead>
            <tbody>
    `;

    allFiles.forEach((file, idx) => {
        html += `
            <tr>
                <td>${idx + 1}</td>
                <td>${file.country_code}</td>
                <td><span class="retailer-name">${file.retailer}</span></td>
                <td><span class="file-size">${file.size.toLocaleString()}</span></td>
                <td>${file.filename}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function toggleFileList(btn) {
    const fileList = btn.nextElementSibling;
    const isHidden = fileList.classList.contains('hidden');
    fileList.classList.toggle('hidden');
    btn.textContent = isHidden ? '접기 ▲' : '상세 보기 ▼';
}
