(function () {
    const instances = new WeakMap();
    const openWrappers = new Set();

    function normalize(value) {
        return (value || "")
            .toString()
            .trim()
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");
    }

    function buildItems(select) {
        return Array.from(select.options || []).map(option => ({
            value: option.value,
            label: option.textContent.trim(),
            searchText: normalize(option.dataset.searchText || option.textContent),
            disabled: option.disabled,
        }));
    }

    function isInsideTemplate(select) {
        return Boolean(select.closest("template"));
    }

    function isHiddenEmptyInline(select) {
        return Boolean(select.closest(".inline-empty-row.is-hidden"));
    }

    function isVisible(select) {
        if (!select.isConnected) {
            return false;
        }

        if (isInsideTemplate(select) || isHiddenEmptyInline(select)) {
            return false;
        }

        return Boolean(select.offsetParent || select.getClientRects().length);
    }

    function isLocked(select) {
        return Boolean(
            select.disabled ||
            select.classList.contains("submit-safe-locked") ||
            select.getAttribute("aria-disabled") === "true"
        );
    }

    function closeAllExcept(currentWrapper) {
        Array.from(openWrappers).forEach(wrapper => {
            if (wrapper !== currentWrapper) {
                wrapper.classList.remove("is-open");
                wrapper.classList.remove("is-open-upward");
                openWrappers.delete(wrapper);
                const instance = instances.get(wrapper.querySelector("select[data-searchable-select='1']"));
                if (instance) {
                    instance.highlightedIndex = -1;
                    instance.syncInputValue(true);
                }
            }
        });
    }

    function initSelect(select, options) {
        const force = Boolean(options && options.force);

        if (!select || instances.has(select)) {
            return;
        }

        if (!force && !isVisible(select)) {
            return;
        }

        const placeholder = select.dataset.searchablePlaceholder || "Cerca...";

        const wrapper = document.createElement("div");
        wrapper.className = "searchable-select";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "searchable-select-input";
        input.placeholder = placeholder;
        input.autocomplete = "new-password";
        input.autocapitalize = "none";
        input.spellcheck = false;
        input.setAttribute("data-lpignore", "true");

        const dropdown = document.createElement("div");
        dropdown.className = "searchable-select-dropdown";

        select.classList.add("searchable-select-native");
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(input);
        wrapper.appendChild(dropdown);
        wrapper.appendChild(select);

        const state = {
            highlightedIndex: -1,
            attributeObserver: null,
            getItems: function () {
                return buildItems(select);
            },
            getSelectedItem: function () {
                return state.getItems().find(item => item.value && item.value === select.value) || null;
            },
            closeDropdown: function () {
                wrapper.classList.remove("is-open");
                wrapper.classList.remove("is-open-upward");
                openWrappers.delete(wrapper);
                state.highlightedIndex = -1;
            },
            updateDropdownPosition: function () {
                const inputRect = input.getBoundingClientRect();
                const desiredHeight = Math.min(dropdown.scrollHeight || 260, 260);
                const availableBelow = Math.max(0, window.innerHeight - inputRect.bottom - 12);
                const availableAbove = Math.max(0, inputRect.top - 12);
                const openUpward = availableBelow < Math.min(180, desiredHeight) && availableAbove > availableBelow;
                wrapper.classList.toggle("is-open-upward", openUpward);
            },
            openDropdown: function () {
                if (isLocked(select)) {
                    return;
                }
                closeAllExcept(wrapper);
                state.updateDropdownPosition();
                wrapper.classList.add("is-open");
                openWrappers.add(wrapper);
            },
            syncDisabledState: function () {
                const locked = isLocked(select);
                input.disabled = locked;
                input.readOnly = locked;
                wrapper.classList.toggle("is-disabled", locked);
                if (locked) {
                    state.closeDropdown();
                }
            },
            syncInputValue: function (force) {
                const selected = state.getSelectedItem();
                if (force || !input.matches(":focus")) {
                    input.value = selected ? selected.label : "";
                }
            },
            selectValue: function (value) {
                select.value = value || "";
                select.dispatchEvent(new Event("change", { bubbles: true }));
                state.syncInputValue(true);
                state.closeDropdown();
            },
            getFilteredItems: function () {
                const query = normalize(input.value);
                const source = state.getItems().filter(item => item.value && !item.disabled);

                if (!query) {
                    return source;
                }

                return source.filter(item => item.searchText.includes(query));
            },
            renderDropdown: function () {
                const filtered = state.getFilteredItems();
                dropdown.innerHTML = "";

                if (!filtered.length) {
                    const empty = document.createElement("div");
                    empty.className = "searchable-select-empty";
                    empty.textContent = "Nessun risultato";
                    dropdown.appendChild(empty);
                    state.updateDropdownPosition();
                    return;
                }

                filtered.forEach((item, index) => {
                    const row = document.createElement("div");
                    row.className = "searchable-select-option";
                    if (item.value === select.value) {
                        row.classList.add("is-selected");
                    }
                    if (index === state.highlightedIndex) {
                        row.classList.add("is-highlighted");
                    }
                    row.textContent = item.label;
                    row.addEventListener("mousedown", function (event) {
                        event.preventDefault();
                        state.selectValue(item.value);
                    });
                    dropdown.appendChild(row);
                });

                state.updateDropdownPosition();
            },
        };

        instances.set(select, state);

        input.addEventListener("focus", function () {
            state.renderDropdown();
            state.openDropdown();
        });

        input.addEventListener("click", function () {
            state.renderDropdown();
            state.openDropdown();
        });

        input.addEventListener("input", function () {
            state.highlightedIndex = -1;
            state.renderDropdown();
            state.openDropdown();
        });

        input.addEventListener("keydown", function (event) {
            const filtered = state.getFilteredItems();

            if (event.key === "ArrowDown") {
                event.preventDefault();
                if (!wrapper.classList.contains("is-open")) {
                    state.renderDropdown();
                    state.openDropdown();
                    return;
                }
                state.highlightedIndex = Math.min(state.highlightedIndex + 1, filtered.length - 1);
                state.renderDropdown();
                return;
            }

            if (event.key === "ArrowUp") {
                event.preventDefault();
                state.highlightedIndex = Math.max(state.highlightedIndex - 1, 0);
                state.renderDropdown();
                return;
            }

            if (event.key === "Enter") {
                if (!wrapper.classList.contains("is-open")) {
                    return;
                }
                event.preventDefault();
                const item = filtered[state.highlightedIndex] || filtered[0];
                if (item) {
                    state.selectValue(item.value);
                }
                return;
            }

            if (event.key === "Escape") {
                state.closeDropdown();
                state.syncInputValue(true);
            }
        });

        select.addEventListener("change", function () {
            state.syncDisabledState();
            state.syncInputValue(true);
            if (wrapper.classList.contains("is-open")) {
                state.renderDropdown();
            }
        });

        state.attributeObserver = new MutationObserver(function () {
            state.syncDisabledState();
            state.syncInputValue(true);
        });

        state.attributeObserver.observe(select, {
            attributes: true,
            attributeFilter: ["disabled", "class", "aria-disabled"],
        });

        state.syncDisabledState();
        state.syncInputValue(true);
    }

    function init(root, options) {
        (root || document).querySelectorAll("select[data-searchable-select='1']").forEach(select => initSelect(select, options));
    }

    function refresh(root) {
        (root || document).querySelectorAll("select[data-searchable-select='1']").forEach(select => {
            const instance = instances.get(select);
            if (instance) {
                instance.syncDisabledState();
                instance.syncInputValue(true);
            }
        });
    }

    window.ArborisFamigliaAutocomplete = {
        init,
        refresh,
    };

    document.addEventListener("click", function (event) {
        Array.from(openWrappers).forEach(wrapper => {
            if (!wrapper.contains(event.target)) {
                const select = wrapper.querySelector("select[data-searchable-select='1']");
                const instance = select ? instances.get(select) : null;
                if (instance) {
                    instance.closeDropdown();
                    instance.syncInputValue(true);
                }
            }
        });
    });

    document.addEventListener("focusin", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLSelectElement) || !target.matches("select[data-searchable-select='1']")) {
            return;
        }

        if (!instances.has(target)) {
            initSelect(target, { force: true });
            const wrapper = target.closest(".searchable-select");
            const input = wrapper ? wrapper.querySelector(".searchable-select-input") : null;
            if (input) {
                input.focus();
            }
        }
    });

    document.addEventListener("mousedown", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLSelectElement) || !target.matches("select[data-searchable-select='1']")) {
            return;
        }

        if (!instances.has(target)) {
            event.preventDefault();
            initSelect(target, { force: true });
            const wrapper = target.closest(".searchable-select");
            const input = wrapper ? wrapper.querySelector(".searchable-select-input") : null;
            if (input) {
                input.focus();
                const instance = instances.get(target);
                if (instance) {
                    instance.renderDropdown();
                    instance.openDropdown();
                }
            }
        }
    }, true);

    document.addEventListener("DOMContentLoaded", function () {
        init(document);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) {
                        return;
                    }

                    if (node.matches("select[data-searchable-select='1']")) {
                        init(node.parentNode || document);
                        return;
                    }

                    if (node.querySelector("select[data-searchable-select='1']")) {
                        init(node);
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    });
})();
