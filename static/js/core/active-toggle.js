(function () {
    function cookieValue(name) {
        const cookies = document.cookie ? document.cookie.split(";") : [];
        for (let index = 0; index < cookies.length; index += 1) {
            const cookie = cookies[index].trim();
            if (cookie.startsWith(name + "=")) {
                return decodeURIComponent(cookie.slice(name.length + 1));
            }
        }
        return "";
    }

    function setToggleLabel(toggle) {
        const form = toggle.closest("[data-active-toggle-form]");
        const label = form ? form.querySelector("[data-active-toggle-label]") : null;
        if (!label) return;
        label.textContent = toggle.checked ? toggle.dataset.activeLabel : toggle.dataset.inactiveLabel;
    }

    function toggleState(toggle, checked) {
        toggle.checked = checked;
        setToggleLabel(toggle);
    }

    function submitToggle(toggle) {
        const form = toggle.closest("[data-active-toggle-form]");
        if (!form || form.classList.contains("is-saving")) return;

        const previousValue = !toggle.checked;
        const data = new FormData(form);
        data.set("value", toggle.checked ? "1" : "0");
        data.set("ajax", "1");

        form.classList.add("is-saving");
        toggle.disabled = true;
        setToggleLabel(toggle);

        fetch(form.action, {
            method: "POST",
            body: data,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": data.get("csrfmiddlewaretoken") || cookieValue("csrftoken"),
            },
            credentials: "same-origin",
        })
            .then(function (response) {
                return response.json().then(function (payload) {
                    if (!response.ok || !payload.ok) {
                        throw new Error(payload.message || "Stato non aggiornato.");
                    }
                    return payload;
                });
            })
            .then(function (payload) {
                toggleState(toggle, Boolean(payload.value));
                form.classList.toggle("is-off", !payload.value);
                form.classList.toggle("is-on", Boolean(payload.value));

                if (form.dataset.activeToggleReload === "1") {
                    window.location.reload();
                }
            })
            .catch(function (error) {
                toggleState(toggle, previousValue);
                window.alert(error.message || "Non e' stato possibile aggiornare lo stato.");
            })
            .finally(function () {
                form.classList.remove("is-saving");
                if (!form.classList.contains("is-readonly")) {
                    toggle.disabled = false;
                }
            });
    }

    document.addEventListener("change", function (event) {
        const toggle = event.target.closest("[data-active-toggle]");
        if (!toggle) return;
        submitToggle(toggle);
    });
})();
