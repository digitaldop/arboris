window.ArborisBetaFeedback = (function () {
    function init() {
        const widget = document.querySelector(".beta-feedback-widget");
        const dialog = document.getElementById("beta-feedback-dialog");
        const form = document.getElementById("beta-feedback-form");
        if (!widget || !dialog || !form) {
            return;
        }

        const endpoint = widget.dataset.feedbackEndpoint || "";
        const title = document.getElementById("beta-feedback-title");
        const typeInput = document.getElementById("beta-feedback-type");
        const messageInput = document.getElementById("beta-feedback-message");
        const status = document.getElementById("beta-feedback-status");
        const submitButton = document.getElementById("beta-feedback-submit");
        const pageUrlInput = document.getElementById("beta-feedback-page-url");
        const pagePathInput = document.getElementById("beta-feedback-page-path");
        const pageTitleInput = document.getElementById("beta-feedback-page-title");
        const breadcrumbInput = document.getElementById("beta-feedback-breadcrumb");
        let lastTrigger = null;

        function breadcrumbText() {
            const breadcrumb = document.querySelector(".breadcrumb");
            if (!breadcrumb) {
                return "";
            }
            return Array.from(breadcrumb.querySelectorAll("a, span"))
                .map(item => item.textContent.trim())
                .filter(Boolean)
                .filter(text => text !== ">")
                .join(" > ");
        }

        function setPageContext() {
            pageUrlInput.value = window.location.href;
            pagePathInput.value = `${window.location.pathname}${window.location.search}${window.location.hash}`;
            pageTitleInput.value = document.title || "";
            breadcrumbInput.value = breadcrumbText();
        }

        function setStatus(message, kind) {
            status.textContent = message || "";
            status.classList.remove("is-success", "is-error");
            if (kind) {
                status.classList.add(kind === "error" ? "is-error" : "is-success");
            }
        }

        function setBusy(isBusy) {
            if (submitButton) {
                submitButton.disabled = isBusy;
            }
            if (messageInput) {
                messageInput.readOnly = isBusy;
            }
        }

        function openDialog(trigger) {
            lastTrigger = trigger || null;
            typeInput.value = trigger.dataset.feedbackType || "";
            title.textContent = trigger.dataset.feedbackTitle || "Feedback beta";
            messageInput.value = "";
            setStatus("", "");
            setPageContext();
            dialog.classList.remove("is-hidden");
            dialog.setAttribute("aria-hidden", "false");
            document.body.classList.add("beta-feedback-open");
            window.setTimeout(function () {
                messageInput.focus();
            }, 0);
        }

        function closeDialog() {
            dialog.classList.add("is-hidden");
            dialog.setAttribute("aria-hidden", "true");
            document.body.classList.remove("beta-feedback-open");
            setBusy(false);
            if (lastTrigger && typeof lastTrigger.focus === "function") {
                lastTrigger.focus({ preventScroll: true });
            }
        }

        widget.addEventListener("click", function (event) {
            const trigger = event.target.closest(".beta-feedback-trigger");
            if (!trigger) {
                return;
            }
            openDialog(trigger);
        });

        dialog.addEventListener("click", function (event) {
            if (event.target.closest("[data-feedback-close]")) {
                closeDialog();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !dialog.classList.contains("is-hidden")) {
                closeDialog();
            }
        });

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            if (!endpoint) {
                setStatus("Endpoint feedback non configurato.", "error");
                return;
            }
            setPageContext();
            setBusy(true);
            setStatus("Invio in corso...", "");

            fetch(endpoint, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            })
                .then(function (response) {
                    return response.json().catch(function () {
                        return {};
                    }).then(function (payload) {
                        if (!response.ok || !payload.ok) {
                            throw new Error(payload.message || "Invio non riuscito.");
                        }
                        return payload;
                    });
                })
                .then(function (payload) {
                    setStatus(payload.message || "Segnalazione inviata. Grazie!", "success");
                    window.setTimeout(closeDialog, 900);
                })
                .catch(function (error) {
                    setStatus(error.message || "Invio non riuscito.", "error");
                })
                .finally(function () {
                    setBusy(false);
                    if (window.ArborisResetLongWaitCursor) {
                        window.ArborisResetLongWaitCursor();
                    }
                });
        });
    }

    return {
        init: init,
    };
})();

document.addEventListener("DOMContentLoaded", function () {
    if (window.ArborisBetaFeedback) {
        window.ArborisBetaFeedback.init();
    }
});
