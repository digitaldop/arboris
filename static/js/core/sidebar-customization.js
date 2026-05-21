window.ArborisSidebarCustomization = (function () {
    const EMPTY_CONFIG = { version: 1, hidden: [], order: {}, custom_sections: [] };
    const HIDDEN_CLASS = "sidebar-customization-hidden";
    const CUSTOM_SECTION_ATTR = "sidebarCustomSection";
    const ICON_OPTIONS = [
        { value: "list", label: "Lista" },
        { value: "home", label: "Home" },
        { value: "calendar", label: "Calendario" },
        { value: "finance", label: "Finanze" },
        { value: "bank", label: "Banca" },
        { value: "coins", label: "Monete" },
        { value: "document", label: "Documento" },
        { value: "briefcase", label: "Lavoro" },
        { value: "user", label: "Utente" },
        { value: "family", label: "Famiglia" },
        { value: "student", label: "Studente" },
        { value: "settings", label: "Impostazioni" },
    ];

    let root = null;
    let config = cloneConfig(EMPTY_CONFIG);
    let hiddenKeys = new Set();
    let configUrl = "";
    let dialog = null;
    let treeContainer = null;
    let customContainer = null;
    let statusNode = null;
    let draggedTreeItem = null;

    function cloneConfig(value) {
        return JSON.parse(JSON.stringify(value || EMPTY_CONFIG));
    }

    function normalizeText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function safeDomId(value) {
        return String(value || "custom").replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 80) || "custom";
    }

    function stableId(prefix) {
        return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function getCookie(name) {
        const prefix = `${name}=`;
        return document.cookie
            .split(";")
            .map(part => part.trim())
            .find(part => part.startsWith(prefix))
            ?.slice(prefix.length) || "";
    }

    function csrfToken() {
        const field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return field ? field.value : getCookie("csrftoken");
    }

    function readInitialConfig() {
        const script = document.getElementById("sidebar-personalizzazione-config");
        if (!script) {
            return cloneConfig(EMPTY_CONFIG);
        }
        try {
            return { ...cloneConfig(EMPTY_CONFIG), ...JSON.parse(script.textContent || "{}") };
        } catch (error) {
            return cloneConfig(EMPTY_CONFIG);
        }
    }

    function uiIconSpriteUrl() {
        const body = document.body;
        if (body?.dataset.uiIconsUrl) {
            return body.dataset.uiIconsUrl;
        }
        const existingUse = document.querySelector('svg use[href*="arboris-ui-icons.svg"]');
        const existingHref = existingUse?.getAttribute("href") || "";
        if (existingHref.includes("#")) {
            return existingHref.split("#")[0];
        }
        return "/static/images/arboris-ui-icons.svg";
    }

    function uiIconHref(iconName) {
        return `${uiIconSpriteUrl()}#${iconName || "list"}`;
    }

    function appendIcon(target, iconName) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        svg.setAttribute("aria-hidden", "true");
        const href = uiIconHref(iconName);
        use.setAttribute("href", href);
        use.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", href);
        svg.appendChild(use);
        target.appendChild(svg);
    }

    function normalizedIconValue(value) {
        const iconValue = normalizeText(value) || "list";
        return ICON_OPTIONS.some(option => option.value === iconValue) ? iconValue : "list";
    }

    function updateIconPreview(preview, iconName) {
        preview.textContent = "";
        appendIcon(preview, normalizedIconValue(iconName));
    }

    function createIconPicker(value, onChange) {
        const picker = document.createElement("span");
        picker.className = "sidebar-customization-icon-picker";

        const preview = document.createElement("span");
        preview.className = "sidebar-customization-icon-preview";
        preview.setAttribute("aria-hidden", "true");

        const select = document.createElement("select");
        select.className = "sidebar-customization-icon-select";
        select.setAttribute("aria-label", "Icona");
        ICON_OPTIONS.forEach(option => {
            const optionNode = document.createElement("option");
            optionNode.value = option.value;
            optionNode.textContent = option.label;
            select.appendChild(optionNode);
        });
        select.value = normalizedIconValue(value);
        updateIconPreview(preview, select.value);

        select.addEventListener("change", function () {
            updateIconPreview(preview, select.value);
            if (onChange) {
                onChange(select.value);
            }
        });

        picker.appendChild(preview);
        picker.appendChild(select);
        return { picker, select };
    }

    function directChild(element, selector) {
        return Array.from(element.children).find(child => child.matches(selector)) || null;
    }

    function getGroupButton(element) {
        if (element.classList.contains("sidebar-section") || element.classList.contains("sidebar-subsection")) {
            return directChild(element, ".sidebar-collapsible");
        }
        return null;
    }

    function getGroupPanel(element) {
        const button = getGroupButton(element);
        const targetId = button?.dataset.target || "";
        return targetId ? document.getElementById(targetId) : null;
    }

    function getElementType(element) {
        if (element.classList.contains("sidebar-section")) {
            return element.dataset[CUSTOM_SECTION_ATTR] === "1" ? "custom-section" : "section";
        }
        if (element.classList.contains("sidebar-subsection")) {
            return "submenu";
        }
        if (element.matches("a[href]")) {
            return "link";
        }
        return "item";
    }

    function getElementLabel(element) {
        if (element.matches("a[href]")) {
            return normalizeText(element.querySelector(".sidebar-link-text")?.textContent || element.textContent);
        }
        const button = getGroupButton(element);
        return normalizeText(button?.textContent || element.textContent);
    }

    function getElementKey(element) {
        if (element.dataset.sidebarCustomizationKey) {
            return element.dataset.sidebarCustomizationKey;
        }

        let key = "";
        if (element.classList.contains("sidebar-section")) {
            if (element.dataset[CUSTOM_SECTION_ATTR] === "1") {
                key = `custom:${element.dataset.customSectionId || stableId("custom")}`;
            } else {
                key = `section:${element.dataset.sidebarSectionKey || safeDomId(getElementLabel(element))}`;
            }
        } else if (element.classList.contains("sidebar-subsection")) {
            const button = getGroupButton(element);
            key = `submenu:${button?.dataset.target || safeDomId(getElementLabel(element))}`;
        } else if (element.matches("a[href]")) {
            const customKey = element.dataset.customLinkId;
            if (customKey) {
                key = `custom-link:${customKey}`;
            } else {
                const url = new URL(element.getAttribute("href") || "#", window.location.origin);
                key = `link:${url.origin === window.location.origin ? `${url.pathname}${url.search}` : url.href}`;
            }
        }

        element.dataset.sidebarCustomizationKey = key;
        return key;
    }

    function isCustomizableChild(element) {
        return element.classList.contains("sidebar-section")
            || element.classList.contains("sidebar-subsection")
            || element.matches("a[href]");
    }

    function getOrderChildren(container) {
        return Array.from(container.children).filter(isCustomizableChild);
    }

    function getOrderContainers() {
        if (!root) {
            return [];
        }
        return [
            root,
            ...Array.from(root.querySelectorAll("[data-sidebar-order-parent]")),
        ].filter(container => container?.dataset?.sidebarOrderParent);
    }

    function getOrderKeys(container) {
        return getOrderChildren(container).map(getElementKey).filter(Boolean);
    }

    function assignOrderParent(container, key) {
        if (container) {
            container.dataset.sidebarOrderParent = key;
        }
    }

    function prepareGroup(element) {
        const key = getElementKey(element);
        const panel = getGroupPanel(element);
        if (!panel) {
            return;
        }

        assignOrderParent(panel, `panel:${key}`);

        let navIndex = 0;
        Array.from(panel.children).forEach(child => {
            if (child.matches("nav.sidebar-nav")) {
                assignOrderParent(child, `nav:${key}:${navIndex}`);
                navIndex += 1;
                Array.from(child.children).forEach(navChild => {
                    if (isCustomizableChild(navChild)) {
                        getElementKey(navChild);
                        if (navChild.classList.contains("sidebar-subsection")) {
                            prepareGroup(navChild);
                        }
                    }
                });
            } else if (isCustomizableChild(child)) {
                getElementKey(child);
                if (child.classList.contains("sidebar-subsection")) {
                    prepareGroup(child);
                }
            }
        });
    }

    function prepareSidebar() {
        root = document.getElementById("sidebar-reorder-list");
        if (!root) {
            return;
        }
        assignOrderParent(root, "root");
        Array.from(root.children).forEach(child => {
            if (!child.classList.contains("sidebar-section")) {
                return;
            }
            getElementKey(child);
            prepareGroup(child);
        });
    }

    function createSidebarLink(link) {
        const anchor = document.createElement("a");
        anchor.href = link.url || "#";
        anchor.dataset.customLinkId = link.id || stableId("custom-link");
        anchor.dataset.sidebarCustomizationKey = `custom-link:${anchor.dataset.customLinkId}`;

        const icon = document.createElement("span");
        icon.className = "sidebar-link-icon sidebar-icon-blue";
        icon.setAttribute("aria-hidden", "true");
        appendIcon(icon, normalizedIconValue(link.icon));

        const text = document.createElement("span");
        text.className = "sidebar-link-text";
        text.textContent = link.label || "Link";

        anchor.appendChild(icon);
        anchor.appendChild(text);
        return anchor;
    }

    function renderCustomSections() {
        if (!root) {
            return;
        }

        root.querySelectorAll("[data-sidebar-custom-section='1']").forEach(section => section.remove());

        (config.custom_sections || []).forEach(sectionConfig => {
            const section = document.createElement("div");
            const sectionId = sectionConfig.id || stableId("custom-section");
            const panelId = `sidebar-custom-${safeDomId(sectionId)}-panel`;
            section.className = "sidebar-section";
            section.dataset.sidebarSectionKey = `custom-${sectionId}`;
            section.dataset[CUSTOM_SECTION_ATTR] = "1";
            section.dataset.customSectionId = sectionId;
            section.dataset.sidebarCustomizationKey = `custom:${sectionId}`;

            const button = document.createElement("button");
            button.type = "button";
            button.className = "sidebar-collapsible collapsible-title is-open";
            button.dataset.target = panelId;
            button.dataset.storageKey = `arboris-sidebar-custom-${safeDomId(sectionId)}`;
            button.dataset.defaultOpen = "true";

            const heading = document.createElement("span");
            heading.className = "sidebar-heading-content";
            const headingIcon = document.createElement("span");
            headingIcon.className = "sidebar-link-icon sidebar-icon-blue sidebar-custom-section-heading-icon";
            headingIcon.setAttribute("aria-hidden", "true");
            appendIcon(headingIcon, normalizedIconValue(sectionConfig.icon));
            const label = document.createElement("span");
            label.textContent = sectionConfig.label || "Menu personalizzato";
            heading.appendChild(headingIcon);
            heading.appendChild(label);
            button.appendChild(heading);

            const panel = document.createElement("div");
            panel.className = "collapsible-panel is-open sidebar-module-panel";
            panel.id = panelId;

            const nav = document.createElement("nav");
            nav.className = "sidebar-nav sidebar-subnav";
            (sectionConfig.links || []).forEach(link => {
                nav.appendChild(createSidebarLink(link));
            });
            panel.appendChild(nav);
            section.appendChild(button);
            section.appendChild(panel);
            root.appendChild(section);
        });
    }

    function applyOrders() {
        const orders = config.order || {};
        getOrderContainers().forEach(container => {
            const order = orders[container.dataset.sidebarOrderParent];
            if (!Array.isArray(order) || !order.length) {
                return;
            }
            const childrenByKey = new Map();
            getOrderChildren(container).forEach(child => {
                childrenByKey.set(getElementKey(child), child);
            });
            const orderedChildren = [];
            order.forEach(childKey => {
                const child = childrenByKey.get(childKey);
                if (child) {
                    orderedChildren.push(child);
                    childrenByKey.delete(childKey);
                }
            });
            [...orderedChildren, ...childrenByKey.values()].forEach(child => {
                container.appendChild(child);
            });
        });
    }

    function applyVisibility() {
        document.querySelectorAll("[data-sidebar-customization-key]").forEach(element => {
            element.classList.toggle(HIDDEN_CLASS, hiddenKeys.has(getElementKey(element)));
        });
    }

    function applyConfig() {
        prepareSidebar();
        renderCustomSections();
        prepareSidebar();
        hiddenKeys = new Set(Array.isArray(config.hidden) ? config.hidden : []);
        applyOrders();
        applyVisibility();
    }

    function getLogicalChildren(group) {
        const panel = getGroupPanel(group);
        if (!panel) {
            return [];
        }
        const children = [];
        Array.from(panel.children).forEach(child => {
            if (child.matches("nav.sidebar-nav")) {
                Array.from(child.children).forEach(navChild => {
                    if (isCustomizableChild(navChild)) {
                        children.push(navChild);
                    }
                });
            } else if (isCustomizableChild(child)) {
                children.push(child);
            }
        });
        return children;
    }

    function flattenSidebarTree() {
        const rows = [];
        function visit(element, depth) {
            rows.push({
                element,
                depth,
                key: getElementKey(element),
                label: getElementLabel(element),
                type: getElementType(element),
            });
            if (element.classList.contains("sidebar-section") || element.classList.contains("sidebar-subsection")) {
                getLogicalChildren(element).forEach(child => visit(child, Math.min(depth + 1, 3)));
            }
        }

        getOrderChildren(root).forEach(section => visit(section, 0));
        return rows;
    }

    function swapWithSibling(element, direction) {
        const parent = element.parentElement;
        if (!parent) {
            return false;
        }
        const siblings = getOrderChildren(parent);
        const index = siblings.indexOf(element);
        const target = siblings[index + direction];
        if (!target) {
            return false;
        }
        if (direction < 0) {
            parent.insertBefore(element, target);
        } else {
            parent.insertBefore(target, element);
        }
        return true;
    }

    function cleanupDragState() {
        if (draggedTreeItem) {
            draggedTreeItem.classList.remove("is-dragging");
        }
        treeContainer?.querySelectorAll(".sidebar-customization-row").forEach(item => {
            item.classList.remove("is-drop-target", "is-drop-before", "is-drop-after");
        });
        draggedTreeItem = null;
    }

    function canDropOnTreeItem(targetItem) {
        return draggedTreeItem
            && targetItem
            && targetItem !== draggedTreeItem
            && targetItem.dataset.sidebarOrderParent === draggedTreeItem.dataset.sidebarOrderParent;
    }

    function updateDropHint(targetItem, event) {
        if (!canDropOnTreeItem(targetItem)) {
            return false;
        }
        const rect = targetItem.getBoundingClientRect();
        const placeBefore = event.clientY < rect.top + rect.height / 2;
        targetItem.classList.toggle("is-drop-before", placeBefore);
        targetItem.classList.toggle("is-drop-after", !placeBefore);
        targetItem.classList.add("is-drop-target");
        return placeBefore;
    }

    function moveDraggedTreeItem(targetItem, event) {
        if (!canDropOnTreeItem(targetItem)) {
            return false;
        }
        const draggedElement = draggedTreeItem.sidebarMenuElement;
        const targetElement = targetItem.sidebarMenuElement;
        const parent = targetElement?.parentElement;
        if (!draggedElement || !targetElement || draggedElement.parentElement !== parent) {
            return false;
        }

        const placeBefore = updateDropHint(targetItem, event);
        if (placeBefore) {
            parent.insertBefore(draggedElement, targetElement);
        } else {
            parent.insertBefore(draggedElement, targetElement.nextSibling);
        }
        return true;
    }

    function buttonWithIcon(label, iconName, className) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className || "table-icon-link";
        button.setAttribute("aria-label", label);
        button.setAttribute("data-floating-text", label);
        appendIcon(button, iconName);
        return button;
    }

    function renderTreeEditor() {
        if (!treeContainer) {
            return;
        }
        prepareSidebar();
        treeContainer.innerHTML = "";

        flattenSidebarTree().forEach(row => {
            const item = document.createElement("div");
            item.className = "sidebar-customization-row";
            item.dataset.depth = String(row.depth);
            item.dataset.sidebarCustomizationRowKey = row.key;
            item.dataset.sidebarOrderParent = row.element.parentElement?.dataset.sidebarOrderParent || "";
            item.draggable = true;
            item.sidebarMenuElement = row.element;
            item.classList.toggle("is-hidden", hiddenKeys.has(row.key));

            item.addEventListener("dragstart", function (event) {
                if (event.target.closest("input, button, select, textarea")) {
                    event.preventDefault();
                    return;
                }
                draggedTreeItem = item;
                item.classList.add("is-dragging");
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", row.key);
                }
            });

            item.addEventListener("dragover", function (event) {
                if (!canDropOnTreeItem(item)) {
                    return;
                }
                event.preventDefault();
                updateDropHint(item, event);
                if (event.dataTransfer) {
                    event.dataTransfer.dropEffect = "move";
                }
            });

            item.addEventListener("dragleave", function () {
                item.classList.remove("is-drop-target", "is-drop-before", "is-drop-after");
            });

            item.addEventListener("drop", function (event) {
                if (!canDropOnTreeItem(item)) {
                    return;
                }
                event.preventDefault();
                if (moveDraggedTreeItem(item, event)) {
                    cleanupDragState();
                    renderTreeEditor();
                }
            });

            item.addEventListener("dragend", cleanupDragState);

            const main = document.createElement("label");
            main.className = "sidebar-customization-row-main";

            const dragHandle = document.createElement("span");
            dragHandle.className = "sidebar-customization-drag-handle";
            dragHandle.setAttribute("aria-hidden", "true");
            dragHandle.setAttribute("title", "Trascina per riordinare");
            appendIcon(dragHandle, "arrows-up-down");

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = !hiddenKeys.has(row.key);
            checkbox.addEventListener("change", function () {
                if (checkbox.checked) {
                    hiddenKeys.delete(row.key);
                } else {
                    hiddenKeys.add(row.key);
                }
                config.hidden = Array.from(hiddenKeys);
                applyVisibility();
                renderTreeEditor();
            });

            const copy = document.createElement("span");
            copy.className = "sidebar-customization-row-copy";
            const label = document.createElement("span");
            label.className = "sidebar-customization-row-label";
            label.textContent = row.label || "Elemento";
            const type = document.createElement("span");
            type.className = "sidebar-customization-row-type";
            type.textContent = row.type === "section" ? "Menu" : row.type === "submenu" ? "Sottomenu" : row.type === "custom-section" ? "Menu personalizzato" : "Voce";
            copy.appendChild(label);
            copy.appendChild(type);

            main.appendChild(dragHandle);
            main.appendChild(checkbox);
            main.appendChild(copy);

            const actions = document.createElement("span");
            actions.className = "sidebar-customization-row-actions";
            const up = buttonWithIcon("Sposta su", "chevron-down", "table-icon-link sidebar-customization-move-up");
            const down = buttonWithIcon("Sposta giu", "chevron-down", "table-icon-link");
            up.addEventListener("click", function () {
                if (swapWithSibling(row.element, -1)) {
                    renderTreeEditor();
                }
            });
            down.addEventListener("click", function () {
                if (swapWithSibling(row.element, 1)) {
                    renderTreeEditor();
                }
            });
            actions.appendChild(up);
            actions.appendChild(down);

            item.appendChild(main);
            item.appendChild(actions);
            treeContainer.appendChild(item);
        });
    }

    function refreshCustomDom() {
        renderCustomSections();
        prepareSidebar();
        applyOrders();
        applyVisibility();
        if (window.ArborisCollapsible) {
            ArborisCollapsible.initCollapsibleSections(document);
        }
    }

    function renderCustomPanel() {
        if (!customContainer) {
            return;
        }
        customContainer.innerHTML = "";

        const addCard = document.createElement("div");
        addCard.className = "sidebar-customization-card";
        const addTitle = document.createElement("h3");
        addTitle.className = "sidebar-customization-section-title";
        addTitle.textContent = "Nuovo menu";
        const addGrid = document.createElement("div");
        addGrid.className = "sidebar-customization-form-grid";

        const labelField = document.createElement("label");
        labelField.className = "sidebar-customization-field";
        labelField.innerHTML = "<span>Nome menu</span>";
        const labelInput = document.createElement("input");
        labelInput.type = "text";
        labelInput.maxLength = 60;
        labelInput.placeholder = "Es. Preferiti";
        labelField.appendChild(labelInput);

        const iconField = document.createElement("label");
        iconField.className = "sidebar-customization-field";
        iconField.innerHTML = "<span>Icona</span>";
        const iconPicker = createIconPicker("list");
        iconField.appendChild(iconPicker.picker);

        const addButton = document.createElement("button");
        addButton.type = "button";
        addButton.className = "btn btn-secondary";
        addButton.textContent = "Aggiungi menu";
        addButton.addEventListener("click", function () {
            const label = normalizeText(labelInput.value);
            if (!label) {
                labelInput.focus();
                return;
            }
            config.custom_sections = config.custom_sections || [];
            config.custom_sections.push({
                id: stableId("menu"),
                label,
                icon: iconPicker.select.value,
                links: [],
            });
            labelInput.value = "";
            refreshCustomDom();
            renderTreeEditor();
            renderCustomPanel();
        });

        addGrid.appendChild(labelField);
        addGrid.appendChild(iconField);
        addCard.appendChild(addTitle);
        addCard.appendChild(addGrid);
        addCard.appendChild(addButton);
        customContainer.appendChild(addCard);

        (config.custom_sections || []).forEach(section => {
            const card = document.createElement("div");
            card.className = "sidebar-customization-card";

            const nameField = document.createElement("label");
            nameField.className = "sidebar-customization-field";
            nameField.innerHTML = "<span>Nome menu</span>";
            const nameInput = document.createElement("input");
            nameInput.type = "text";
            nameInput.maxLength = 60;
            nameInput.value = section.label || "";
            nameInput.addEventListener("change", function () {
                section.label = normalizeText(nameInput.value) || "Menu personalizzato";
                refreshCustomDom();
                renderTreeEditor();
            });
            nameField.appendChild(nameInput);

            const iconFieldExisting = document.createElement("label");
            iconFieldExisting.className = "sidebar-customization-field";
            iconFieldExisting.innerHTML = "<span>Icona menu</span>";
            const iconPickerExisting = createIconPicker(section.icon || "list", function (iconValue) {
                section.icon = iconValue;
                (section.links || []).forEach(link => {
                    link.icon = iconValue;
                });
                refreshCustomDom();
                renderTreeEditor();
            });
            iconFieldExisting.appendChild(iconPickerExisting.picker);

            const linksTitle = document.createElement("h3");
            linksTitle.className = "sidebar-customization-section-title";
            linksTitle.textContent = "Link";

            const linksList = document.createElement("div");
            (section.links || []).forEach(link => {
                const row = document.createElement("div");
                row.className = "sidebar-customization-link-row";
                const copy = document.createElement("span");
                copy.textContent = `${link.label || "Link"} - ${link.url || "#"}`;
                const remove = buttonWithIcon("Rimuovi link", "trash", "table-icon-link table-icon-link-danger");
                remove.addEventListener("click", function () {
                    section.links = (section.links || []).filter(item => item !== link);
                    refreshCustomDom();
                    renderTreeEditor();
                    renderCustomPanel();
                });
                row.appendChild(copy);
                row.appendChild(remove);
                linksList.appendChild(row);
            });

            const linkLabelField = document.createElement("label");
            linkLabelField.className = "sidebar-customization-field";
            linkLabelField.innerHTML = "<span>Nuovo link</span>";
            const linkLabelInput = document.createElement("input");
            linkLabelInput.type = "text";
            linkLabelInput.maxLength = 80;
            linkLabelInput.placeholder = "Etichetta";
            linkLabelField.appendChild(linkLabelInput);

            const linkUrlField = document.createElement("label");
            linkUrlField.className = "sidebar-customization-field";
            linkUrlField.innerHTML = "<span>URL</span>";
            const linkUrlInput = document.createElement("input");
            linkUrlInput.type = "text";
            linkUrlInput.maxLength = 240;
            linkUrlInput.placeholder = "/percorso/ oppure https://...";
            linkUrlField.appendChild(linkUrlInput);

            const addLink = document.createElement("button");
            addLink.type = "button";
            addLink.className = "btn btn-secondary";
            addLink.textContent = "Aggiungi link";
            addLink.addEventListener("click", function () {
                const label = normalizeText(linkLabelInput.value);
                const url = normalizeText(linkUrlInput.value);
                if (!label || !url) {
                    (label ? linkUrlInput : linkLabelInput).focus();
                    return;
                }
                section.links = section.links || [];
                section.links.push({
                    id: stableId("link"),
                    label,
                    url,
                    icon: normalizedIconValue(section.icon),
                });
                refreshCustomDom();
                renderTreeEditor();
                renderCustomPanel();
            });

            const removeMenu = document.createElement("button");
            removeMenu.type = "button";
            removeMenu.className = "btn btn-danger";
            removeMenu.textContent = "Elimina menu";
            removeMenu.addEventListener("click", function () {
                config.custom_sections = (config.custom_sections || []).filter(item => item !== section);
                refreshCustomDom();
                renderTreeEditor();
                renderCustomPanel();
            });

            card.appendChild(nameField);
            card.appendChild(iconFieldExisting);
            card.appendChild(linksTitle);
            card.appendChild(linksList);
            card.appendChild(linkLabelField);
            card.appendChild(linkUrlField);
            card.appendChild(addLink);
            card.appendChild(removeMenu);
            customContainer.appendChild(card);
        });
    }

    function collectOrders() {
        const order = {};
        getOrderContainers().forEach(container => {
            const keys = getOrderKeys(container);
            if (keys.length) {
                order[container.dataset.sidebarOrderParent] = keys;
            }
        });
        return order;
    }

    function normalizeConfigForSave() {
        config.hidden = Array.from(hiddenKeys);
        config.order = collectOrders();
        (config.custom_sections || []).forEach(section => {
            section.icon = normalizedIconValue(section.icon);
            (section.links || []).forEach(link => {
                link.icon = normalizedIconValue(link.icon || section.icon);
            });
        });
        return config;
    }

    function setStatus(message, tone) {
        if (!statusNode) {
            return;
        }
        statusNode.textContent = message || "";
        statusNode.dataset.tone = tone || "";
    }

    function setActionBusy(button, busy, label) {
        if (!button) {
            return;
        }
        if (!button.dataset.defaultLabel) {
            button.dataset.defaultLabel = button.textContent;
        }
        button.disabled = busy;
        button.textContent = busy ? label : button.dataset.defaultLabel;
    }

    function responseErrorMessage(response, fallbackMessage) {
        if (response.status === 403) {
            return "Sessione scaduta o token di sicurezza non valido. Ricarica la pagina e riprova.";
        }
        return fallbackMessage;
    }

    function openDialog() {
        if (!dialog) {
            buildDialog();
        }
        renderTreeEditor();
        renderCustomPanel();
        dialog.classList.add("is-open");
        dialog.setAttribute("aria-hidden", "false");
        dialog.querySelector(".sidebar-customization-close")?.focus();
    }

    function closeDialog() {
        if (!dialog) {
            return;
        }
        dialog.classList.remove("is-open");
        dialog.setAttribute("aria-hidden", "true");
    }

    function persistConfig(options) {
        const saveButton = options?.button || null;
        const closeOnSuccess = Boolean(options?.closeOnSuccess);
        const silent = Boolean(options?.silent);
        if (!configUrl) {
            const error = new Error("Endpoint di salvataggio non disponibile. Ricarica la pagina.");
            if (!silent) {
                setStatus(error.message, "error");
            }
            return Promise.reject(error);
        }
        normalizeConfigForSave();
        if (!silent) {
            setStatus("Salvataggio...", "");
        }
        setActionBusy(saveButton, true, "Salvataggio...");

        return fetch(configUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify({ config }),
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(responseErrorMessage(response, "Salvataggio non riuscito"));
                }
                return response.json();
            })
            .then(payload => {
                config = { ...cloneConfig(EMPTY_CONFIG), ...(payload.config || {}) };
                hiddenKeys = new Set(config.hidden || []);
                applyConfig();
                renderTreeEditor();
                renderCustomPanel();
                if (!silent) {
                    setStatus("Menu salvato.", "");
                }
                if (closeOnSuccess) {
                    closeDialog();
                }
                return payload;
            })
            .catch(error => {
                if (!silent) {
                    setStatus(error.message || "Salvataggio non riuscito", "error");
                }
                throw error;
            })
            .finally(() => {
                setActionBusy(saveButton, false);
            });
    }

    function saveConfig() {
        const saveButton = dialog?.querySelector("[data-sidebar-customization-save]");
        persistConfig({ button: saveButton, closeOnSuccess: true }).catch(() => {});
    }

    function resetConfig() {
        const resetButton = dialog?.querySelector("[data-sidebar-customization-reset]");
        if (!configUrl) {
            setStatus("Endpoint di salvataggio non disponibile. Ricarica la pagina.", "error");
            return;
        }
        setStatus("Ripristino...", "");
        setActionBusy(resetButton, true, "Ripristino...");
        fetch(configUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify({ reset: true }),
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(responseErrorMessage(response, "Ripristino non riuscito"));
                }
                window.location.reload();
            })
            .catch(error => {
                setStatus(error.message || "Ripristino non riuscito", "error");
                setActionBusy(resetButton, false);
            });
    }

    function buildDialog() {
        dialog = document.createElement("div");
        dialog.className = "sidebar-customization-dialog";
        dialog.setAttribute("aria-hidden", "true");

        const backdrop = document.createElement("div");
        backdrop.className = "sidebar-customization-backdrop";
        backdrop.addEventListener("click", closeDialog);

        const panel = document.createElement("section");
        panel.className = "sidebar-customization-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "true");
        panel.setAttribute("aria-labelledby", "sidebar-customization-title");

        const head = document.createElement("div");
        head.className = "sidebar-customization-head";
        const heading = document.createElement("div");
        const title = document.createElement("h2");
        title.className = "sidebar-customization-title";
        title.id = "sidebar-customization-title";
        title.textContent = "Personalizza menu";
        const subtitle = document.createElement("p");
        subtitle.className = "sidebar-customization-subtitle";
        subtitle.textContent = "Scegli cosa mostrare, riordina le voci e aggiungi menu personali. I permessi del tuo profilo restano sempre applicati.";
        heading.appendChild(title);
        heading.appendChild(subtitle);
        const close = buttonWithIcon("Chiudi", "x", "table-icon-link sidebar-customization-close");
        close.addEventListener("click", closeDialog);
        head.appendChild(heading);
        head.appendChild(close);

        const body = document.createElement("div");
        body.className = "sidebar-customization-body";
        const listPanel = document.createElement("div");
        listPanel.className = "sidebar-customization-list-panel";
        const listTitle = document.createElement("h3");
        listTitle.className = "sidebar-customization-section-title";
        listTitle.textContent = "Menu e voci";
        treeContainer = document.createElement("div");
        treeContainer.className = "sidebar-customization-tree";
        listPanel.appendChild(listTitle);
        listPanel.appendChild(treeContainer);

        const customPanel = document.createElement("div");
        customPanel.className = "sidebar-customization-custom-panel";
        const customTitle = document.createElement("h3");
        customTitle.className = "sidebar-customization-section-title";
        customTitle.textContent = "Menu personalizzati";
        customContainer = document.createElement("div");
        customPanel.appendChild(customTitle);
        customPanel.appendChild(customContainer);
        body.appendChild(listPanel);
        body.appendChild(customPanel);

        const footer = document.createElement("div");
        footer.className = "sidebar-customization-footer";
        statusNode = document.createElement("div");
        statusNode.className = "sidebar-customization-status";
        statusNode.setAttribute("aria-live", "polite");
        const actions = document.createElement("div");
        actions.className = "sidebar-customization-actions";
        const reset = document.createElement("button");
        reset.type = "button";
        reset.className = "btn btn-secondary";
        reset.textContent = "Ripristina default";
        reset.setAttribute("data-sidebar-customization-reset", "1");
        reset.addEventListener("click", resetConfig);
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "btn btn-secondary";
        cancel.textContent = "Chiudi";
        cancel.addEventListener("click", closeDialog);
        const save = document.createElement("button");
        save.type = "button";
        save.className = "btn btn-primary";
        save.textContent = "Salva menu";
        save.setAttribute("data-sidebar-customization-save", "1");
        save.addEventListener("click", saveConfig);
        actions.appendChild(reset);
        actions.appendChild(cancel);
        actions.appendChild(save);
        footer.appendChild(statusNode);
        footer.appendChild(actions);

        panel.appendChild(head);
        panel.appendChild(body);
        panel.appendChild(footer);
        dialog.appendChild(backdrop);
        dialog.appendChild(panel);
        document.body.appendChild(dialog);
    }

    function hasPersistentOrder() {
        return Boolean(config && config.order && Object.keys(config.order).length);
    }

    function init() {
        const trigger = document.getElementById("sidebar-customize-toggle");
        root = document.getElementById("sidebar-reorder-list");
        if (!trigger || !root) {
            return;
        }
        configUrl = trigger.dataset.sidebarConfigUrl || "";
        config = { ...cloneConfig(EMPTY_CONFIG), ...readInitialConfig() };
        applyConfig();
        trigger.addEventListener("click", openDialog);
    }

    return {
        init,
        hasPersistentOrder,
        saveCurrentOrder() {
            return persistConfig({ silent: true });
        },
    };
})();
