(function () {
    "use strict";

    function setupDropdown(dropdown) {
        const feed = dropdown.dataset.notificationFeed;
        const list = document.querySelector('[data-notification-list="' + feed + '"]');
        const scope = list || dropdown;
        let refreshVersion = 0;
        let pendingWrites = 0;

        function showError() {
            let error = scope.querySelector(".notification-save-error");
            if (!error) {
                error = document.createElement("div");
                error.className = "notification-save-error";
                error.setAttribute("role", "alert");
                (list || dropdown.querySelector(".header-notification-menu")).prepend(error);
            }
            error.textContent = "Lettura non salvata. Riprova; se la sessione è scaduta, accedi nuovamente.";
        }

        async function readResponse(response) {
            if (!response.ok || response.redirected || !(response.headers.get("Content-Type") || "").includes("application/json")) {
                throw new Error("Notification request failed");
            }
            const data = await response.json();
            if (!data.success) throw new Error("Notification not saved");
            return data;
        }

        async function refresh() {
            const version = ++refreshVersion;
            const url = new URL(dropdown.dataset.notificationStatusUrl, window.location.origin);
            url.searchParams.set("next", window.location.pathname + window.location.search);
            try {
                const data = await readResponse(await fetch(url, {credentials: "same-origin", cache: "no-store", headers: {Accept: "application/json"}}));
                if (version !== refreshVersion || pendingWrites) return;
                const badge = dropdown.querySelector(".header-notification-count");
                badge.textContent = String(data.non_lette);
                badge.hidden = data.non_lette === 0;
                const menu = dropdown.querySelector(".header-notification-menu");
                menu.outerHTML = data.html;
                if (window.ArborisPopupWindowTriggers) window.ArborisPopupWindowTriggers.wire(dropdown);
            } catch (_) {
                // Una risposta di login o un errore di rete non equivale a zero non lette.
            }
        }

        function updateList(ids) {
            if (!list) return;
            const readIds = new Set(ids.map(String));
            list.querySelectorAll("[data-notification-id]").forEach(row => {
                if (!readIds.has(row.dataset.notificationId)) return;
                row.classList.remove("finance-row-unread");
                const state = row.querySelector("[data-notification-state]");
                if (state) {
                    state.textContent = "Letta";
                    state.className = "anagrafica-status-chip is-muted";
                }
                row.querySelectorAll("form").forEach(form => { form.hidden = true; });
                if (list.dataset.unreadOnly === "1") row.hidden = true;
            });
            const visible = list.querySelectorAll("[data-notification-id]:not([hidden])").length;
            const count = document.querySelector("[data-notification-list-count]");
            if (count) count.textContent = String(visible);
            if (!visible && !list.querySelector(".empty-state")) {
                const empty = document.createElement("div");
                empty.className = "empty-state";
                empty.textContent = "Nessuna notifica da leggere. Le precedenti restano disponibili nel filtro Tutte.";
                list.append(empty);
            }
        }

        async function save(url, form) {
            const csrf = (form || document).querySelector("[name=csrfmiddlewaretoken]");
            if (!csrf) { showError(); return; }
            const body = new URLSearchParams({csrfmiddlewaretoken: csrf.value, next: window.location.pathname + window.location.search});
            pendingWrites += 1;
            refreshVersion += 1;
            const buttons = form ? Array.from(form.querySelectorAll("button")) : [];
            buttons.forEach(button => { button.disabled = true; });
            try {
                const data = await readResponse(await fetch(url, {
                    method: "POST", body, credentials: "same-origin", keepalive: true,
                    headers: {Accept: "application/json"},
                }));
                updateList(data.lette_ids);
                scope.querySelectorAll(".notification-save-error").forEach(error => error.remove());
            } catch (_) {
                showError();
            } finally {
                pendingWrites -= 1;
                buttons.forEach(button => { button.disabled = false; });
                if (!pendingWrites) refresh();
            }
        }

        // La richiesta parte prima della navigazione o dell'apertura del popup.
        // keepalive ne permette il completamento anche cambiando pagina.
        document.addEventListener("click", function (event) {
            const link = event.target.closest("a[data-notification-read-url]");
            if (link && (dropdown.contains(link) || (list && list.contains(link)))) save(link.dataset.notificationReadUrl);
        }, true);
        document.addEventListener("submit", function (event) {
            const form = event.target;
            const belongsToFeed = dropdown.contains(form) || (list && list.contains(form)) || form.dataset.notificationMarkAll === feed;
            if (!belongsToFeed) return;
            event.preventDefault();
            save(form.action, form);
        }, true);
        dropdown.addEventListener("toggle", function () {
            if (!dropdown.open) return;
            document.querySelectorAll("[data-notification-status-url]").forEach(other => {
                if (other !== dropdown) other.open = false;
            });
            refresh();
        });
        // A normal navigation already contains a fresh server-rendered summary.
        // Refresh on history restoration, where the browser reuses old markup.
        window.addEventListener("pageshow", function (event) { if (event.persisted) refresh(); });
        document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
    }

    function init() {
        document.querySelectorAll("[data-notification-status-url]").forEach(setupDropdown);
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
