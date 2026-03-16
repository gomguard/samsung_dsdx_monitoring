/**
 * DS Document - 문서 편집 페이지
 *
 * 의존성:
 *   - security.js  : getCsrfToken()
 *   - ui.js        : showToast(), showConfirm()
 *   - format.js    : formatFileSize()
 *   - components/editor.html : initEditor(), setEditorHTML(), getEditorHTML(), generateObjectDocumentId(), editorPreview
 *   - buttons.js   : AppButton
 *
 * data attributes (id="app-data"):
 *   data-document-id           : 문서 ID (편집 시)
 *   data-is-new                : "true" / "false"
 *   data-category-type         : 카테고리 타입 (1,2,3)
 *   data-api-upload-url        : 파일 업로드 API URL
 *   data-api-detail-url        : 문서 상세 API URL
 *   data-api-create-url        : 문서 생성 API URL
 *   data-api-files-url         : 첨부파일 목록 API URL
 *   data-index-url             : 목록 페이지 URL
 */

var editor = null;
var documentId = '';
var isNew = true;
var categoryType = 1;

// object_document_id: 기존 문서면 API에서 로드, 새 문서면 JS에서 생성
var objectDocumentId = '';

// 파일 목록 (파일저장 모드)
var existingFiles = [];
var pendingFiles = [];
var pendingDeletes = [];

// 페이지 로드
document.addEventListener('DOMContentLoaded', function() {
    var appData = document.getElementById('app-data').dataset;
    documentId = appData.documentId || '';
    isNew = appData.isNew === 'true';
    categoryType = parseInt(appData.categoryType) || 1;

    if (isNew) {
        objectDocumentId = generateObjectDocumentId();
    }

    // 모드별 UI 초기화
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

// 목록 링크에 현재 카테고리 반영
function updateBackLink() {
    var appData = document.getElementById('app-data').dataset;
    var btn = document.getElementById('btnBackToList');
    if (!btn) return;
    var catId = document.getElementById('categoryIdHidden')
        ? document.getElementById('categoryIdHidden').value
        : (document.getElementById('categoryId') ? document.getElementById('categoryId').value : '');
    if (catId) {
        btn.href = appData.indexUrl + '?category=' + encodeURIComponent(catId);
    }
}

// 에디터 초기화
function initEditorMode() {
    var appData = document.getElementById('app-data').dataset;
    document.getElementById('editorSection').style.display = '';
    if (editor) return;

    AppButton('#editorPreviewBtnArea', '미리보기', 'openDocPreview', { icon: 'search', style: 'outline', size: 'sm' });

    editor = initEditor('editor', '', {
        height: '650px',
        uploadUrl: appData.apiUploadUrl,
        getObjectDocumentId: function() { return objectDocumentId; }
    });

    if (isNew) {
        var tplEl = document.getElementById('templateContentData');
        if (tplEl && tplEl.value.trim()) {
            setEditorHTML(editor, tplEl.value);
        }
    }
}

// 파일저장 초기화
function initFileMode() {
    document.getElementById('fileSection').style.display = '';
    document.getElementById('fileMemoSection').style.display = editor ? 'none' : '';
    setupFileDropzone();
}

// 문서 미리보기
function openDocPreview() {
    var docTitle = document.getElementById('documentTitle').value.trim();
    editorPreview.open(editor, '문서 미리보기', docTitle);
}

// 파일 드롭존 설정
var _dropzoneInitialized = false;
function setupFileDropzone() {
    if (_dropzoneInitialized) return;
    _dropzoneInitialized = true;
    var dropzone = document.getElementById('fileDropzone');
    var fileInput = document.getElementById('fileInput');

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

// 파일 처리 (메모리에 보관, 저장 시 업로드)
function handleFiles(files) {
    for (var i = 0; i < files.length; i++) {
        var file = files[i];
        var tempId = 'pending-' + Date.now() + '-' + i;
        pendingFiles.push({ tempId: tempId, name: file.name, size: file.size, fileObj: file });
        addFileItem(tempId, file.name, file.size, null, false, true);
    }
}

// 파일 목록 UI 추가
function addFileItem(id, name, size, url, uploading, isPending) {
    var sizeStr = formatFileSize(size);
    var list = document.getElementById('fileList');
    var div = document.createElement('div');
    div.className = 'file-item';
    div.id = 'file-' + id;
    div.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
            '<polyline points="14 2 14 8 20 8"/>' +
        '</svg>' +
        '<span class="file-item-name">' + escapeHtml(name) + '</span>' +
        '<span class="file-item-size">' + (uploading ? '업로드 중...' : sizeStr) + '</span>' +
        (uploading ? '' : '<button class="file-item-remove" onclick="removeFile(\'' + id + '\', ' + (isPending ? 'true' : 'false') + ')" title="삭제">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">' +
                '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>' +
            '</svg>' +
        '</button>');
    list.appendChild(div);
}

function removeFileItem(id) {
    var el = document.getElementById('file-' + id);
    if (el) el.remove();
}

function removeFile(id, isPending) {
    if (isPending) {
        pendingFiles = pendingFiles.filter(function(f) { return f.tempId !== id; });
    } else {
        existingFiles = existingFiles.filter(function(f) { return String(f.file_id) !== String(id); });
        pendingDeletes.push(id);
    }
    removeFileItem(id);
}

// escapeHtml → esc() (security.js 공통)
var escapeHtml = esc;

// 문서 로드
function loadDocument(id) {
    var appData = document.getElementById('app-data').dataset;
    fetch(appData.apiDetailUrl + '?document_id=' + encodeURIComponent(id))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.success) {
                var doc = res.document;
                objectDocumentId = doc.object_document_id || '';
                categoryType = doc.category_type || 1;

                var catSelect = document.getElementById('categoryId');
                var catName = document.getElementById('categoryName');
                if (catSelect && catName) {
                    catSelect.value = doc.category_id;
                    var selectedOption = catSelect.options[catSelect.selectedIndex];
                    catName.textContent = selectedOption ? selectedOption.text : doc.category_id;
                }
                document.getElementById('documentTitle').value = doc.title;

                updateBackLink();

                if (categoryType === 2) {
                    document.getElementById('editorSection').style.display = 'none';
                    initFileMode();
                    if (doc.content) document.getElementById('fileContent').value = doc.content;
                    loadExistingFiles();
                } else if (categoryType === 3) {
                    initEditorMode();
                    initFileMode();
                    if (doc.content) setEditorHTML(editor, doc.content);
                    loadExistingFiles();
                } else {
                    document.getElementById('fileSection').style.display = 'none';
                    initEditorMode();
                    if (doc.content) setEditorHTML(editor, doc.content);
                }
            } else {
                showToast(res.error || '문서를 불러올 수 없습니다.', 'error');
            }
        });
}

// 기존 첨부파일 로드
function loadExistingFiles() {
    var appData = document.getElementById('app-data').dataset;
    if (!objectDocumentId) return;
    fetch(appData.apiFilesUrl + '?object_document_id=' + encodeURIComponent(objectDocumentId))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.success && res.files) {
                res.files.forEach(function(f) {
                    existingFiles.push({
                        file_id: f.file_id,
                        name: f.original_file_name,
                        size: f.file_size,
                        url: '/api/ds/documents/file/' + f.file_name
                    });
                    addFileItem(f.file_id, f.original_file_name, f.file_size, '/api/ds/documents/file/' + f.file_name, false, false);
                });
            }
        });
}

// 파일 일괄 업로드 (저장 시 호출, upload_type=2 첨부파일)
function uploadPendingFiles() {
    var appData = document.getElementById('app-data').dataset;
    var promises = pendingFiles.map(function(f) {
        var formData = new FormData();
        formData.append('file', f.fileObj, f.name);
        formData.append('object_document_id', objectDocumentId);
        formData.append('upload_type', '2');
        return fetch(appData.apiUploadUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: formData
        }).then(function(r) { return r.json(); });
    });
    return Promise.all(promises);
}

// 파일 일괄 삭제 (저장 시 호출)
function deletePendingFiles() {
    var promises = pendingDeletes.map(function(fileId) {
        return fetch('/api/ds/documents/files/' + fileId + '/delete/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        }).then(function(r) { return r.json(); });
    });
    return Promise.all(promises);
}

// 문서 저장
function saveDocument() {
    var hiddenCat = document.getElementById('categoryIdHidden');
    var categoryId = hiddenCat ? hiddenCat.value : document.getElementById('categoryId').value;
    var title = document.getElementById('documentTitle').value.trim();

    // 모드별 content 결정
    var content;
    if (categoryType === 2) {
        content = document.getElementById('fileContent').value.trim();
    } else if (categoryType === 3) {
        content = getEditorHTML(editor);
    } else {
        content = getEditorHTML(editor);
    }

    if (!categoryId) {
        showToast('카테고리를 선택하세요.', 'error');
        return;
    }

    if (!title) {
        showToast('문서 제목을 입력하세요.', 'error');
        return;
    }

    // 파일 모드(type 2, 3): 업로드/삭제 먼저 처리 후 문서 저장
    if ((categoryType === 2 || categoryType === 3) && (pendingFiles.length > 0 || pendingDeletes.length > 0)) {
        Promise.all([uploadPendingFiles(), deletePendingFiles()])
            .then(function(results) {
                var uploadResults = results[0];
                var failedUploads = uploadResults.filter(function(r) { return !r.success; });
                if (failedUploads.length > 0) {
                    showToast('일부 파일 업로드에 실패했습니다.', 'error');
                    return;
                }
                pendingFiles = [];
                pendingDeletes = [];
                doSaveDocument(categoryId, title, content);
            })
            .catch(function() {
                showToast('파일 처리 중 오류가 발생했습니다.', 'error');
            });
    } else {
        doSaveDocument(categoryId, title, content);
    }
}

// 실제 문서 저장 API 호출
function doSaveDocument(categoryId, title, content) {
    var appData = document.getElementById('app-data').dataset;
    var url, body;
    if (isNew) {
        url = appData.apiCreateUrl;
        body = { category_id: categoryId, title: title, content: content, object_document_id: objectDocumentId };
    } else {
        url = '/api/ds/documents/' + encodeURIComponent(documentId) + '/update/';
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
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (res.success) {
            showToast(res.message, 'success');
            if (isNew && res.document_id) {
                setTimeout(function() {
                    window.location.href = '/ds/documents/' + encodeURIComponent(res.document_id) + '/edit/';
                }, 1000);
            }
        } else {
            showToast(res.error || '저장에 실패했습니다.', 'error');
        }
    });
}

// 문서 삭제
function deleteDocument() {
    var appData = document.getElementById('app-data').dataset;
    showConfirm('이 문서를 삭제하시겠습니까?').then(function(confirmed) {
        if (confirmed) {
            fetch('/api/ds/documents/' + encodeURIComponent(documentId) + '/delete/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() }
            })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.success) {
                    showToast(res.message, 'success');
                    setTimeout(function() {
                        window.location.href = appData.indexUrl;
                    }, 1000);
                } else {
                    showToast(res.error || '삭제에 실패했습니다.', 'error');
                }
            });
        }
    });
}
