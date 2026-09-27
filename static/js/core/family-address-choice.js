(function () {
    "use strict";
    function apply(checkbox) {
        const choice = checkbox.closest(".family-address-choice");
        if (!choice) return;
        const wrapper = choice.closest(".inline-related-field") || choice.parentElement;
        wrapper.classList.toggle("uses-family-address", checkbox.checked);
    }
    document.addEventListener("change", function (event) {
        if (event.target.matches('.family-address-choice input[type="checkbox"]')) apply(event.target);
    });
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll('.family-address-choice input[type="checkbox"]').forEach(apply);
        new MutationObserver(function (records) {
            for (const record of records) for (const node of record.addedNodes) {
                if (node.nodeType !== 1) continue;
                node.querySelectorAll('.family-address-choice input[type="checkbox"]').forEach(apply);
            }
        }).observe(document.body, {childList: true, subtree: true});
    });
})();
