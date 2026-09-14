(function () {
    "use strict";
    const form = document.getElementById("family-communication-form");
    if (!form) return;
    const cards = Array.from(form.querySelectorAll("[data-recipient-classes]"));
    const recipients = Array.from(form.querySelectorAll('input[name="destinatari"]'));
    const classes = Array.from(form.querySelectorAll('input[name="classi"]'));
    const allMode = form.querySelector('[name="ambito_destinatari"][value="tutti"]');
    const classMode = form.querySelector('[name="ambito_destinatari"][value="classi"]');
    const years = Array.from(form.querySelectorAll('input[name="anni_scolastici"]'));
    const renderedYears = Array.from(form.querySelectorAll('[name="anni_destinatari"]')).map(item => item.value).sort().join(",");
    const summary = form.querySelector("[data-selection-summary]");
    const sendButtons = form.querySelectorAll('[name="action"][value="send"], [data-open-mail-client]');
    let submitting = false;

    function yearsChanged() {
        return years.filter(item => item.checked).map(item => item.value).sort().join(",") !== renderedYears;
    }
    function selectedRecipients() {
        return recipients.filter(item => item.checked && !item.disabled);
    }
    function emailOf(item) {
        return (item.dataset.recipientEmail || "").trim().toLowerCase();
    }
    function selectedEmails() {
        return Array.from(new Set(selectedRecipients().map(emailOf).filter(Boolean)));
    }
    function updateSelection() {
        const count = selectedRecipients().length;
        const unique = selectedEmails().length;
        summary.textContent = (count === 1 ? "1 destinatario selezionato" : count + " destinatari selezionati")
            + " · " + (unique === 1 ? "1 indirizzo email unico" : unique + " indirizzi email unici");
        const changed = yearsChanged();
        form.querySelector("[data-years-changed]").hidden = !changed;
        sendButtons.forEach(button => { button.disabled = submitting || changed || unique === 0; });
    }
    function applyFilters(selectMatching) {
        const filter = new Set(classes.filter(item => item.checked).map(item => item.value));
        const useClasses = classMode && classMode.checked;
        let studentCount = 0;
        cards.forEach(card => {
            const visible = !useClasses || card.dataset.recipientClasses.split(" ").some(key => filter.has(key));
            card.hidden = !visible;
            if (visible) studentCount += 1;
            card.querySelectorAll('input[name="destinatari"]').forEach(box => {
                box.disabled = !visible;
                if (!visible || selectMatching) box.checked = visible;
            });
        });
        const visibleRecipients = recipients.filter(item => !item.disabled);
        const emails = new Map();
        visibleRecipients.forEach(box => { const key = emailOf(box); emails.set(key, (emails.get(key) || 0) + 1); });
        visibleRecipients.forEach(box => {
            const duplicate = emails.get(emailOf(box)) > 1;
            const label = box.closest("label");
            label.classList.toggle("is-duplicate", duplicate);
            const chip = label.querySelector("[data-duplicate-chip]");
            chip.classList.toggle("family-communication-chip-placeholder", !duplicate);
            chip.setAttribute("aria-hidden", String(!duplicate));
        });
        const stats = {studenti: studentCount, destinatari: visibleRecipients.length, email_uniche: emails.size, duplicati: visibleRecipients.length - emails.size};
        form.querySelectorAll("[data-recipient-stat]").forEach(node => { node.textContent = stats[node.dataset.recipientStat]; });
        form.querySelector("[data-no-recipients]").hidden = studentCount > 0;
        updateSelection();
    }
    classes.forEach(box => box.addEventListener("change", function () {
        classMode.checked = true;
        applyFilters(true);
    }));
    [allMode, classMode].filter(Boolean).forEach(radio => radio.addEventListener("change", function () {
        if (allMode.checked) classes.forEach(box => { box.checked = false; });
        applyFilters(true);
    }));
    recipients.forEach(box => box.addEventListener("change", updateSelection));
    years.forEach(box => box.addEventListener("change", updateSelection));
    form.querySelectorAll("[data-recipient-action]").forEach(button => button.addEventListener("click", function () {
        const checked = button.dataset.recipientAction === "select-all";
        recipients.forEach(box => { box.checked = checked && !box.disabled; });
        updateSelection();
    }));
    form.addEventListener("submit", function (event) {
        if (event.submitter && event.submitter.value === "send") {
            if (submitting || yearsChanged() || !selectedEmails().length) {
                event.preventDefault();
                return;
            }
            submitting = true;
            // Preserve the submitter's name/value until form serialization.
            window.setTimeout(updateSelection, 0);
        }
    });
    form.querySelectorAll("[data-open-mail-client]").forEach(button => button.addEventListener("click", function () {
        const emails = selectedEmails();
        if (!emails.length || yearsChanged()) return;
        const subject = form.querySelector('[name="oggetto"]').value.trim();
        const body = form.querySelector('[name="messaggio"]').value.trim();
        function mailto(includeBody) {
            const params = ["bcc=" + encodeURIComponent(emails.join(","))];
            if (subject) params.push("subject=" + encodeURIComponent(subject));
            if (includeBody && body) params.push("body=" + encodeURIComponent(body));
            return "mailto:?" + params.join("&");
        }
        let url = mailto(true);
        if (url.length > 1800 && body) url = mailto(false);
        if (url.length > 1800) {
            window.alert("Troppi indirizzi per aprire il client email tramite link. Riduci la selezione oppure usa l'invio da Arboris.");
            return;
        }
        window.location.href = url;
    }));
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) { submitting = false; applyFilters(false); }
    });
    applyFilters(false);
})();
