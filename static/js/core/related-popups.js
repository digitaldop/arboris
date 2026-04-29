window.ArborisRelatedPopups = (function () {
    function getPopupSize(url) {
        const normalizedUrl = String(url || "").toLowerCase();
        const viewportHeight = window.screen && window.screen.availHeight ? window.screen.availHeight : window.screen.height;
        const isAddressPopup = normalizedUrl.indexOf("/indirizzi/") !== -1;

        if (isAddressPopup) {
            return {
                width: 900,
                height: Math.max(760, Math.min(900, viewportHeight - 40)),
            };
        }

        return {
            width: 900,
            height: 700,
        };
    }

    function openRelatedPopup(url) {
        const size = getPopupSize(url);
        const width = size.width;
        const height = size.height;
        const left = Math.max(0, (window.screen.width - width) / 2);
        const top = Math.max(0, (window.screen.height - height) / 2);

        window.open(
            url,
            "related_popup",
            `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
        );
    }

    function findTargetSelect(fieldName, targetInputName) {
        if (targetInputName) {
            const exact = document.querySelector(`select[name="${targetInputName}"]`);
            if (exact) return exact;
        }

        const fallback = document.getElementById("id_" + fieldName);
        if (fallback) return fallback;

        const byName = document.querySelector(`select[name$="-${fieldName}"]`);
        if (byName) return byName;

        return null;
    }

    function dismissRelatedPopup(fieldName, objectId, objectLabel, targetInputName) {
        const select = findTargetSelect(fieldName, targetInputName);

        if (!select) {
            if (typeof window.ArborisReloadWithLongWait === "function") {
                window.ArborisReloadWithLongWait();
            } else {
                window.location.reload();
            }
            return;
        }

        let option = Array.from(select.options).find(opt => opt.value === String(objectId));

        if (!option) {
            option = document.createElement("option");
            option.value = String(objectId);
            option.textContent = objectLabel;
            select.appendChild(option);
        } else {
            option.textContent = objectLabel;
        }

        select.value = String(objectId);
        select.dispatchEvent(new Event("change"));
    }

    function dismissDeletedRelatedPopup(fieldName, objectId, targetInputName) {
        const select = findTargetSelect(fieldName, targetInputName);

        if (!select) {
            if (typeof window.ArborisReloadWithLongWait === "function") {
                window.ArborisReloadWithLongWait();
            } else {
                window.location.reload();
            }
            return;
        }

        const option = Array.from(select.options).find(opt => opt.value === String(objectId));
        const wasSelected = select.value === String(objectId);

        if (option) {
            option.remove();
        }

        if (wasSelected) {
            select.value = "";
        }

        select.dispatchEvent(new Event("change"));
    }

    return {
        openRelatedPopup,
        findTargetSelect,
        dismissRelatedPopup,
        dismissDeletedRelatedPopup,
    };
})();
