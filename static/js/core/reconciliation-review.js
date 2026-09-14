(function () {
    "use strict";
    const header = document.querySelector("[data-reconciliation-status]");
    const review = document.querySelector("[data-reconciliation-review]");
    const url = review ? review.dataset.statusUrl : header && header.dataset.reconciliationStatus;
    let inFlight = false;
    let baseline = null;
    let pendingRejections = 0;
    let acceptNextStatus = false;

    function tellParent() {
        try {
            if (window.opener) window.opener.postMessage({type: "arboris-reconciliation-updated"}, window.location.origin);
            if (window.parent !== window) window.parent.postMessage({type: "arboris-reconciliation-updated"}, window.location.origin);
        } catch (_) {}
    }
    async function refresh() {
        if (!url || document.hidden || inFlight || pendingRejections) return;
        inFlight = true;
        try {
            const response = await fetch(url, {credentials: "same-origin", cache: "no-store", arborisBackground: true, headers: {Accept: "application/json"}});
            if (!response.ok || response.redirected || !(response.headers.get("content-type") || "").includes("application/json")) return;
            const data = await response.json();
            if (pendingRejections) return;
            if (header) {
                header.querySelector("[data-reconciliation-count]").textContent = data.count;
                header.dataset.hasPending = String(data.count > 0);
                header.title = data.analisi_rinviata ? "Analisi rinviata: nuovo tentativo automatico" : data.analisi_in_corso ? "Analisi degli abbinamenti in corso" : "Apri le proposte da confermare";
            }
            if (review) {
                const signature = JSON.stringify(data);
                if (!acceptNextStatus && ((baseline !== null && signature !== baseline) || (baseline === null && data.count !== Number(review.dataset.initialCount)))) review.querySelector("[data-review-refresh]").hidden = false;
                baseline = signature;
                acceptNextStatus = false;
                review.querySelector("[data-analysis-state]").textContent = data.analisi_rinviata ? "Analisi rinviata: il sistema riproverà automaticamente." : data.analisi_in_corso ? "Analisi in corso. Gli abbinamenti saranno disponibili al completamento." : data.count + " casi da verificare.";
            }
        } catch (_) {
            // Keep the last successful count when offline or after session expiry.
        } finally { inFlight = false; }
    }
    if (url) {
        window.setInterval(refresh, 30000);
        document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
        window.addEventListener("focus", refresh);
        window.addEventListener("message", function (event) {
            if (event.origin === window.location.origin && event.data && event.data.type === "arboris-reconciliation-updated") refresh();
        });
    }
    if (!review) return;
    const form = review.querySelector("[data-review-form]");
    const errorBox = review.querySelector("[data-review-error]");
    const boxes = () => Array.from(form.querySelectorAll("[data-proposal-nodes]"));
    const rows = () => Array.from(form.querySelectorAll("[data-review-row]"));
    const panels = row => Array.from(row.querySelectorAll("[data-proposal-panel]"));
    const selectedBoxes = () => boxes().filter(box => box.checked && !box.disabled && !box.closest("[data-review-row]").hidden);
    let submitted = false;

    function updateSelection() {
        const selected = selectedBoxes();
        const summary = form.querySelector("[data-selection-summary]");
        const cents = selected.reduce((total, box) => total + Number(box.dataset.proposalTotalCents), 0);
        const total = new Intl.NumberFormat("it-IT", {style: "currency", currency: "EUR"}).format(cents / 100);
        if (summary) summary.textContent = selected.length ? (selected.length === 1 ? "1 proposta selezionata" : selected.length + " proposte selezionate") + " · Totale: " + total : "Nessuna proposta selezionata";
        form.querySelectorAll("[data-bulk-decision]").forEach(button => { button.disabled = !selected.length || submitted; });
        const empty = !rows().some(row => !row.hidden);
        form.querySelector("[data-review-empty]").hidden = !empty;
        const bulk = form.querySelector("[data-review-bulk]");
        if (bulk) bulk.hidden = empty || !selected.length;
    }
    function resolveConflicts(box) {
        if (!box || !box.checked) return;
        const nodes = new Set(box.dataset.proposalNodes.split(","));
        boxes().forEach(other => {
            if (other !== box && other.checked && other.dataset.proposalNodes.split(",").some(node => nodes.has(node))) other.checked = false;
        });
    }
    function activate(row, id, preserveSelection) {
        const wasSelected = panels(row).some(panel => {
            const box = panel.querySelector("[data-proposal-nodes]");
            return box && box.checked;
        });
        panels(row).forEach(panel => {
            const active = panel.dataset.proposalPanel === id;
            panel.hidden = !active;
            panel.querySelectorAll("button, input").forEach(control => { control.disabled = !active; });
            const box = panel.querySelector("[data-proposal-nodes]");
            if (box) box.checked = active && preserveSelection && wasSelected;
            if (active) {
                row.style.setProperty("--match-confidence", panel.dataset.confidence);
                resolveConflicts(box);
            }
        });
        updateSelection();
    }
    rows().forEach(row => {
        const choice = row.querySelector("[data-proposal-choice]");
        activate(row, choice ? choice.value : panels(row)[0].dataset.proposalPanel, true);
        if (choice) choice.addEventListener("change", () => activate(row, choice.value, true));
    });
    review.classList.add("review-enhanced");
    form.addEventListener("change", event => {
        if (event.target.matches("[data-proposal-nodes]")) {
            resolveConflicts(event.target);
            updateSelection();
        }
    });
    function removeSavedOptions(row, saved) {
        panels(row).forEach(panel => { if (saved.has(panel.dataset.proposalPanel)) panel.remove(); });
        const remaining = panels(row);
        if (!remaining.length) { row.remove(); return; }
        const ids = remaining.map(panel => panel.dataset.proposalPanel);
        row.dataset.rejectIds = ids.join(",");
        row.querySelectorAll('[data-review-action="rifiuta"]').forEach(button => { button.value = "rifiuta:" + ids.join(","); });
        const choice = row.querySelector("[data-proposal-choice]");
        if (choice) {
            Array.from(choice.options).forEach(option => { if (saved.has(option.value)) option.remove(); });
            row.querySelector("[data-option-count]").textContent = "(" + ids.length + ")";
        }
        row.hidden = false;
        activate(row, choice ? choice.value : ids[0], false);
    }
    async function rejectRows(targetRows) {
        targetRows = targetRows.filter(row => row.isConnected && !row.hidden);
        if (!targetRows.length) return;
        const ids = Array.from(new Set(targetRows.flatMap(row => row.dataset.rejectIds.split(","))));
        const data = new URLSearchParams();
        data.set("csrfmiddlewaretoken", form.querySelector('[name="csrfmiddlewaretoken"]').value);
        data.set("ambito", form.querySelector('[name="ambito"]').value);
        data.set("azione", "rifiuta");
        ids.forEach(id => data.append("proposte", id));
        const previouslyChecked = new Set(selectedBoxes().map(box => box.value));
        pendingRejections++;
        targetRows.forEach(row => { row.hidden = true; });
        errorBox.hidden = true;
        updateSelection();
        const saved = new Set();
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 20000);
        try {
            const response = await fetch(form.action, {
                method: "POST", body: data, credentials: "same-origin", keepalive: true,
                arborisBackground: true, signal: controller.signal,
                headers: {Accept: "application/json"},
            });
            if (!response.ok || response.redirected || !(response.headers.get("content-type") || "").includes("application/json")) throw new Error("Salvataggio non riuscito.");
            const result = await response.json();
            if (!Array.isArray(result.results)) throw new Error("Risposta non valida.");
            result.results.forEach(item => { if (item.success) saved.add(String(item.id)); });
            if (saved.size !== ids.length) throw new Error((result.errors || []).join(" ") || "Alcune proposte sono cambiate: aggiorna l'elenco prima di riprovare.");
        } catch (error) {
            errorBox.textContent = "Non è stato possibile completare il rifiuto. Le righe non salvate sono state ripristinate: riprova o aggiorna le proposte.";
            errorBox.hidden = false;
        } finally {
            window.clearTimeout(timeout);
            targetRows.forEach(row => {
                removeSavedOptions(row, saved);
                if (row.isConnected) {
                    const box = row.querySelector('[data-proposal-panel]:not([hidden]) [data-proposal-nodes]');
                    if (box && previouslyChecked.has(box.value)) { box.checked = true; resolveConflicts(box); }
                }
            });
            pendingRejections--;
            if (saved.size) {
                const next = review.querySelector("[data-review-next]");
                if (next) { next.href = window.location.href; next.textContent = "Carica altre proposte"; }
            }
            updateSelection();
            acceptNextStatus = true;
            tellParent();
            refresh();
        }
    }
    function rejectionTargets(button) {
        const row = button.closest("[data-review-row]");
        return row ? [row] : Array.from(new Set(selectedBoxes().map(box => box.closest("[data-review-row]"))));
    }
    // Handle rejection on click before a submit can arm the navigation overlay.
    form.addEventListener("click", event => {
        const button = event.target.closest('button[data-review-action="rifiuta"], button[data-bulk-decision][value="rifiuta"]');
        if (!button || button.disabled || submitted) return;
        event.preventDefault();
        rejectRows(rejectionTargets(button));
    });
    form.addEventListener("submit", function (event) {
        if (submitted) { event.preventDefault(); return; }
        const button = event.submitter;
        if (!button) { event.preventDefault(); return; }
        const action = button.dataset.reviewAction || button.value;
        if (action === "rifiuta") {
            event.preventDefault();
            rejectRows(rejectionTargets(button));
            return;
        }
        submitted = true;
        form.setAttribute("aria-busy", "true");
        window.setTimeout(() => form.querySelectorAll("button").forEach(item => { item.disabled = true; }), 0);
    });
    window.addEventListener("pageshow", function (event) {
        if (!event.persisted) return;
        submitted = false;
        form.removeAttribute("aria-busy");
        rows().forEach(row => {
            const choice = row.querySelector("[data-proposal-choice]");
            activate(row, choice ? choice.value : panels(row)[0].dataset.proposalPanel, true);
        });
        refresh();
    });
    review.querySelectorAll("[data-review-close]").forEach(button => button.addEventListener("click", function () {
        tellParent();
        if (window.parent !== window && window.parent.ArborisModalPopups) {
            window.parent.ArborisModalPopups.closeForWindow(window);
        } else { window.close(); }
    }));
    tellParent();
    refresh();
})();
