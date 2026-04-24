window.ArborisRichNotes = (function () {
    const UNDERLINE_PATTERN = /__(.+?)__/gs;
    const BOLD_PATTERN = /\*\*(.+?)\*\*/gs;
    const ITALIC_PATTERN = /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/gs;
    const BLOCK_TAGS = new Set(["DIV", "P", "LI"]);
    let observer = null;
    let refreshQueued = false;

    function escapeHtml(value) {
        return value
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function renderRichNotesHtml(value) {
        const text = value == null ? "" : String(value);
        if (!text.trim()) {
            return "";
        }

        let html = escapeHtml(text);
        html = html.replace(UNDERLINE_PATTERN, "<u>$1</u>");
        html = html.replace(BOLD_PATTERN, "<strong>$1</strong>");
        html = html.replace(ITALIC_PATTERN, "<em>$1</em>");
        html = html.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/\n/g, "<br>");
        return html;
    }

    function normalizeText(value) {
        return (value || "")
            .replace(/\u00a0/g, " ")
            .replace(/\u200b/g, "")
            .replace(/\r\n/g, "\n")
            .replace(/\r/g, "\n")
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n[ \t]+/g, "\n")
            .replace(/\n{3,}/g, "\n\n");
    }

    function isRichNoteTextarea(textarea) {
        if (!textarea || textarea.tagName !== "TEXTAREA") {
            return false;
        }

        if (textarea.dataset.richNotesSkip === "true") {
            return false;
        }

        const source = `${textarea.name || ""} ${textarea.id || ""}`.toLowerCase();
        return source.includes("note");
    }

    function isReadonly(textarea) {
        if (!textarea) {
            return true;
        }

        return Boolean(
            textarea.disabled ||
            textarea.readOnly ||
            textarea.closest("fieldset[disabled]")
        );
    }

    function createToolbarButton(label, command, title) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "rich-note-toolbar-btn";
        button.textContent = label;
        button.dataset.command = command;
        button.setAttribute("aria-label", title);
        button.setAttribute("title", title);
        return button;
    }

    function insertPlainText(text) {
        const selection = window.getSelection();
        if (!selection || !selection.rangeCount) {
            return;
        }

        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(text);
        range.insertNode(textNode);
        range.setStartAfter(textNode);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function serializeChildren(parent) {
        let result = "";

        Array.from(parent.childNodes).forEach((node, index, nodes) => {
            const serialized = serializeNode(node);
            const isBlockElement = node.nodeType === Node.ELEMENT_NODE && BLOCK_TAGS.has(node.tagName);

            if (!serialized && !isBlockElement) {
                return;
            }

            if (isBlockElement) {
                const content = serialized.replace(/\n+$/g, "");
                if (content) {
                    if (result && !result.endsWith("\n")) {
                        result += "\n";
                    }
                    result += content;
                }

                const hasMoreSiblings = nodes.slice(index + 1).some((sibling) => {
                    if (sibling.nodeType === Node.TEXT_NODE) {
                        return Boolean(normalizeText(sibling.nodeValue).trim());
                    }

                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === "BR") {
                        return true;
                    }

                    return Boolean(serializeNode(sibling).trim());
                });

                if (content && hasMoreSiblings) {
                    result += "\n";
                }

                return;
            }

            result += serialized;
        });

        return result;
    }

    function serializeNode(node) {
        if (!node) {
            return "";
        }

        if (node.nodeType === Node.TEXT_NODE) {
            return normalizeText(node.nodeValue);
        }

        if (node.nodeType !== Node.ELEMENT_NODE) {
            return "";
        }

        const tagName = node.tagName;

        if (tagName === "BR") {
            return "\n";
        }

        const content = serializeChildren(node);

        if (tagName === "STRONG" || tagName === "B") {
            return content ? `**${content}**` : "";
        }

        if (tagName === "EM" || tagName === "I") {
            return content ? `*${content}*` : "";
        }

        if (tagName === "U") {
            return content ? `__${content}__` : "";
        }

        return content;
    }

    function serializeEditor(editor) {
        return normalizeText(serializeChildren(editor)).replace(/\n+$/g, "");
    }

    function setEditorHtml(editor, value) {
        const html = renderRichNotesHtml(value);
        editor.innerHTML = html || "";
    }

    function syncTextareaFromEditor(textarea) {
        const wrapper = textarea.closest(".rich-note-field");
        const editor = wrapper ? wrapper.querySelector(".rich-note-editor") : null;
        if (!editor) {
            return;
        }

        const serializedValue = serializeEditor(editor);
        textarea.value = serializedValue;
        textarea.dataset.richNotesLastValue = serializedValue;
    }

    function syncEditorFromTextarea(textarea, force) {
        const wrapper = textarea.closest(".rich-note-field");
        const editor = wrapper ? wrapper.querySelector(".rich-note-editor") : null;
        if (!editor) {
            return;
        }

        const currentValue = textarea.value || "";
        const lastValue = textarea.dataset.richNotesLastValue || "";
        const isFocused = document.activeElement === editor;

        if (!force && isFocused && currentValue === lastValue) {
            return;
        }

        if (!force && currentValue === lastValue && editor.innerHTML !== "") {
            return;
        }

        setEditorHtml(editor, currentValue);
        textarea.dataset.richNotesLastValue = currentValue;
    }

    function applyCommand(editor, command) {
        editor.focus();

        if (typeof document.execCommand === "function") {
            document.execCommand(command, false, null);
        }
    }

    function buildField(textarea) {
        const wrapper = document.createElement("div");
        wrapper.className = "rich-note-field";

        const toolbar = document.createElement("div");
        toolbar.className = "rich-note-toolbar";
        toolbar.setAttribute("role", "toolbar");
        toolbar.appendChild(createToolbarButton("B", "bold", "Grassetto"));
        toolbar.appendChild(createToolbarButton("I", "italic", "Corsivo"));
        toolbar.appendChild(createToolbarButton("U", "underline", "Sottolineato"));

        const editor = document.createElement("div");
        editor.className = "rich-note-editor";
        editor.contentEditable = "true";
        editor.setAttribute("role", "textbox");
        editor.setAttribute("aria-multiline", "true");

        const preview = document.createElement("div");
        preview.className = "rich-note-preview";

        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(toolbar);
        wrapper.appendChild(editor);
        wrapper.appendChild(preview);
        wrapper.appendChild(textarea);

        toolbar.addEventListener("click", function (event) {
            const button = event.target.closest(".rich-note-toolbar-btn");
            if (!button) {
                return;
            }

            applyCommand(editor, button.dataset.command || "");
            syncTextareaFromEditor(textarea);
        });

        toolbar.addEventListener("mousedown", function (event) {
            if (event.target.closest(".rich-note-toolbar-btn")) {
                event.preventDefault();
            }
        });

        editor.addEventListener("input", function () {
            syncTextareaFromEditor(textarea);
        });

        editor.addEventListener("blur", function () {
            syncTextareaFromEditor(textarea);
        });

        editor.addEventListener("paste", function (event) {
            const clipboardText = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
            if (!clipboardText) {
                return;
            }

            event.preventDefault();
            editor.focus();

            if (typeof document.execCommand === "function") {
                document.execCommand("insertText", false, clipboardText);
            } else {
                insertPlainText(clipboardText);
            }

            syncTextareaFromEditor(textarea);
        });

        textarea.addEventListener("input", function () {
            syncEditorFromTextarea(textarea, false);
        });

        textarea.classList.add("rich-note-source");
        textarea.dataset.richNotesBound = "1";
        textarea.dataset.richNotesLastValue = textarea.value || "";
        setEditorHtml(editor, textarea.value || "");
    }

    function enhanceTextarea(textarea) {
        if (!isRichNoteTextarea(textarea) || textarea.dataset.richNotesBound === "1") {
            return;
        }

        buildField(textarea);
    }

    function refreshTextarea(textarea) {
        if (!isRichNoteTextarea(textarea)) {
            return;
        }

        const wrapper = textarea.closest(".rich-note-field");
        if (!wrapper) {
            return;
        }

        const toolbar = wrapper.querySelector(".rich-note-toolbar");
        const editor = wrapper.querySelector(".rich-note-editor");
        const preview = wrapper.querySelector(".rich-note-preview");
        const readonly = isReadonly(textarea);

        if (!toolbar || !editor || !preview) {
            return;
        }

        syncEditorFromTextarea(textarea, false);

        wrapper.classList.toggle("is-readonly", readonly);
        toolbar.hidden = readonly;
        editor.hidden = readonly;
        preview.hidden = !readonly;

        if (readonly) {
            preview.innerHTML = renderRichNotesHtml(textarea.value || "");
        }
    }

    function enhance(root) {
        const scope = root || document;
        scope.querySelectorAll("textarea").forEach(enhanceTextarea);
    }

    function refresh(root) {
        const scope = root || document;
        scope.querySelectorAll('textarea[data-rich-notes-bound="1"]').forEach(refreshTextarea);
    }

    function queueRefresh() {
        if (refreshQueued) {
            return;
        }

        refreshQueued = true;
        window.requestAnimationFrame(function () {
            refreshQueued = false;
            enhance(document);
            refresh(document);
        });
    }

    function startObserver() {
        if (observer || !document.body) {
            return;
        }

        observer = new MutationObserver(function () {
            queueRefresh();
        });

        observer.observe(document.body, {
            subtree: true,
            childList: true,
            attributes: true,
            attributeFilter: ["disabled", "readonly", "class"],
        });
    }

    function init(root) {
        enhance(root || document);
        refresh(root || document);
        startObserver();
    }

    return {
        init: init,
        refresh: refresh,
        renderHtml: renderRichNotesHtml,
    };
})();
