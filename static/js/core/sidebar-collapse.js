window.ArborisSidebarCollapse = (function () {
    const STORAGE_KEY = "arboris-sidebar-collapsed";

    function applyState(collapsed, button) {
        document.body.classList.toggle("sidebar-is-collapsed", collapsed);

        if (!button) {
            return;
        }

        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
        button.setAttribute(
            "title",
            collapsed ? "Espandi menu laterale" : "Comprimi menu laterale"
        );
        button.setAttribute(
            "aria-label",
            collapsed ? "Espandi menu laterale" : "Comprimi menu laterale"
        );

        const icon = button.querySelector(".sidebar-collapse-icon");
        if (icon) {
            icon.textContent = collapsed ? "\u203A" : "\u2039";
        }
    }

    function init() {
        const button = document.getElementById("sidebar-collapse-btn");
        if (!button) {
            return;
        }

        const collapsed = window.localStorage.getItem(STORAGE_KEY) === "1";
        applyState(collapsed, button);

        button.addEventListener("click", function () {
            const nextCollapsed = !document.body.classList.contains("sidebar-is-collapsed");
            applyState(nextCollapsed, button);
            window.localStorage.setItem(STORAGE_KEY, nextCollapsed ? "1" : "0");
        });
    }

    return {
        init,
    };
})();
