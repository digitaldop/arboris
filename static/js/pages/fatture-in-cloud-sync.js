(() => {
    const form = document.getElementById("fic-sync-form");
    if (!form) return;
    const period = form.elements.periodo;
    const date = form.elements.data_inizio;
    const manual = document.getElementById("fic-manual-date");
    const submit = document.getElementById("fic-sync-submit");
    const pause = document.getElementById("fic-sync-pause");
    const status = document.getElementById("fic-sync-status");
    let running = false;
    let pauseRequested = false;

    const updatePeriod = () => {
        const custom = period.value === "manuale";
        manual.hidden = !custom;
        date.disabled = !custom;
        date.required = custom;
    };
    period.addEventListener("change", updatePeriod);
    updatePeriod();
    pause.addEventListener("click", () => {
        pauseRequested = true;
        pause.disabled = true;
        status.textContent = "Pausa richiesta: completo le fatture in elaborazione…";
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
