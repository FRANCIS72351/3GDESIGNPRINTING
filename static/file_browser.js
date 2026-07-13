(function () {
    const STORAGE_KEY = '3g-file-browser-view';
    const loadingEl = document.getElementById('fileBrowserLoading');
    const containers = document.querySelectorAll('[data-view-container]');
    const toggleButtons = document.querySelectorAll('.file-view-toggle [data-view]');

    function setView(mode) {
        containers.forEach(function (el) {
            el.classList.remove('file-items-grid', 'file-items-list');
            el.classList.add(mode === 'list' ? 'file-items-list' : 'file-items-grid');
        });
        toggleButtons.forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.view === mode);
        });
        try {
            localStorage.setItem(STORAGE_KEY, mode);
        } catch (e) { /* ignore */ }
    }

    const saved = (function () {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    })();

    if (saved === 'list' || saved === 'grid') {
        setView(saved);
    }

    toggleButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            setView(btn.dataset.view);
        });
    });

    function showLoading() {
        if (!loadingEl) return;
        loadingEl.setAttribute('aria-hidden', 'false');
        loadingEl.classList.add('is-visible');
    }

    document.querySelectorAll(
        '.file-tree-item, .file-item-folder, .file-breadcrumb a, .file-browser-sidebar a'
    ).forEach(function (link) {
        if (link.getAttribute('target') === '_blank') return;
        link.addEventListener('click', showLoading);
    });

    document.querySelectorAll('.file-search-form').forEach(function (form) {
        form.addEventListener('submit', showLoading);
    });

    window.addEventListener('pageshow', function () {
        if (!loadingEl) return;
        loadingEl.classList.remove('is-visible');
        loadingEl.setAttribute('aria-hidden', 'true');
    });
})();
