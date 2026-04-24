(function () {
    function debounce(fn, delay) {
        let timer = null;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function initContainer(container) {
        if (!container || container.dataset.autocompleteReady === "1") {
            return;
        }

        const input = container.querySelector("[data-citta-search]");
        const hidden = container.querySelector("[data-citta-hidden]");
        let resultsBox = container.querySelector(".citta-results");

        if (!input || !hidden) {
            return;
        }

        if (!resultsBox) {
            resultsBox = document.createElement("div");
            resultsBox.className = "citta-results";
            resultsBox.setAttribute("aria-hidden", "true");
            container.appendChild(resultsBox);
        }

        container.dataset.autocompleteReady = "1";
        let selectedLabel = (input.value || "").trim();

        function hideResults() {
            resultsBox.style.display = "none";
            resultsBox.innerHTML = "";
        }

        function selectItem(item) {
            input.value = item.label;
            hidden.value = item.id;
            hidden.dataset.codiceCatastale = item.codice_catastale || "";
            selectedLabel = item.label;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            hidden.dispatchEvent(new Event("change", { bubbles: true }));
            hideResults();
        }

        function renderResults(results) {
            resultsBox.innerHTML = "";

            if (!results.length) {
                hideResults();
                return;
            }

            results.forEach((item) => {
                const row = document.createElement("div");
                row.className = "citta-item";
                row.textContent = item.label;
                row.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    selectItem(item);
                });
                resultsBox.appendChild(row);
            });

            resultsBox.style.display = "block";
        }

        const fetchResults = debounce(function () {
            const query = input.value.trim();

            if (query.length < 2) {
                hideResults();
                return;
            }

            fetch(`/ajax/cerca-citta/?q=${encodeURIComponent(query)}`)
                .then((response) => response.json())
                .then((data) => renderResults(data.results || []))
                .catch(() => hideResults());
        }, 180);

        input.addEventListener("input", function () {
            const query = input.value.trim();
            if (query !== selectedLabel) {
                hidden.value = "";
                hidden.dataset.codiceCatastale = "";
            }
            fetchResults();
        });

        input.addEventListener("focus", function () {
            if (input.value.trim().length >= 2 && resultsBox.children.length) {
                resultsBox.style.display = "block";
            }
        });

        document.addEventListener("click", function (event) {
            if (!container.contains(event.target)) {
                hideResults();
            }
        });
    }

    function init(root) {
        (root || document).querySelectorAll(".citta-autocomplete").forEach(initContainer);
    }

    window.ArborisCittaAutocomplete = {
        init,
    };

    document.addEventListener("DOMContentLoaded", function () {
        if (!document.querySelector(".citta-autocomplete [data-citta-search]")) {
            return;
        }

        init(document);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) {
                        return;
                    }

                    if (node.matches(".citta-autocomplete")) {
                        init(node.parentNode || document);
                        return;
                    }

                    if (node.querySelector(".citta-autocomplete")) {
                        init(node);
                    }
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
