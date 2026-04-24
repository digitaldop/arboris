window.ArborisCopyActions = (function () {
    function fallbackCopyText(text) {
        if (text === undefined || text === null || text === "") {
            return false;
        }

        const helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "readonly");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();

        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (error) {
            copied = false;
        }

        document.body.removeChild(helper);
        return copied;
    }

    async function copyText(text) {
        if (text === undefined || text === null || text === "") {
            return false;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (error) {
                return fallbackCopyText(text);
            }
        }

        return fallbackCopyText(text);
    }

    function showCopiedState(button) {
        button.classList.add("is-copied");

        window.setTimeout(function () {
            button.classList.remove("is-copied");
        }, 1200);
    }

    function init(container = document) {
        container.querySelectorAll("[data-copy-text]").forEach(button => {
            if (button.dataset.copyBound === "1") {
                return;
            }

            button.dataset.copyBound = "1";
            button.addEventListener("click", async function (event) {
                event.preventDefault();
                event.stopPropagation();

                const copied = await copyText(button.dataset.copyText);
                if (copied) {
                    showCopiedState(button);
                }
            });
        });
    }

    return {
        init,
    };
})();
