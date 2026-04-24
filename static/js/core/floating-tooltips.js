window.ArborisFloatingTooltips = (function () {
    let tooltipEl = null;
    let activeTrigger = null;

    function ensureTooltip() {
        if (tooltipEl) {
            return tooltipEl;
        }

        tooltipEl = document.createElement("div");
        tooltipEl.className = "floating-tooltip";
        tooltipEl.setAttribute("role", "tooltip");
        tooltipEl.innerHTML = '<div class="floating-tooltip__bubble"></div><div class="floating-tooltip__arrow"></div>';
        document.body.appendChild(tooltipEl);
        return tooltipEl;
    }

    function getTooltipText(trigger) {
        if (!trigger) {
            return "";
        }

        if (trigger.dataset.floatingText) {
            return trigger.dataset.floatingText.trim();
        }

        const inlineTooltip = trigger.querySelector(".copy-inline-tooltip");
        if (inlineTooltip && inlineTooltip.textContent) {
            return inlineTooltip.textContent.trim();
        }

        if (trigger.title) {
            return trigger.title.trim();
        }

        return "";
    }

    function positionTooltip(trigger) {
        if (!tooltipEl || !trigger) {
            return;
        }

        const bubble = tooltipEl.querySelector(".floating-tooltip__bubble");
        const triggerRect = trigger.getBoundingClientRect();

        tooltipEl.classList.remove("is-below");
        tooltipEl.style.left = "0px";
        tooltipEl.style.top = "0px";

        const tooltipRect = tooltipEl.getBoundingClientRect();
        const spacing = 10;
        const viewportPadding = 8;

        let left = triggerRect.left + (triggerRect.width / 2) - (tooltipRect.width / 2);
        left = Math.max(viewportPadding, Math.min(left, window.innerWidth - tooltipRect.width - viewportPadding));

        let top = triggerRect.top - tooltipRect.height - spacing;
        const shouldPlaceBelow = top < viewportPadding;

        if (shouldPlaceBelow) {
            tooltipEl.classList.add("is-below");
            top = triggerRect.bottom + spacing;
        }

        tooltipEl.style.left = `${left}px`;
        tooltipEl.style.top = `${Math.max(viewportPadding, top)}px`;
        bubble.textContent = getTooltipText(trigger);
    }

    function showTooltip(trigger) {
        const text = getTooltipText(trigger);
        if (!text) {
            return;
        }

        activeTrigger = trigger;
        ensureTooltip();
        tooltipEl.querySelector(".floating-tooltip__bubble").textContent = text;
        tooltipEl.classList.add("is-visible");
        positionTooltip(trigger);
    }

    function hideTooltip(trigger) {
        if (!tooltipEl) {
            return;
        }

        if (trigger && activeTrigger && trigger !== activeTrigger) {
            return;
        }

        tooltipEl.classList.remove("is-visible");
        tooltipEl.classList.remove("is-below");
        activeTrigger = null;
    }

    function bindDelegatedEvents(root = document) {
        if (root.documentElement && root.documentElement.dataset.floatingTooltipsBound === "1") {
            return;
        }

        if (root.documentElement) {
            root.documentElement.dataset.floatingTooltipsBound = "1";
        }

        root.addEventListener("mouseover", function (event) {
            const trigger = event.target.closest("[data-floating-text], [title], .copy-inline-btn");
            if (!trigger) {
                return;
            }

            if (trigger.contains(event.relatedTarget)) {
                return;
            }

            showTooltip(trigger);
        });

        root.addEventListener("mouseout", function (event) {
            const trigger = event.target.closest("[data-floating-text], [title], .copy-inline-btn");
            if (!trigger) {
                return;
            }

            if (trigger.contains(event.relatedTarget)) {
                return;
            }

            hideTooltip(trigger);
        });

        root.addEventListener("focusin", function (event) {
            const trigger = event.target.closest("[data-floating-text], [title], .copy-inline-btn");
            if (trigger) {
                showTooltip(trigger);
            }
        });

        root.addEventListener("focusout", function (event) {
            const trigger = event.target.closest("[data-floating-text], [title], .copy-inline-btn");
            if (trigger) {
                hideTooltip(trigger);
            }
        });

        window.addEventListener("scroll", function () {
            if (activeTrigger) {
                positionTooltip(activeTrigger);
            }
        }, true);

        window.addEventListener("resize", function () {
            if (activeTrigger) {
                positionTooltip(activeTrigger);
            }
        });
    }

    function init(root = document) {
        bindDelegatedEvents(root);
    }

    return {
        init,
        show: showTooltip,
        hide: hideTooltip,
    };
})();
