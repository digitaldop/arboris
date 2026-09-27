(function () {
    "use strict";
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-address-autocomplete]").forEach(function (root) {
            const form = root.closest("form");
            const input = root.querySelector("#address-query");
            const results = root.querySelector("#address-results");
            const status = root.querySelector("[data-address-status]");
            const preview = root.querySelector("[data-address-preview]");
            const field = name => form.elements.namedItem(name);
            let timer, controller, revision = 0;
            function clearResults() {
                results.replaceChildren(); results.hidden = true;
                input.setAttribute("aria-expanded", "false");
            }
            function select(item) {
                revision++; if (controller) controller.abort(); clearResults();
                field("via").value = item.via;
                field("numero_civico").value = item.numero_civico;
                field("citta").value = item.citta_id || "";
                field("citta_search").value = item.citta_label || "";
                field("cap").value = item.cap || "";
                const capSelect = field("cap_scelto");
                capSelect.replaceChildren(new Option("Seleziona il CAP", ""));
                if (item.cap_id) capSelect.add(new Option(item.cap, item.cap_id, true, true));
                field("citta").dispatchEvent(new Event("change", {bubbles: true}));
                field("geoapify_token").value = item.token || "";
                input.value = item.label;
                preview.textContent = item.label;
                status.textContent = item.requires_review ? "Verifica Comune e CAP nei campi manuali: la corrispondenza non è certa." : "Indirizzo selezionato. Puoi verificare o correggere i campi prima di salvare.";
            }
            function schedule() {
                clearTimeout(timer); revision++; clearResults();
                if (controller) controller.abort();
                const query = input.value.trim(), current = revision;
                if (query.length < 4) return;
                timer = setTimeout(async function () {
                    controller = new AbortController();
                    status.textContent = "Ricerca in corso…";
                    const url = new URL(root.dataset.addressAutocomplete, window.location.origin);
                    url.searchParams.set("q", query);
                    if (field("citta").value) url.searchParams.set("citta_id", field("citta").value);
                    try {
                        const response = await fetch(url, {signal: controller.signal, credentials: "same-origin"});
                        const data = await response.json();
                        if (current !== revision) return;
                        clearResults();
                        (data.results || []).forEach(function (item) {
                            const button = document.createElement("button");
                            button.type = "button"; button.className = "btn btn-secondary";
                            button.textContent = item.label + (item.source === "arboris" ? " · già in Arboris" : "");
                            button.addEventListener("click", () => select(item));
                            results.appendChild(button);
                        });
                        results.hidden = !results.children.length;
                        input.setAttribute("aria-expanded", String(!results.hidden));
                        status.textContent = data.unavailable ? "Ricerca esterna non disponibile. Puoi usare gli indirizzi in Arboris o compilare i campi manualmente." : results.hidden ? "Nessun risultato: compila i campi manualmente." : "Seleziona un indirizzo e verifica i dati.";
                    } catch (error) {
                        if (error.name !== "AbortError" && current === revision) status.textContent = "Ricerca non disponibile. Compila i campi manualmente.";
                    }
                }, 350);
            }
            input.addEventListener("input", schedule);
            input.addEventListener("keydown", function (event) {
                if (event.key === "Escape") { revision++; clearResults(); if (controller) controller.abort(); }
                if (event.key === "ArrowDown" && results.firstElementChild) { event.preventDefault(); results.firstElementChild.focus(); }
            });
            results.addEventListener("keydown", function (event) {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    const next = event.key === "ArrowDown" ? event.target.nextElementSibling : event.target.previousElementSibling;
                    (next || input).focus();
                }
                if (event.key === "Escape") { clearResults(); input.focus(); }
            });
            ["via", "numero_civico", "citta_search", "cap"].forEach(function (name) {
                field(name).addEventListener("input", function () {
                    field("geoapify_token").value = ""; preview.textContent = "Indirizzo modificato manualmente.";
                    if (name === "cap") field("cap_scelto").value = "";
                    if (name === "citta_search") field("cap").value = "";
                });
            });
            field("cap_scelto").addEventListener("change", function () {
                const option = this.selectedOptions[0];
                field("cap").value = this.value && option ? option.textContent : "";
            });
        });
    });
})();
