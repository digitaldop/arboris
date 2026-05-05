(function () {
    const DEBOUNCE_MS = 220;
    const MIN_QUERY_LENGTH = 2;

    function debounce(fn, delay) {
        let timer = null;
        return function (...args) {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function buildResultMarkup(result, index) {
        const title = escapeHtml(result.title);
        const subtitle = escapeHtml(result.subtitle);
        const category = escapeHtml(result.category);
        const module = escapeHtml(result.module);
        const url = escapeHtml(result.url);

        return `
            <a
                href="${url}"
                class="header-search-result"
                role="option"
                id="global-search-option-${index}"
                data-global-search-result
                data-result-index="${index}"
            >
                <span class="header-search-result-main">
                    <span class="header-search-result-title">${title}</span>
                    ${subtitle ? `<span class="header-search-result-subtitle">${subtitle}</span>` : ""}
                </span>
                <span class="header-search-result-meta">
                    <span class="header-search-result-category">${category}</span>
                    ${module ? `<span class="header-search-result-module">${module}</span>` : ""}
                </span>
            </a>
        `;
    }

    function initForm(form) {
        if (!form || form.dataset.globalSearchReady === "1") {
            return;
        }

        const input = form.querySelector("[data-global-search-input]");
        const dropdown = form.querySelector("[data-global-search-dropdown]");
        const searchUrl = form.dataset.globalSearchUrl;
        if (!input || !dropdown || !searchUrl) {
            return;
        }

        form.dataset.globalSearchReady = "1";
        let requestSerial = 0;
        let activeIndex = -1;

        function getResults() {
            return Array.from(dropdown.querySelectorAll("[data-global-search-result]"));
        }

        function setExpanded(expanded) {
            input.setAttribute("aria-expanded", expanded ? "true" : "false");
        }

        function closeDropdown() {
            dropdown.hidden = true;
            dropdown.innerHTML = "";
            dropdown.classList.remove("is-loading");
            input.removeAttribute("aria-activedescendant");
            setExpanded(false);
            activeIndex = -1;
        }

        function setActiveIndex(index) {
            const results = getResults();
            if (!results.length) {
                activeIndex = -1;
                input.removeAttribute("aria-activedescendant");
                return;
            }

            activeIndex = Math.max(0, Math.min(index, results.length - 1));
            results.forEach((result, resultIndex) => {
                result.classList.toggle("is-active", resultIndex === activeIndex);
                result.setAttribute("aria-selected", resultIndex === activeIndex ? "true" : "false");
            });
            input.setAttribute("aria-activedescendant", results[activeIndex].id);
        }

        function renderMessage(message) {
            dropdown.hidden = false;
            dropdown.innerHTML = `<div class="header-search-empty">${escapeHtml(message)}</div>`;
            setExpanded(true);
            activeIndex = -1;
        }

        function renderResults(results, query) {
            dropdown.classList.remove("is-loading");

            if (!query || query.length < MIN_QUERY_LENGTH) {
                closeDropdown();
                return;
            }

            if (!results.length) {
                renderMessage("Nessuna corrispondenza trovata.");
                return;
            }

            dropdown.hidden = false;
            dropdown.innerHTML = `
                <div class="header-search-dropdown-head">
                    <span>Risultati</span>
                    <strong>${results.length}</strong>
                </div>
                <div class="header-search-results-list">
                    ${results.map(buildResultMarkup).join("")}
                </div>
            `;
            setExpanded(true);
            setActiveIndex(0);
        }

        function search() {
            const query = input.value.trim();
            const serial = ++requestSerial;

            if (query.length < MIN_QUERY_LENGTH) {
                closeDropdown();
                return;
            }

            const url = new URL(searchUrl, window.location.origin);
            url.searchParams.set("q", query);

            dropdown.hidden = false;
            dropdown.classList.add("is-loading");
            dropdown.innerHTML = '<div class="header-search-empty">Ricerca in corso...</div>';
            setExpanded(true);

            fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error("Search failed");
                    }
                    return response.json();
                })
                .then((data) => {
                    if (serial !== requestSerial) {
                        return;
                    }
                    renderResults(Array.isArray(data.results) ? data.results : [], query);
                })
                .catch(() => {
                    if (serial !== requestSerial) {
                        return;
                    }
                    renderMessage("Ricerca non disponibile in questo momento.");
                });
        }

        const debouncedSearch = debounce(search, DEBOUNCE_MS);

        input.addEventListener("input", debouncedSearch);
        input.addEventListener("focus", function () {
            if (input.value.trim().length >= MIN_QUERY_LENGTH && dropdown.innerHTML.trim()) {
                dropdown.hidden = false;
                setExpanded(true);
            }
        });

        input.addEventListener("keydown", function (event) {
            const results = getResults();
            if (event.key === "Escape") {
                closeDropdown();
                return;
            }
            if (!results.length) {
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex(activeIndex + 1);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex(activeIndex - 1);
            } else if (event.key === "Enter" && activeIndex >= 0) {
                event.preventDefault();
                results[activeIndex].click();
            }
        });

        form.addEventListener("submit", function (event) {
            const results = getResults();
            if (!results.length || activeIndex < 0) {
                return;
            }
            event.preventDefault();
            results[activeIndex].click();
        });

        document.addEventListener("click", function (event) {
            if (!form.contains(event.target)) {
                closeDropdown();
            }
        });
    }

    function init(root) {
        (root || document).querySelectorAll("[data-global-search-form]").forEach(initForm);
    }

    window.ArborisGlobalSearch = { init };

    document.addEventListener("DOMContentLoaded", function () {
        init(document);
    });
})();
