(function () {
    "use strict";

    function init() {
        const dropdown = document.querySelector("[data-notification-status-url]");
        if (!dropdown) return;
        let refreshVersion = 0;
        let pendingWrites = 0;

        function showError() {
            let error = document.querySelector(".notification-save-error");
            if (!error) {
                error = document.createElement("div");
                error.className = "notification-save-error";
                error.setAttribute("role", "alert");
                (document.querySelector("[data-notification-list]") || dropdown.querySelector(".header-notification-menu")).prepend(error);
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
            const list = document.querySelector("[data-notification-list]");
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
                document.querySelectorAll(".notification-save-error").forEach(error => error.remove());
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
            if (link) save(link.dataset.notificationReadUrl);
        }, true);
        document.addEventListener("submit", function (event) {
            const form = event.target;
            if (!form.matches(".header-notification-read-form, .header-notification-mark-all-form, [data-notification-list] form, [data-notification-mark-all]")) return;
            event.preventDefault();
            save(form.action, form);
        }, true);
        dropdown.addEventListener("toggle", function () { if (dropdown.open) refresh(); });
        window.addEventListener("pageshow", refresh);
        document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
