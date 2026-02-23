/**
 * Knowledge Base JavaScript for FlyPig LINE Bot Admin
 */

document.addEventListener('DOMContentLoaded', function () {
    // Initialize view document functionality
    initViewDocument();

    // Initialize delete document functionality
    initDeleteDocument();

    // Initialize file upload functionality
    initFileUpload();

    // Initialize status polling
    initStatusPolling();
});

/**
 * Status badge HTML for each state
 */
const STATUS_BADGES = {
    learned: '<span class="badge bg-success">✅ 已學習</span>',
    pending: '<span class="badge bg-warning text-dark">⏳ 等待中</span>',
    no_content: '<span class="badge bg-danger">❌ 無內容</span>',
};

/**
 * Fetch and update document learning statuses
 */
function refreshStatus() {
    const btn = document.getElementById('refreshStatusBtn');
    if (btn) {
        btn.disabled = true;
        btn.querySelector('i').classList.add('fa-spin');
    }

    fetch('/admin/knowledge_base/status')
        .then(r => r.json())
        .then(data => {
            data.documents.forEach(doc => {
                const cell = document.querySelector(`.doc-status[data-doc-id="${doc.id}"]`);
                if (cell) {
                    cell.innerHTML = STATUS_BADGES[doc.status] || doc.status;
                }
            });

            // If there are pending docs, keep polling; otherwise stop
            if (!data.has_pending && window._statusInterval) {
                clearInterval(window._statusInterval);
                window._statusInterval = null;
            }
        })
        .catch(err => console.error('Status refresh error:', err))
        .finally(() => {
            if (btn) {
                btn.disabled = false;
                btn.querySelector('i').classList.remove('fa-spin');
            }
        });
}

/**
 * Initialize auto-polling and refresh button
 */
function initStatusPolling() {
    // Manual refresh button
    const btn = document.getElementById('refreshStatusBtn');
    if (btn) {
        btn.addEventListener('click', refreshStatus);
    }

    // Auto-poll every 5 seconds if there are any pending documents
    const hasPending = document.querySelector('.badge.bg-warning');
    if (hasPending) {
        window._statusInterval = setInterval(refreshStatus, 5000);
    }
}

/**
 * Initialize the view document functionality
 */
function initViewDocument() {
    const viewButtons = document.querySelectorAll('.view-document');
    const documentTitle = document.getElementById('documentTitle');
    const documentContent = document.getElementById('documentContent');

    viewButtons.forEach(button => {
        button.addEventListener('click', function () {
            const docId = this.getAttribute('data-id');

            // Show loading state
            documentTitle.textContent = 'Loading...';
            documentContent.textContent = 'Loading document content...';

            // Fetch document data
            fetch(`/admin/knowledge_base/view/${docId}`)
                .then(response => response.json())
                .then(doc => {
                    // Update modal with document data
                    documentTitle.textContent = doc.title;
                    documentContent.textContent = doc.content;
                })
                .catch(error => {
                    console.error('Error fetching document:', error);
                    documentTitle.textContent = 'Error';
                    documentContent.textContent = 'Failed to load document content. Please try again.';
                });
        });
    });
}

/**
 * Initialize the delete document functionality
 */
function initDeleteDocument() {
    const deleteButtons = document.querySelectorAll('.delete-document');
    const deleteForm = document.getElementById('deleteDocumentForm');
    const deleteDocumentTitle = document.getElementById('deleteDocumentTitle');

    deleteButtons.forEach(button => {
        button.addEventListener('click', function () {
            const docId = this.getAttribute('data-id');
            const docTitle = this.getAttribute('data-title');

            // Set form action and document title
            deleteForm.action = `/admin/knowledge_base/delete/${docId}`;
            deleteDocumentTitle.textContent = docTitle;
        });
    });
}

/**
 * Initialize the file upload functionality
 */
function initFileUpload() {
    const fileInput = document.getElementById('file');
    const titleInput = document.getElementById('title');
    const contentInput = document.getElementById('content');

    if (!fileInput || !titleInput || !contentInput) return;

    fileInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file) return;

        // Set the title from the filename if empty
        if (titleInput.value.trim() === '') {
            // Remove extension and replace underscores/hyphens with spaces
            const fileName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
            // Capitalize first letter of each word
            titleInput.value = fileName.replace(/\b\w/g, l => l.toUpperCase());
        }

        // Handle text file preview
        if (file.type === 'text/plain' ||
            file.name.endsWith('.md') ||
            file.name.endsWith('.txt')) {

            const reader = new FileReader();
            reader.onload = function (e) {
                contentInput.value = e.target.result;
            };
            reader.readAsText(file);
        } else {
            // For non-text files, show a placeholder message
            contentInput.value = `File content will be processed on upload.\nFile: ${file.name}\nType: ${file.type}\nSize: ${(file.size / 1024).toFixed(2)} KB`;
        }
    });
}

/**
 * Format file size to human-readable format
 * @param {number} bytes - The file size in bytes
 * @returns {string} - Formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Show a preview of the document content
 * @param {string} content - The document content
 * @returns {string} - Truncated content for preview
 */
function getContentPreview(content) {
    const maxPreviewLength = 200;

    if (!content) return '';

    if (content.length > maxPreviewLength) {
        return content.substring(0, maxPreviewLength) + '...';
    }

    return content;
}
