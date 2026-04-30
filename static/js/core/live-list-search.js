(function () {
    const DEBOUNCE_MS = 260;

    function debounce(fn, delay) {
        let timer = null;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function buildUrl(form) {
        const url = new URL(form.getAttribute("action") || window.location.href, window.location.href);
        const params = new URLSearchParams();
        const data = new FormData(form);

        data.forEach((value, key) => {
            const normalized = String(value || "").trim();
            if (normalized) {
                params.set(key, normalized);
            }
        });

        url.search = params.toString();
        return url;
    }

    function syncClearLink(form) {
        const input = form.querySelector("[data-live-list-input]");
        const clearLink = form.querySelector("[data-live-list-clear]");
        if (!input || !clearLink) return;
        clearLink.hidden = !input.value.trim();
    }

    function initForm(form) {
        if (!form || form.dataset.liveListReady === "1") return;

        const input = form.querySelector("[data-live-list-input]");
        const targetSelector = form.dataset.liveListTarget;
        if (!input || !targetSelector) return;

        form.dataset.liveListReady = "1";
        let requestSerial = 0;

        function refreshResults() {
            const target = document.querySelector(targetSelector);
            if (!target) return;

            const url = buildUrl(form);
            const serial = ++requestSerial;

            target.classList.add("is-loading");
            syncClearLink(form);
            window.history.replaceState({}, "", url);

            fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            })
                .then((response) => response.text())
                .then((html) => {
                    if (serial !== requestSerial) return;
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, "text/html");
                    const nextTarget = doc.querySelector(targetSelector);
                    if (!nextTarget) return;
                    target.innerHTML = nextTarget.innerHTML;
                    if (window.ArborisListRowLinks) {
                        window.ArborisListRowLinks.init();
                    }
                })
                .catch(() => {
                    form.submit();
                })
                .finally(() => {
                    if (serial === requestSerial) {
                        target.classList.remove("is-loading");
                    }
                });
        }

        const debouncedRefresh = debounce(refreshResults, DEBOUNCE_MS);

        input.addEventListener("input", function () {
            debouncedRefresh();
            syncClearLink(form);
        });

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            refreshResults();
        });

        const clearLink = form.querySelector("[data-live-list-clear]");
        if (clearLink) {
            clearLink.addEventListener("click", function (event) {
                event.preventDefault();
                input.value = "";
                refreshResults();
                input.focus();
            });
        }

        syncClearLink(form);
    }

    function init(root) {
        (root || document).querySelectorAll("[data-live-list-form]").forEach(initForm);
    }

    window.ArborisLiveListSearch = { init };

    document.addEventListener("DOMContentLoaded", function () {
        init(document);
    });
})();
