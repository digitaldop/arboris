document.addEventListener("DOMContentLoaded", function () {
    const city = document.getElementById("id_citta");
    const cap = document.getElementById("id_cap_scelto");
    const search = document.querySelector("[data-address-autocomplete]");
    if (!city || !cap || !search) return;
    let version = 0;
    city.addEventListener("change", async function () {
        const current = ++version, preferred = cap.value;
        if (!city.value) { cap.replaceChildren(new Option("Seleziona CAP", "")); return; }
        try {
            const url = new URL(search.dataset.cityUrl, location.origin);
            url.searchParams.set("id", city.value);
            const response = await fetch(url);
            const data = await response.json();
            if (current !== version) return;
            const item = (data.results || []).find(row => String(row.id) === city.value);
            cap.replaceChildren(new Option("Seleziona CAP", ""));
            (item ? item.caps : []).forEach(row => cap.add(new Option(row.codice, row.id)));
            if (preferred) cap.value = preferred;
            else if (item && item.caps.length === 1 && !document.getElementById("id_cap").value) cap.value = item.caps[0].id;
        } catch (_) { /* Manual CAP remains available. */ }
    });
});
