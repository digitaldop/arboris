(() => {
    const form = document.getElementById("fic-sync-form");
    if (!form) return;
    const period = form.elements.periodo;
    const date = form.elements.data_inizio;
    const endDate = form.elements.data_fine;
    const manual = document.getElementById("fic-manual-date");
    const manualEnd = document.getElementById("fic-manual-end-date");
    const rangeHelp = document.getElementById("fic-manual-range-help");
    const submit = document.getElementById("fic-sync-submit");
    const pause = document.getElementById("fic-sync-pause");
    const status = document.getElementById("fic-sync-status");
    let running = false;
    let pauseRequested = false;
    let wakeWait = null;

    const waitForRetry = async (seconds, summary) => {
        const deadline = Date.now() + Math.max(1, Number(seconds) || 60) * 1000;
        while (!pauseRequested) {
            const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
            if (!remaining) return true;
            const hours = Math.floor(remaining / 3600);
            const minutes = Math.floor((remaining % 3600) / 60);
            const wait = `${hours ? `${hours} h ` : ""}${minutes ? `${minutes} min ` : ""}${remaining % 60} s`;
            status.textContent = `Fatture in Cloud richiede una pausa. Ripresa automatica tra ${wait}. ${summary}`;
            await new Promise((resolve) => {
                const timer = setTimeout(() => { wakeWait = null; resolve(); }, 1000);
                wakeWait = () => { clearTimeout(timer); wakeWait = null; resolve(); };
            });
        }
        return false;
    };

    const updatePeriod = () => {
        const custom = period.value === "manuale";
        manual.hidden = !custom;
        manualEnd.hidden = !custom;
        rangeHelp.hidden = !custom;
        date.disabled = !custom;
        endDate.disabled = !custom;
        date.required = custom;
        endDate.min = custom ? date.value : "";
    };
    period.addEventListener("change", updatePeriod);
    date.addEventListener("input", updatePeriod);
    updatePeriod();
    pause.addEventListener("click", () => {
        pauseRequested = true;
        pause.disabled = true;
        if (wakeWait) wakeWait();
        else status.textContent = "Pausa richiesta: completo le fatture in elaborazione…";
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (running || !form.reportValidity()) return;
        const body = new FormData(form);
        let created = 0;
        let updated = 0;
        running = true;
        pauseRequested = false;
        submit.disabled = true;
        period.disabled = true;
        date.disabled = true;
        endDate.disabled = true;
        pause.hidden = false;
        pause.disabled = false;
        status.classList.remove("is-error");
        status.textContent = "Importazione in corso…";
        try {
            while (true) {
                const response = await fetch(form.action, {
                    method: "POST", body, credentials: "same-origin",
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                });
                if (!response.headers.get("content-type")?.includes("application/json")) {
                    throw new Error("Risposta non disponibile. Ricarica la pagina e riprendi l'importazione.");
                }
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || "Importazione non riuscita. Riprova.");
                created += result.creati || 0;
                updated += result.aggiornati || 0;
                const summary = `${created} fatture nuove, ${updated} aggiornate.`;
                if (result.in_attesa_limite) {
                    if (await waitForRetry(result.riprova_tra_secondi, summary)) continue;
                    status.textContent = `Importazione in pausa: ${summary} Premi Continua importazione per riprendere.`;
                    submit.querySelector(".btn-label").textContent = "Continua importazione";
                    break;
                }
                if (!result.interrotta_per_tempo) {
                    const partial = result.esito === "parziale";
                    status.classList.toggle("is-error", partial);
                    status.textContent = `${partial ? "Importazione parziale" : "Importazione completata"}: ${summary}`;
                    if (partial) status.textContent += " " + (result.messaggi || []).join(" ");
                    submit.querySelector(".btn-label").textContent = partial ? "Riprova importazione" : "Sincronizza ora";
                    break;
                }
                if (pauseRequested || !result.avanzato) {
                    status.textContent = `Importazione in pausa: ${summary} Premi Continua importazione per riprendere.`;
                    submit.querySelector(".btn-label").textContent = "Continua importazione";
                    break;
                }
                status.textContent = `Importazione in corso: ${summary} Continuo con le altre fatture…`;
            }
        } catch (error) {
            status.classList.add("is-error");
            status.textContent = error.message;
            submit.querySelector(".btn-label").textContent = "Riprendi importazione";
        } finally {
            running = false;
            submit.disabled = false;
            period.disabled = false;
            pause.hidden = true;
            updatePeriod();
        }
    });
})();
