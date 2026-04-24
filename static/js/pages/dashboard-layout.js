window.ArborisDashboardLayout = (function () {
    function readStoredOrder(storageKey) {
        if (!storageKey) {
            return [];
        }

        try {
            const value = window.localStorage.getItem(storageKey);
            const parsed = JSON.parse(value || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    function saveOrder(storageKey, container) {
        if (!storageKey) {
            return;
        }

        const orderedIds = Array.from(container.querySelectorAll("[data-dashboard-section-id]"))
            .map((section) => section.dataset.dashboardSectionId)
            .filter(Boolean);

        try {
            window.localStorage.setItem(storageKey, JSON.stringify(orderedIds));
        } catch (error) {}
    }

    function applyStoredOrder(storageKey, container) {
        const orderedIds = readStoredOrder(storageKey);
        if (!orderedIds.length) {
            return;
        }

        const sections = Array.from(container.querySelectorAll("[data-dashboard-section-id]"));
        const sectionMap = new Map(
            sections.map((section) => [section.dataset.dashboardSectionId, section])
        );

        orderedIds.forEach((sectionId) => {
            const section = sectionMap.get(sectionId);
            if (section) {
                container.appendChild(section);
                sectionMap.delete(sectionId);
            }
        });

        sectionMap.forEach((section) => {
            container.appendChild(section);
        });
    }

    function bindDragAndDrop(container, storageKey) {
        let draggingSection = null;

        function clearDropState() {
            container.querySelectorAll(".dashboard-section.is-drop-target").forEach((section) => {
                section.classList.remove("is-drop-target");
            });
        }

        function bindSection(section) {
            if (section.dataset.dashboardDragBound === "1") {
                return;
            }

            section.dataset.dashboardDragBound = "1";
            const handle = section.querySelector(".dashboard-drag-handle");
            if (!handle) {
                return;
            }

            handle.addEventListener("click", function (event) {
                event.preventDefault();
                event.stopPropagation();
            });

            handle.addEventListener("dragstart", function (event) {
                draggingSection = section;
                section.classList.add("is-dragging");
                container.classList.add("is-drag-active");
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", section.dataset.dashboardSectionId || "");
            });

            handle.addEventListener("dragend", function () {
                if (draggingSection) {
                    draggingSection.classList.remove("is-dragging");
                }
                container.classList.remove("is-drag-active");
                clearDropState();
                draggingSection = null;
                saveOrder(storageKey, container);
            });
        }

        Array.from(container.querySelectorAll("[data-dashboard-section-id]")).forEach(bindSection);

        container.addEventListener("dragover", function (event) {
            if (!draggingSection) {
                return;
            }

            event.preventDefault();
            const targetSection = event.target.closest("[data-dashboard-section-id]");
            clearDropState();

            if (!targetSection || targetSection === draggingSection) {
                return;
            }

            const rect = targetSection.getBoundingClientRect();
            const insertAfter = event.clientY > rect.top + (rect.height / 2);
            targetSection.classList.add("is-drop-target");

            if (insertAfter) {
                container.insertBefore(draggingSection, targetSection.nextSibling);
            } else {
                container.insertBefore(draggingSection, targetSection);
            }
        });

        container.addEventListener("drop", function (event) {
            if (!draggingSection) {
                return;
            }

            event.preventDefault();
            clearDropState();
            saveOrder(storageKey, container);
        });
    }

    function init(container = document) {
        const dashboardContainer = container.querySelector("#dashboard-sections");
        if (!dashboardContainer || dashboardContainer.dataset.dashboardLayoutBound === "1") {
            return;
        }

        dashboardContainer.dataset.dashboardLayoutBound = "1";
        const storageKey = dashboardContainer.dataset.dashboardOrderKey || "arboris-dashboard-section-order";
        applyStoredOrder(storageKey, dashboardContainer);
        bindDragAndDrop(dashboardContainer, storageKey);
    }

    return {
        init,
    };
})();
