(function () {
    "use strict";
    const header = document.querySelector("[data-reconciliation-status]");
    const review = document.querySelector("[data-reconciliation-review]");
    const url = review ? review.dataset.statusUrl : header && header.dataset.reconciliationStatus;
    let inFlight = false;
    let baseline = null;
    let dirty = false;

    function tellParent() {
        try {
            if (window.opener) window.opener.postMessage({type: "arboris-reconciliation-updated"}, window.location.origin);
            if (window.parent !== window) window.parent.postMessage({type: "arboris-reconciliation-updated"}, window.location.origin);
        } catch (_) {}
    }
    async function refresh() {
        if (!url || document.hidden || inFlight) return;
        inFlight = true;
        try {
            const response = await fetch(url, {credentials: "same-origin", cache: "no-store", headers: {Accept: "application/json"}});
            if (!response.ok || response.redirected || !(response.headers.get("content-type") || "").includes("application/json")) return;
            const data = await response.json();
            if (header) {
                header.querySelector("[data-reconciliation-count]").textContent = data.count;
                header.dataset.hasPending = String(data.count > 0);
                header.title = data.analisi_rinviata ? "Analisi rinviata: nuovo tentativo automatico" : data.analisi_in_corso ? "Analisi degli abbinamenti in corso" : "Apri le proposte da confermare";
            }
            if (review) {
                const signature = JSON.stringify(data);
                if ((baseline !== null && signature !== baseline) || (baseline === null && data.count !== Number(review.dataset.initialCount))) review.querySelector("[data-review-refresh]").hidden = false;
                baseline = signature;
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
    tellParent();
    refresh();
    const form = review.querySelector("[data-review-form]");
    const checkboxes = Array.from(form.querySelectorAll("[data-proposal-nodes]"));
    function updateSelection() {
        const selected = checkboxes.filter(box => box.checked);
        dirty = selected.length > 0;
        const summary = form.querySelector("[data-selection-summary]");
        const cents = selected.reduce((total, box) => total + Number(box.dataset.proposalTotalCents), 0);
        const total = new Intl.NumberFormat("it-IT", {style: "currency", currency: "EUR"}).format(cents / 100);
        if (summary) summary.textContent = selected.length ? (selected.length === 1 ? "1 proposta selezionata" : selected.length + " proposte selezionate") + " · Totale: " + total : "Nessuna proposta selezionata";
        form.querySelectorAll("[data-bulk-decision]").forEach(button => { button.disabled = !dirty; });
    }
    checkboxes.forEach(box => box.addEventListener("change", function () {
        if (box.checked) {
            const nodes = new Set(box.dataset.proposalNodes.split(","));
            checkboxes.forEach(other => {
                if (other !== box && other.checked && other.dataset.proposalNodes.split(",").some(node => nodes.has(node))) other.checked = false;
            });
        }
        updateSelection();
    }));
    let submitted = false;
    window.addEventListener("pageshow", function (event) {
        if (!event.persisted) return;
        submitted = false;
        form.removeAttribute("aria-busy");
        form.querySelectorAll("[data-review-action]").forEach(button => { button.disabled = false; });
        updateSelection();
        refresh();
    });
    form.addEventListener("submit", function (event) {
        if (submitted) { event.preventDefault(); return; }
        const button = event.submitter;
        if (!button) { event.preventDefault(); return; }
        if (button.dataset.reviewAction) {
            const field = document.createElement("input");
            field.type = "hidden"; field.name = "azione"; field.value = button.dataset.reviewAction;
            form.appendChild(field);
        }
        submitted = true;
        form.setAttribute("aria-busy", "true");
        // Keep the submitter enabled until the browser serializes its name/value.
        window.setTimeout(function () { form.querySelectorAll("button").forEach(item => { item.disabled = true; }); }, 0);
    });
    review.querySelectorAll("[data-review-close]").forEach(button => button.addEventListener("click", function () {
        tellParent();
        if (window.parent !== window && window.parent.ArborisModalPopups) {
            window.parent.ArborisModalPopups.closeForWindow(window);
        } else { window.close(); }
    }));
})();
