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
        return Array.from(select.options || []).map((option, index) => ({
            index,
            value: option.value,
            label: option.textContent.trim(),
            searchText: normalize(option.dataset.searchText || option.textContent),
            disabled: option.disabled,
            priority: option.dataset.searchablePriority === "1",
            group: option.dataset.searchableGroup || "",
            categoryName: option.dataset.categoryName || "",
            categoryParent: option.dataset.categoryParent || "",
            categoryLevel: Math.max(0, parseInt(option.dataset.categoryLevel || "0", 10) || 0),
            categoryType: option.dataset.categoryType || "",
            categoryKind: option.dataset.categoryKind || "",
            categoryColor: option.dataset.categoryColor || "",
            categoryIcon: option.dataset.categoryIcon || "",
            categoryPath: option.dataset.categoryPath || "",
            categoryHasChildren: option.dataset.categoryHasChildren === "1",
            categoryChildrenCount: Math.max(0, parseInt(option.dataset.categoryChildrenCount || "0", 10) || 0),
        }));
    }

    function mainSearchText(item) {
        return (item.searchText || "").split(" (")[0].trim();
    }

    function matchRank(item, query) {
        const text = item.searchText || "";
        const mainText = mainSearchText(item);

        if (text === query || mainText === query) {
            return 0;
        }

        if (text.startsWith(query) || mainText.startsWith(query)) {
            return 1;
        }

        if (text.includes(` ${query}`) || text.includes(`(${query}`)) {
            return 2;
        }

        return 3;
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

    function iconNameForCategory(item) {
        const map = {
            banknote: "coins",
            receipt: "document",
            wallet: "coins",
            "credit-card": "bank",
            bank: "bank",
            cart: "supplier",
            home: "home",
            school: "student",
            book: "document",
            users: "family",
            heart: "hands-heart",
            bolt: "lightbulb",
            droplet: "finance",
            wifi: "settings",
            tool: "settings",
            briefcase: "briefcase",
            calendar: "calendar",
            transfer: "refresh",
        };
        if (!item.value) {
            return "archive";
        }
        if (item.categoryIcon && map[item.categoryIcon]) {
            return map[item.categoryIcon];
        }
        if (item.categoryKind === "entrata") {
            return "coins";
        }
        if (item.categoryKind === "trasferimento") {
            return "refresh";
        }
        return item.categoryHasChildren ? "list" : "document";
    }

    function spriteHref() {
        const existingUse = document.querySelector("svg use[href*='arboris-ui-icons']");
        const existingHref = existingUse ? existingUse.getAttribute("href") : "";
        if (existingHref && existingHref.includes("#")) {
            return existingHref.split("#")[0];
        }
        return "/static/images/arboris-ui-icons.svg";
    }

    function appendSpriteIcon(target, iconName) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        svg.setAttribute("aria-hidden", "true");
        use.setAttribute("href", `${spriteHref()}#${iconName}`);
        svg.appendChild(use);
        target.appendChild(svg);
    }

    function renderCategoryOption(row, item) {
        const level = Math.min(item.categoryLevel || 0, 5);
        row.classList.add("searchable-select-option-category");
        row.classList.add(`searchable-select-option-category-level-${level}`);
        row.classList.toggle("is-nested", level > 0);
        row.classList.toggle("is-empty-category", !item.value);
        row.dataset.categoryKind = item.categoryKind || "";
        row.style.setProperty("--category-level", level);
        row.style.setProperty("--category-indent", `${level * 16}px`);

        const branch = document.createElement("span");
        branch.className = "searchable-select-category-branch";
        branch.setAttribute("aria-hidden", "true");

        const swatch = document.createElement("span");
        swatch.className = "searchable-select-category-swatch";
        if (item.categoryColor) {
            swatch.style.backgroundColor = item.categoryColor;
        }
        swatch.setAttribute("aria-hidden", "true");

        const text = document.createElement("span");
        text.className = "searchable-select-category-text";

        const name = document.createElement("span");
        name.className = "searchable-select-category-name";
        name.textContent = item.categoryName || item.label;

        const meta = document.createElement("span");
        meta.className = "searchable-select-category-meta";
        if (!item.value) {
            meta.textContent = item.categoryType || "Senza categoria";
        } else if (item.categoryParent) {
            meta.textContent = `${item.categoryParent} / ${item.categoryType || "Categoria"}`;
        } else {
            meta.textContent = `Categoria principale / ${item.categoryType || "Categoria"}`;
        }

        text.appendChild(name);
        text.appendChild(meta);
        row.appendChild(branch);
        row.appendChild(swatch);
        row.appendChild(text);
    }

    function renderMovementCategoryOption(row, item, select) {
        const level = Math.min(item.categoryLevel || 0, 6);
        row.classList.add("searchable-select-option-category");
        row.classList.add("searchable-select-option-movement-category");
        row.classList.add(`searchable-select-option-category-level-${level}`);
        row.classList.toggle("is-nested", level > 0);
        row.classList.toggle("is-empty-category", !item.value);
        row.classList.toggle("has-children", item.categoryHasChildren);
        row.dataset.categoryKind = item.categoryKind || "";
        row.style.setProperty("--category-level", level);
        row.style.setProperty("--category-indent", `${level * 18}px`);

        const branch = document.createElement("span");
        branch.className = "searchable-select-category-branch";
        branch.setAttribute("aria-hidden", "true");

        const icon = document.createElement("span");
        icon.className = "searchable-select-category-icon";
        if (item.categoryColor) {
            icon.style.setProperty("--category-color", item.categoryColor);
        }
        appendSpriteIcon(icon, iconNameForCategory(item));

        const text = document.createElement("span");
        text.className = "searchable-select-category-text";

        const name = document.createElement("span");
        name.className = "searchable-select-category-name";
        name.textContent = item.categoryName || item.label;

        const meta = document.createElement("span");
        meta.className = "searchable-select-category-meta";
        if (!item.value) {
            meta.textContent = item.categoryType || "Senza categoria";
        } else if (item.categoryParent) {
            meta.textContent = `${item.categoryParent} / ${item.categoryType || "Categoria"}`;
        } else {
            meta.textContent = `Categoria principale / ${item.categoryType || "Categoria"}`;
        }

        text.appendChild(name);
        text.appendChild(meta);

        const affordance = document.createElement("span");
        affordance.className = "searchable-select-category-affordance";
        affordance.setAttribute("aria-hidden", "true");
        if (item.value === select.value) {
            appendSpriteIcon(affordance, "check");
        } else if (item.categoryHasChildren) {
            affordance.textContent = "›";
        }

        row.appendChild(branch);
        row.appendChild(icon);
        row.appendChild(text);
        row.appendChild(affordance);
    }

    function renderOptionContent(row, item, select) {
        if (select.dataset.searchableVariant === "movement-category-tree") {
            renderMovementCategoryOption(row, item, select);
            return;
        }
        if (select.dataset.searchableVariant === "category-tree") {
            renderCategoryOption(row, item);
            return;
        }
        row.textContent = item.label;
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
        const minChars = Math.max(0, parseInt(select.dataset.searchableMinChars || "0", 10) || 0);

        const wrapper = document.createElement("div");
        wrapper.className = "searchable-select";
        if (select.dataset.searchableVariant) {
            wrapper.classList.add(`searchable-select-${select.dataset.searchableVariant}`);
        }

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
                const allowEmpty = select.dataset.searchableAllowEmpty === "1";
                const source = state.getItems().filter(item => (allowEmpty || item.value) && !item.disabled);
                const prioritySource = source.filter(item => item.priority);

                if (!query) {
                    if (prioritySource.length) {
                        return prioritySource;
                    }
                    return minChars ? [] : source;
                }

                if (minChars && query.length < minChars) {
                    return prioritySource.filter(item => item.searchText.includes(query));
                }

                return source
                    .filter(item => item.searchText.includes(query))
                    .sort((first, second) => {
                        if (first.priority !== second.priority) {
                            return first.priority ? -1 : 1;
                        }

                        const rankDelta = matchRank(first, query) - matchRank(second, query);
                        if (rankDelta !== 0) {
                            return rankDelta;
                        }

                        const lengthDelta = mainSearchText(first).length - mainSearchText(second).length;
                        if (lengthDelta !== 0) {
                            return lengthDelta;
                        }

                        return first.index - second.index;
                    });
            },
            renderDropdown: function () {
                const filtered = state.getFilteredItems();
                const isMovementCategoryTree = select.dataset.searchableVariant === "movement-category-tree";
                dropdown.innerHTML = "";

                if (!filtered.length) {
                    const empty = document.createElement("div");
                    empty.className = "searchable-select-empty";
                    const query = normalize(input.value);
                    empty.textContent = minChars && query.length < minChars
                        ? `Digita almeno ${minChars} caratteri`
                        : "Nessun risultato";
                    dropdown.appendChild(empty);
                    state.updateDropdownPosition();
                    return;
                }

                if (isMovementCategoryTree) {
                    const heading = document.createElement("div");
                    heading.className = "searchable-select-section-heading";
                    heading.textContent = normalize(input.value) ? "Risultati categorie" : "Categorie principali";
                    dropdown.appendChild(heading);
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
                    renderOptionContent(row, item, select);
                    row.addEventListener("mousedown", function (event) {
                        event.preventDefault();
                        state.selectValue(item.value);
                    });
                    dropdown.appendChild(row);
                });

                if (isMovementCategoryTree) {
                    const hint = document.createElement("div");
                    hint.className = "searchable-select-keyboard-hint";
                    hint.innerHTML = "<kbd>Invio</kbd><span>per confermare</span>";
                    dropdown.appendChild(hint);
                }

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
