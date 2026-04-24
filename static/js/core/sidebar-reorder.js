window.ArborisSidebarReorder = (function () {
    const STORAGE_KEY = "arboris-sidebar-section-order";
    const ENABLED_CLASS = "is-reorder-enabled";
    const DRAGGING_CLASS = "is-dragging";

    function getSections(container) {
        return Array.from(container.children).filter(function (element) {
            return element.classList.contains("sidebar-section");
        });
    }

    function readStoredOrder() {
        try {
            const rawValue = window.localStorage.getItem(STORAGE_KEY);
            if (!rawValue) {
                return [];
            }

            const parsedValue = JSON.parse(rawValue);
            return Array.isArray(parsedValue) ? parsedValue : [];
        } catch (error) {
            return [];
        }
    }

    function saveCurrentOrder(container) {
        const order = getSections(container)
            .map(function (section) {
                return section.dataset.sidebarSectionKey;
            })
            .filter(Boolean);

        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(order));
        } catch (error) {
            return;
        }
    }

    function applyStoredOrder(container) {
        const storedOrder = readStoredOrder();
        if (!storedOrder.length) {
            return;
        }

        const sectionsByKey = new Map();
        getSections(container).forEach(function (section) {
            sectionsByKey.set(section.dataset.sidebarSectionKey, section);
        });

        storedOrder.forEach(function (sectionKey) {
            const section = sectionsByKey.get(sectionKey);
            if (section) {
                container.appendChild(section);
                sectionsByKey.delete(sectionKey);
            }
        });

        sectionsByKey.forEach(function (section) {
            container.appendChild(section);
        });
    }

    function setReorderEnabled(container, enabled) {
        container.classList.toggle(ENABLED_CLASS, enabled);

        getSections(container).forEach(function (section) {
            section.draggable = enabled;
        });
    }

    function getDragAfterElement(container, pointerY, draggedSection) {
        return getSections(container)
            .filter(function (section) {
                return section !== draggedSection;
            })
            .reduce(
                function (closest, section) {
                    const rect = section.getBoundingClientRect();
                    const offset = pointerY - rect.top - rect.height / 2;

                    if (offset < 0 && offset > closest.offset) {
                        return {
                            offset,
                            element: section,
                        };
                    }

                    return closest;
                },
                {
                    offset: Number.NEGATIVE_INFINITY,
                    element: null,
                }
            ).element;
    }

    function init() {
        const container = document.getElementById("sidebar-reorder-list");
        const toggle = document.getElementById("sidebar-reorder-toggle");
        if (!container || !toggle) {
            return;
        }

        let draggedSection = null;

        applyStoredOrder(container);
        setReorderEnabled(container, false);
        toggle.checked = false;

        getSections(container).forEach(function (section) {
            section.addEventListener("dragstart", function (event) {
                if (!container.classList.contains(ENABLED_CLASS)) {
                    event.preventDefault();
                    return;
                }

                draggedSection = section;
                section.classList.add(DRAGGING_CLASS);

                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", section.dataset.sidebarSectionKey || "");
                }
            });

            section.addEventListener("dragend", function () {
                if (!draggedSection) {
                    return;
                }

                draggedSection.classList.remove(DRAGGING_CLASS);
                draggedSection = null;
                saveCurrentOrder(container);
            });
        });

        container.addEventListener("dragover", function (event) {
            if (!container.classList.contains(ENABLED_CLASS) || !draggedSection) {
                return;
            }

            event.preventDefault();
            const nextSection = getDragAfterElement(container, event.clientY, draggedSection);

            if (nextSection) {
                container.insertBefore(draggedSection, nextSection);
                return;
            }

            container.appendChild(draggedSection);
        });

        toggle.addEventListener("change", function () {
            setReorderEnabled(container, toggle.checked);
        });
    }

    return {
        init,
    };
})();
