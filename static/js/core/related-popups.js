window.ArborisRelatedPopups = (function () {
    let activePopupLock = null;
    let activePopupPoll = null;

    function getScreenMetrics() {
        const screenObj = window.screen || {};
        return {
            width: screenObj.availWidth || screenObj.width || window.innerWidth || 1200,
            height: screenObj.availHeight || screenObj.height || window.innerHeight || 800,
            left: screenObj.availLeft || 0,
            top: screenObj.availTop || 0,
        };
    }

    function isPopupContext() {
        return Boolean(
            (document.body && document.body.classList.contains("popup-page")) ||
            (window.opener && !window.opener.closed)
        );
    }

    function isReservedWindowName(windowName) {
        return ["_blank", "_self", "_parent", "_top"].indexOf(String(windowName || "").toLowerCase()) !== -1;
    }

    function createPopupToken() {
        return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function resolvePopupWindowName(windowName, options) {
        const baseName = windowName || "related_popup";
        if (isReservedWindowName(baseName)) {
            return baseName;
        }

        const cfg = options || {};
        if (cfg.forceUnique || isPopupContext() || window.name === baseName) {
            return `${baseName}-child-${createPopupToken()}`;
        }

        return baseName;
    }

    function getModalPopupApi() {
        try {
            if (window.top && window.top.ArborisModalPopups) {
                return window.top.ArborisModalPopups;
            }
        } catch (error) {
            // Cross-window access can fail outside the application origin.
        }

        return window.ArborisModalPopups || null;
    }

    function clampPopupDimension(desired, minimum, available) {
        const maxAvailable = Math.max(320, available || desired);
        if (maxAvailable < minimum) {
            return maxAvailable;
        }
        return Math.max(minimum, Math.min(desired, maxAvailable));
    }

    function getPopupSize(url) {
        const normalizedUrl = String(url || "").toLowerCase();
        const screenMetrics = getScreenMetrics();
        const maxWidth = screenMetrics.width - 24;
        const maxHeight = screenMetrics.height - 24;
        const isAddressPopup = normalizedUrl.indexOf("/indirizzi/") !== -1;
        const isRelationPopup = normalizedUrl.indexOf("/relazioni-familiari/") !== -1;
        const isFamilyStatusPopup = normalizedUrl.indexOf("/stati-relazione-famiglia/") !== -1;
        const isFamilyPopup = normalizedUrl.indexOf("/famiglie/") !== -1 && normalizedUrl.indexOf("popup=1") !== -1;

        if (isAddressPopup) {
            return {
                width: clampPopupDimension(1120, 900, maxWidth),
                height: clampPopupDimension(1040, 900, maxHeight),
            };
        }

        if (isRelationPopup) {
            return {
                width: clampPopupDimension(1120, 900, maxWidth),
                height: clampPopupDimension(980, 860, maxHeight),
            };
        }

        if (isFamilyStatusPopup) {
            return {
                width: clampPopupDimension(1120, 900, maxWidth),
                height: clampPopupDimension(1040, 900, maxHeight),
            };
        }

        if (isFamilyPopup) {
            return {
                width: clampPopupDimension(1120, 900, maxWidth),
                height: clampPopupDimension(880, 760, maxHeight),
            };
        }

        return {
            width: clampPopupDimension(900, 760, maxWidth),
            height: clampPopupDimension(700, 620, maxHeight),
        };
    }

    function focusPopup(popupWindow) {
        try {
            if (popupWindow && !popupWindow.closed) {
                popupWindow.focus();
            }
        } catch (error) {
            // Cross-window focus can fail silently in some browser policies.
        }
    }

    function isActivePopupStillOpen() {
        try {
            return Boolean(activePopupLock && activePopupLock.popupWindow && !activePopupLock.popupWindow.closed);
        } catch (error) {
            return false;
        }
    }

    function unlockPopupWindow() {
        if (activePopupPoll) {
            window.clearInterval(activePopupPoll);
            activePopupPoll = null;
        }

        if (!activePopupLock) {
            return;
        }

        document.removeEventListener("keydown", blockLockedWindowInteraction, true);
        document.removeEventListener("focusin", keepFocusOnLockOverlay, true);

        if (activePopupLock.overlay && activePopupLock.overlay.parentNode) {
            activePopupLock.overlay.parentNode.removeChild(activePopupLock.overlay);
        }

        if (document.body) {
            document.body.classList.remove("related-popup-lock-active");
        }

        activePopupLock = null;
    }

    function blockLockedWindowInteraction(event) {
        if (!activePopupLock) {
            return;
        }

        if (!isActivePopupStillOpen()) {
            unlockPopupWindow();
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        focusPopup(activePopupLock.popupWindow);
    }

    function keepFocusOnLockOverlay(event) {
        if (!activePopupLock) {
            return;
        }

        if (!isActivePopupStillOpen()) {
            unlockPopupWindow();
            return;
        }

        if (activePopupLock.overlay && activePopupLock.overlay.contains(event.target)) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        if (activePopupLock.overlay && typeof activePopupLock.overlay.focus === "function") {
            activePopupLock.overlay.focus({ preventScroll: true });
        }
        focusPopup(activePopupLock.popupWindow);
    }

    function lockWindowUntilPopupCloses(popupWindow, message) {
        if (!popupWindow || popupWindow.closed || !document.body) {
            return;
        }

        unlockPopupWindow();

        const overlay = document.createElement("div");
        overlay.className = "related-popup-lock-overlay";
        overlay.tabIndex = 0;
        overlay.setAttribute("aria-live", "polite");

        const card = document.createElement("div");
        card.className = "related-popup-lock-card";
        card.setAttribute("role", "status");

        const title = document.createElement("span");
        title.className = "related-popup-lock-title";
        title.textContent = "Popup attivo";

        const body = document.createElement("span");
        body.className = "related-popup-lock-message";
        body.textContent = message || "Completa il popup aperto per continuare.";

        card.appendChild(title);
        card.appendChild(body);
        overlay.appendChild(card);

        overlay.addEventListener("mousedown", function (event) {
            event.preventDefault();
            focusPopup(popupWindow);
        });
        overlay.addEventListener("click", function (event) {
            event.preventDefault();
            focusPopup(popupWindow);
        });

        activePopupLock = {
            popupWindow: popupWindow,
            overlay: overlay,
        };

        document.body.classList.add("related-popup-lock-active");
        document.body.appendChild(overlay);
        overlay.focus({ preventScroll: true });

        document.addEventListener("keydown", blockLockedWindowInteraction, true);
        document.addEventListener("focusin", keepFocusOnLockOverlay, true);

        activePopupPoll = window.setInterval(function () {
            if (!isActivePopupStillOpen()) {
                unlockPopupWindow();
            }
        }, 250);
    }

    function openManagedPopup(url, windowName, features, options) {
        if (typeof window.ArborisResetLongWaitCursor === "function") {
            window.ArborisResetLongWaitCursor();
        }

        const cfg = options || {};
        const baseName = windowName || "related_popup";
        const modalPopups = getModalPopupApi();
        if (cfg.lightbox !== false && modalPopups && typeof modalPopups.open === "function" && !isReservedWindowName(baseName)) {
            const modalHandle = modalPopups.open(url, {
                features: features || "width=760,height=680,resizable=yes,scrollbars=yes",
                openerWindow: window,
                title: cfg.title || "Popup Arboris",
                windowName: baseName,
            });
            if (modalHandle) {
                return modalHandle;
            }
        }

        const popupName = resolvePopupWindowName(windowName || "related_popup", cfg);
        const popupWindow = window.open(
            url,
            popupName,
            features || "width=760,height=680,resizable=yes,scrollbars=yes"
        );

        if (popupWindow && !popupWindow.closed) {
            focusPopup(popupWindow);
            if (cfg.lockOpener !== false) {
                lockWindowUntilPopupCloses(popupWindow, cfg.lockMessage);
            }
        }

        return popupWindow;
    }

    function openRelatedPopup(url) {
        const screenMetrics = getScreenMetrics();
        const size = getPopupSize(url);
        const width = size.width;
        const height = size.height;
        const left = screenMetrics.left + Math.max(0, (screenMetrics.width - width) / 2);
        const top = screenMetrics.top + Math.max(0, (screenMetrics.height - height) / 2);

        return openManagedPopup(
            url,
            "related_popup",
            `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`,
            {
                forceUnique: isPopupContext(),
                lockMessage: "Completa il popup aperto per continuare.",
            }
        );
    }

    function findTargetSelect(fieldName, targetInputName) {
        if (targetInputName) {
            const exact = document.querySelector(`select[name="${targetInputName}"]`);
            if (exact) return exact;

            const byExplicitId = document.getElementById(targetInputName);
            if (byExplicitId && byExplicitId instanceof HTMLSelectElement) return byExplicitId;
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
        openManagedPopup,
        findTargetSelect,
        dismissRelatedPopup,
        dismissDeletedRelatedPopup,
    };
})();
