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
        }
        resultsBox.classList.add("citta-results-floating");
        document.body.appendChild(resultsBox);

        container.dataset.autocompleteReady = "1";
        let selectedLabel = (input.value || "").trim();

        function updateDropdownPosition() {
            const inputRect = input.getBoundingClientRect();
            const desiredHeight = Math.min(resultsBox.scrollHeight || 240, 240);
            const availableBelow = Math.max(0, window.innerHeight - inputRect.bottom - 12);
            const availableAbove = Math.max(0, inputRect.top - 12);
            const openUpward = availableBelow < Math.min(160, desiredHeight) && availableAbove > availableBelow;
            container.classList.toggle("is-open-upward", openUpward);
            resultsBox.classList.toggle("is-open-upward", openUpward);
            resultsBox.style.left = `${inputRect.left}px`;
            resultsBox.style.width = `${inputRect.width}px`;
            if (openUpward) {
                resultsBox.style.top = "auto";
                resultsBox.style.bottom = `${window.innerHeight - inputRect.top + 4}px`;
            } else {
                resultsBox.style.top = `${inputRect.bottom + 4}px`;
                resultsBox.style.bottom = "auto";
            }
        }

        function hideResults() {
            resultsBox.style.display = "none";
            resultsBox.innerHTML = "";
            container.classList.remove("is-open-upward");
            resultsBox.classList.remove("is-open-upward");
            resultsBox.setAttribute("aria-hidden", "true");
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

            updateDropdownPosition();
            resultsBox.style.display = "block";
            resultsBox.setAttribute("aria-hidden", "false");
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
                const hadSelection = Boolean(hidden.value);
                hidden.value = "";
                hidden.dataset.codiceCatastale = "";
                if (hadSelection) {
                    hidden.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
            fetchResults();
        });

        input.addEventListener("focus", function () {
            if (input.value.trim().length >= 2 && resultsBox.children.length) {
                updateDropdownPosition();
                resultsBox.style.display = "block";
                resultsBox.setAttribute("aria-hidden", "false");
            }
        });

        document.addEventListener("click", function (event) {
            if (!container.contains(event.target) && !resultsBox.contains(event.target)) {
                hideResults();
            }
        });

        window.addEventListener("resize", function () {
            if (resultsBox.style.display === "block") {
                updateDropdownPosition();
            }
        });

        window.addEventListener("scroll", function () {
            if (resultsBox.style.display === "block") {
                updateDropdownPosition();
            }
        }, true);
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
