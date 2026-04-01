
// window.DX_DOC_EDIT_CONFIG 브릿지 연동
const CONFIG = window.DX_DOC_EDIT_CONFIG || {};

let editor = null;
const documentId = CONFIG.documentId || '';
const isNew = CONFIG.isNew || false;
let categoryType = CONFIG.categoryType || 1;

let objectDocumentId = '';

let existingFiles = [];
let pendingFiles = [];
let pendingDeletes = [];

document.addEventListener('DOMContentLoaded', function() {
    if (isNew) {
        objectDocumentId = generateObjectDocumentId();
    }

    if (categoryType === 2) {
        document.getElementById('editorSection').style.display = 'none';
        initFileMode();
    } else if (categoryType === 3) {
        initEditorMode();
        initFileMode();
    } else {
        initEditorMode();
    }

    if (!isNew && documentId) {
        loadDocument(documentId);
    }

    updateBackLink();
});

function updateBackLink() {
    const btn = document.getElementById('btnBackToList');
    if (!btn) return;
    const catIdHidden = document.getElementById('categoryIdHidden');
    const catIdSelect = document.getElementById('categoryId');
    const catId = catIdHidden ? catIdHidden.value : (catIdSelect ? catIdSelect.value : '');
    if (catId) {
        btn.href = (CONFIG.urls?.index || '') + '?category=' + encodeURIComponent(catId);
    }
}

function initEditorMode() {
    document.getElementById('editorSection').style.display = '';
    if (categoryType !== 3) {
        document.getElementById('fileSection').style.display = 'none';
    }
    if (editor) return;

    if (typeof AppButton !== 'undefined') {
        AppButton('#editorPreviewBtnArea', '미리보기', 'openDocPreview', { icon: 'search', style: 'outline', size: 'sm' });
    }

    if (typeof initEditor !== 'undefined') {
        editor = initEditor('editor', '', {
            height: '650px',
            getObjectDocumentId: function() { return objectDocumentId; }
        });
    }

    if (isNew) {
        const tplEl = document.getElementById('templateContentData');
        if (tplEl && tplEl.value.trim() && typeof setEditorHTML !== 'undefined') {
            setEditorHTML(editor, tplEl.value);
        }
    }
}

function openDocPreview() {
    var docTitle = document.getElementById('documentTitle').value.trim();
    if (typeof editorPreview !== 'undefined') {
        editorPreview.open(editor, '문서 미리보기', docTitle);
    }
}

function initFileMode() {
    if (categoryType !== 3) {
        document.getElementById('editorSection').style.display = 'none';
    }
    document.getElementById('fileSection').style.display = '';
    document.getElementById('fileMemoSection').style.display = (categoryType === 3) ? 'none' : '';

    const dropzone = document.getElementById('fileDropzone');
    const fileInput = document.getElementById('fileInput');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', function() { fileInput.click(); });

        fileInput.addEventListener('change', function() {
            handleFiles(fileInput.files);
            fileInput.value = '';
        });

        dropzone.addEventListener('dragover', function(e) {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        dropzone.addEventListener('dragleave', function() {
            dropzone.classList.remove('dragover');
        });
        dropzone.addEventListener('drop', function(e) {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });
    }
}

function handleFiles(files) {
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const tempId = 'pending-' + Date.now() + '-' + i;
        pendingFiles.push({ tempId: tempId, name: file.name, size: file.size, fileObj: file });
        addFileItem(tempId, file.name, file.size, null, false, true);
    }
}

function addFileItem(id, name, size, url, uploading, isPending) {
    const sizeStr = formatFileSize(size);
    const list = document.getElementById('fileList');
    if (!list) return;
    const div = document.createElement('div');
    div.className = 'file-item';
    div.id = 'file-' + id;
    div.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span class="file-item-name">${escapeHtml(name)}</span>
        <span class="file-item-size">${uploading ? '업로드 중...' : sizeStr}</span>
        ${uploading ? '' : `<button class="file-item-remove" onclick="removeFile('${id}', ${isPending ? 'true' : 'false'})" title="삭제">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>`}
    `;
    list.appendChild(div);
}

function removeFileItem(id) {
    const el = document.getElementById('file-' + id);
    if (el) el.remove();
}

function removeFile(id, isPending) {
    if (isPending) {
        pendingFiles = pendingFiles.filter(f => f.tempId !== id);
    } else {
        existingFiles = existingFiles.filter(f => String(f.file_id) !== String(id));
        pendingDeletes.push(id);
    }
    removeFileItem(id);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function loadDocument(id) {
    fetch((CONFIG.urls?.api_detail || '') + '?document_id=' + encodeURIComponent(id))
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                const doc = res.document;
                objectDocumentId = doc.object_document_id || '';
                categoryType = doc.category_type || 1;
                
                const catSelect = document.getElementById('categoryId');
                const catName = document.getElementById('categoryName');
                if (catSelect && catName) {
                    catSelect.value = doc.category_id;
                    const selectedOption = catSelect.options[catSelect.selectedIndex];
                    catName.textContent = selectedOption ? selectedOption.text : doc.category_id;
                }
                const docTitleEl = document.getElementById('documentTitle');
                if (docTitleEl) docTitleEl.value = doc.title;

                updateBackLink();

                if (categoryType === 2) {
                    if (!document.getElementById('fileSection').style.display ||
                        document.getElementById('fileSection').style.display === 'none') {
                        initFileMode();
                    }
                    document.getElementById('editorSection').style.display = 'none';
                    document.getElementById('fileSection').style.display = '';
                    if (doc.content) {
                        const fileContentEl = document.getElementById('fileContent');
                        if (fileContentEl) fileContentEl.value = doc.content;
                    }
                    loadExistingFiles();
                } else if (categoryType === 3) {
                    initEditorMode();
                    initFileMode();
                    if (doc.content && typeof setEditorHTML !== 'undefined') setEditorHTML(editor, doc.content);
                    loadExistingFiles();
                } else {
                    document.getElementById('fileSection').style.display = 'none';
                    if (doc.content && typeof setEditorHTML !== 'undefined') setEditorHTML(editor, doc.content);
                }
            } else {
                if (typeof showToast !== 'undefined') showToast(res.error || '문서를 불러올 수 없습니다.', 'error');
            }
        });
}

function loadExistingFiles() {
    if (!objectDocumentId) return;
    fetch((CONFIG.urls?.api_files || '') + '?object_document_id=' + encodeURIComponent(objectDocumentId))
        .then(r => r.json())
        .then(res => {
            if (res.success && res.files) {
                res.files.forEach(f => {
                    existingFiles.push({
                        file_id: f.file_id,
                        name: f.original_file_name,
                        size: f.file_size,
                        url: '/api/dx/documents/file/' + f.file_name
                    });
                    addFileItem(f.file_id, f.original_file_name, f.file_size, '/api/dx/documents/file/' + f.file_name, false, false);
                });
            }
        });
}

async function uploadPendingFiles() {
    const results = [];
    for (const f of pendingFiles) {
        const formData = new FormData();
        formData.append('file', f.fileObj, f.name);
        formData.append('object_document_id', objectDocumentId);
        formData.append('upload_type', '2'); // 2 = 첨부파일
        
        const res = await fetch(CONFIG.urls?.api_upload || '', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: formData
        }).then(r => r.json());
        results.push(res);
    }
    return results;
}

function deletePendingFiles() {
    const promises = pendingDeletes.map(fileId => {
        return fetch((CONFIG.urls?.file_delete_base || '/api/dx/documents/files/') + fileId + '/delete/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        }).then(r => r.json());
    });
    return Promise.all(promises);
}

function saveDocument() {
    const hiddenCat = document.getElementById('categoryIdHidden');
    const categoryId = hiddenCat ? hiddenCat.value : document.getElementById('categoryId').value;
    const title = document.getElementById('documentTitle').value.trim();

    let content;
    if (categoryType === 2) {
        content = document.getElementById('fileContent').value.trim();
    } else {
        content = (typeof getEditorHTML !== 'undefined' && editor) ? getEditorHTML(editor) : '';
    }

    if (!categoryId) {
        if (typeof showToast !== 'undefined') showToast('카테고리를 선택하세요.', 'error');
        return;
    }

    if (!title) {
        if (typeof showToast !== 'undefined') showToast('문서 제목을 입력하세요.', 'error');
        return;
    }

    if ((categoryType === 2 || categoryType === 3) && (pendingFiles.length > 0 || pendingDeletes.length > 0)) {
        Promise.all([uploadPendingFiles(), deletePendingFiles()])
            .then(function(results) {
                const uploadResults = results[0];
                const failedUploads = uploadResults.filter(r => !r.success);
                if (failedUploads.length > 0) {
                    if (typeof showToast !== 'undefined') showToast('일부 파일 업로드에 실패했습니다.', 'error');
                    return;
                }
                pendingFiles = [];
                pendingDeletes = [];
                doSaveDocument(categoryId, title, content);
            })
            .catch(function() {
                if (typeof showToast !== 'undefined') showToast('파일 처리 중 오류가 발생했습니다.', 'error');
            });
    } else {
        doSaveDocument(categoryId, title, content);
    }
}

function doSaveDocument(categoryId, title, content) {
    let url, body;
    if (isNew) {
        url = CONFIG.urls?.api_create || '';
        body = { category_id: categoryId, title: title, content: content, object_document_id: objectDocumentId };
    } else {
        url = (CONFIG.urls?.update_base || '/api/dx/documents/') + encodeURIComponent(documentId) + '/update/';
        body = { title: title, content: content };
    }

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(body)
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            if (typeof showToast !== 'undefined') showToast(res.message, 'success');
            if (isNew && res.document_id) {
                setTimeout(() => {
                    window.location.href = (CONFIG.urls?.edit_base || '/dx/documents/') + encodeURIComponent(res.document_id) + '/edit/';
                }, 1000);
            }
        } else {
            if (typeof showToast !== 'undefined') showToast(res.error || '저장에 실패했습니다.', 'error');
        }
    });
}



function getCsrfToken() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
}

