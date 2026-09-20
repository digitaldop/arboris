document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-payroll-period-toggle]").forEach(function (toggle) {
        const form = toggle.form;
        const solarYear = form.querySelector("[data-payroll-solar-year]");
        const schoolYear = form.querySelector("[data-payroll-school-year]");
        toggle.addEventListener("change", function () {
            const solarMemory = form.querySelector("[data-payroll-solar-memory]");
            const schoolMemory = form.querySelector("[data-payroll-school-memory]");
            solarMemory.value = solarYear.querySelector("input").value;
            schoolMemory.value = schoolYear.querySelector("select").value;
            solarMemory.disabled = !toggle.checked;
            schoolMemory.disabled = toggle.checked;
            solarYear.hidden = toggle.checked;
            schoolYear.hidden = !toggle.checked;
            solarYear.querySelector("input").disabled = toggle.checked;
            schoolYear.querySelector("select").disabled = !toggle.checked;
            form.requestSubmit();
        });
    });
    document.querySelectorAll("[data-payroll-auto-submit]").forEach(function (field) {
        field.addEventListener("change", function () {
            field.form.requestSubmit();
        });
    });
});
