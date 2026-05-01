window.ArborisModalPopups = (function () {
    const stack = [];
    let root = null;
    let previousActiveElement = null;

    function canReachTopModalApi() {
        try {
            return Boolean(window.top && window.top !== window && window.top.ArborisModalPopups);
        } catch (error) {
            return false;
        }
    }

    function getTopModalApi() {
        if (!canReachTopModalApi()) {
            return null;
        }
        return window.top.ArborisModalPopups;
    }

    function parseFeatureSize(features) {
        const result = {
            width: 900,
            height: 700,
        };
        String(features || "")
            .split(",")
            .map(part => part.trim())
            .forEach(function (part) {
                const pieces = part.split("=");
                if (pieces.length !== 2) {
                    return;
                }
                const key = pieces[0].trim().toLowerCase();
                const value = parseInt(pieces[1], 10);
                if (!Number.isFinite(value) || value <= 0) {
                    return;
                }
                if (key === "width") {
                    result.width = value;
                }
                if (key === "height") {
                    result.height = value;
                }
            });
        return result;
    }

    function ensureRoot() {
        if (root && root.parentNode) {
            return root;
        }

        root = document.createElement("div");
        root.className = "app-modal-stack";
        root.setAttribute("aria-live", "polite");
        document.body.appendChild(root);
        return root;
    }

    function updateBodyState() {
        if (!document.body) {
            return;
        }

        if (stack.length) {
            document.body.classList.add("app-modal-open");
        } else {
            document.body.classList.remove("app-modal-open");
            if (root && root.parentNode) {
                root.parentNode.removeChild(root);
                root = null;
            }
            if (previousActiveElement && typeof previousActiveElement.focus === "function") {
                try {
                    previousActiveElement.focus({ preventScroll: true });
                } catch (error) {
                    previousActiveElement.focus();
                }
            }
            previousActiveElement = null;
        }
    }

    function findLayerIndexByWindow(sourceWindow) {
        if (!sourceWindow) {
            return stack.length - 1;
        }

        for (let i = stack.length - 1; i >= 0; i -= 1) {
            try {
                if (stack[i].iframe && stack[i].iframe.contentWindow === sourceWindow) {
                    return i;
                }
            } catch (error) {
                // Ignore cross-window access failures and keep searching.
            }
        }

        return stack.length - 1;
    }

    function getCurrentLayer(sourceWindow) {
        const index = findLayerIndexByWindow(sourceWindow);
        if (index < 0) {
            return null;
        }
        return stack[index] || null;
    }

    function getOpenerWindow(sourceWindow) {
        const layer = getCurrentLayer(sourceWindow);
        if (layer && layer.openerWindow && !layer.openerWindow.closed) {
            return layer.openerWindow;
        }
        return window;
    }

    function closeAt(index) {
        if (index < 0 || index >= stack.length) {
            return;
        }

        const layersToClose = stack.splice(index);
        layersToClose.forEach(function (layer) {
            if (layer.resizeHandler) {
                window.removeEventListener("resize", layer.resizeHandler);
            }
            if (layer.node && layer.node.parentNode) {
                layer.node.parentNode.removeChild(layer.node);
            }
            layer.closed = true;
        });

        const activeLayer = stack[stack.length - 1] || null;
        if (activeLayer && activeLayer.node) {
            activeLayer.node.classList.add("is-active");
            focusLayer(activeLayer);
        }
        updateBodyState();
    }

    function closeForWindow(sourceWindow) {
        closeAt(findLayerIndexByWindow(sourceWindow));
    }

    function closeTopLayer() {
        closeAt(stack.length - 1);
    }

    function focusLayer(layer) {
        if (!layer) {
            return;
        }

        try {
            if (layer.loaded && layer.iframe && layer.iframe.contentWindow) {
                layer.iframe.contentWindow.focus();
                return;
            }
        } catch (error) {
            // Fall back to focusing the modal shell.
        }

        if (layer.windowEl && typeof layer.windowEl.focus === "function") {
            layer.windowEl.focus({ preventScroll: true });
        }
    }

    function focusTopLayer() {
        focusLayer(stack[stack.length - 1] || null);
    }

    function getFrameDocument(layer) {
        if (!layer || !layer.iframe) {
            return null;
        }

        try {
            return layer.iframe.contentDocument || (layer.iframe.contentWindow ? layer.iframe.contentWindow.document : null);
        } catch (error) {
            return null;
        }
    }

    function markChildDocument(childDocument) {
        if (!childDocument || !childDocument.documentElement) {
            return;
        }

        childDocument.documentElement.classList.add("app-modal-child");
        if (childDocument.body) {
            childDocument.body.classList.add("app-modal-child-body");
        }
    }

    function fitLayerToContent(layer) {
        if (!layer || !layer.windowEl) {
            return;
        }

        const childDocument = getFrameDocument(layer);
        if (!childDocument || !childDocument.documentElement || !childDocument.body) {
            return;
        }

        const html = childDocument.documentElement;
        const body = childDocument.body;
        const contentWidth = Math.max(
            html.scrollWidth,
            body.scrollWidth,
            html.offsetWidth,
            body.offsetWidth
        );
        const contentHeight = Math.max(
            html.scrollHeight,
            body.scrollHeight,
            html.offsetHeight,
            body.offsetHeight
        );
        const viewportWidth = Math.max(320, window.innerWidth - 28);
        const viewportHeight = Math.max(360, window.innerHeight - 28);
        const desiredWidth = Math.min(viewportWidth, Math.max(620, contentWidth));
        const desiredHeight = Math.min(viewportHeight, Math.max(420, contentHeight));

        layer.windowEl.style.setProperty("--app-modal-width", `${Math.ceil(desiredWidth)}px`);
        layer.windowEl.style.setProperty("--app-modal-height", `${Math.ceil(desiredHeight)}px`);
        layer.node.classList.toggle(
            "is-content-clipped",
            contentWidth > viewportWidth + 2 || contentHeight > viewportHeight + 2
        );
    }

    function scheduleFitLayerToContent(layer) {
        if (!layer) {
            return;
        }

        window.requestAnimationFrame(function () {
            fitLayerToContent(layer);
        });
        window.setTimeout(function () {
            fitLayerToContent(layer);
        }, 160);
        window.setTimeout(function () {
            fitLayerToContent(layer);
        }, 420);
    }

    function installFrameCloseBridge(layer) {
        if (!layer || !layer.iframe) {
            return;
        }

        let childWindow = null;
        let childDocument = null;
        try {
            childWindow = layer.iframe.contentWindow;
            childDocument = childWindow ? childWindow.document : null;
        } catch (error) {
            return;
        }

        if (!childWindow || !childDocument || childWindow.__arborisModalCloseBridge === "1") {
            return;
        }

        markChildDocument(childDocument);

        childWindow.__arborisModalCloseBridge = "1";
        childWindow.ArborisClosePopup = function () {
            closeForWindow(childWindow);
        };

        try {
            childWindow.close = childWindow.ArborisClosePopup;
        } catch (error) {
            // Some browsers may keep window.close readonly; the click bridge below still covers template buttons.
        }

        childDocument.addEventListener("click", function (event) {
            const closeTrigger = event.target && event.target.closest
                ? event.target.closest("[onclick*='window.close']")
                : null;
            if (!closeTrigger) {
                return;
            }
            event.preventDefault();
            event.stopImmediatePropagation();
            closeForWindow(childWindow);
        }, true);

        childDocument.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            closeForWindow(childWindow);
        }, true);
    }

    function buildLayer(url, options) {
        const cfg = options || {};
        const size = parseFeatureSize(cfg.features);
        const stackRoot = ensureRoot();
        const layerIndex = stack.length;

        const layerNode = document.createElement("div");
        layerNode.className = "app-modal-layer is-active";
        layerNode.style.zIndex = String(1000 + layerIndex * 2);

        const backdrop = document.createElement("div");
        backdrop.className = "app-modal-backdrop";

        const windowEl = document.createElement("section");
        windowEl.className = "app-modal-window";
        windowEl.tabIndex = -1;
        windowEl.setAttribute("role", "dialog");
        windowEl.setAttribute("aria-modal", "true");
        windowEl.style.setProperty("--app-modal-width", `${size.width}px`);
        windowEl.style.setProperty("--app-modal-height", `${size.height}px`);

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "app-modal-close";
        closeButton.setAttribute("aria-label", "Chiudi popup");
        closeButton.innerHTML = "&times;";

        const loading = document.createElement("div");
        loading.className = "app-modal-loading";
        loading.textContent = "Caricamento...";

        const iframe = document.createElement("iframe");
        iframe.className = "app-modal-frame";
        iframe.title = cfg.title || "Popup Arboris";

        windowEl.appendChild(closeButton);
        windowEl.appendChild(loading);
        windowEl.appendChild(iframe);
        layerNode.appendChild(backdrop);
        layerNode.appendChild(windowEl);

        stack.forEach(function (layer) {
            if (layer.node) {
                layer.node.classList.remove("is-active");
            }
        });
        stackRoot.appendChild(layerNode);

        const layer = {
            closed: false,
            iframe: iframe,
            loaded: false,
            node: layerNode,
            openerWindow: cfg.openerWindow || window,
            windowEl: windowEl,
        };

        layer.resizeHandler = function () {
            scheduleFitLayerToContent(layer);
        };
        window.addEventListener("resize", layer.resizeHandler);

        closeButton.addEventListener("click", function (event) {
            event.preventDefault();
            const index = stack.indexOf(layer);
            if (index >= 0) {
                closeAt(index);
            }
        });

        iframe.addEventListener("load", function () {
            layer.loaded = true;
            installFrameCloseBridge(layer);
            layerNode.classList.add("is-loaded");
            scheduleFitLayerToContent(layer);
            focusLayer(layer);
        });

        backdrop.addEventListener("mousedown", function (event) {
            event.preventDefault();
            focusLayer(layer);
        });

        layerNode.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            const index = stack.indexOf(layer);
            if (index >= 0) {
                closeAt(index);
            }
        });

        iframe.src = url;

        return layer;
    }

    function open(url, options) {
        const topApi = getTopModalApi();
        if (topApi && topApi !== api) {
            return topApi.open(url, Object.assign({}, options || {}, { openerWindow: window }));
        }

        if (!document.body) {
            return null;
        }

        if (!stack.length) {
            previousActiveElement = document.activeElement;
        }

        const layer = buildLayer(url, options || {});
        stack.push(layer);
        updateBodyState();
        focusLayer(layer);

        return {
            get closed() {
                return layer.closed;
            },
            close: function () {
                const index = stack.indexOf(layer);
                if (index >= 0) {
                    closeAt(index);
                }
            },
            focus: function () {
                focusLayer(layer);
            },
        };
    }

    function handleRelatedSelection(payload, sourceWindow) {
        const data = payload || {};
        const openerWindow = getOpenerWindow(sourceWindow);

        if (data.action === "delete") {
            if (openerWindow && typeof openerWindow.dismissDeletedRelatedPopup === "function") {
                openerWindow.dismissDeletedRelatedPopup(data.fieldName, data.objectId, data.targetInputName);
            } else {
                reloadOpener(openerWindow);
            }
        } else if (openerWindow && typeof openerWindow.dismissRelatedPopup === "function") {
            openerWindow.dismissRelatedPopup(data.fieldName, data.objectId, data.objectLabel, data.targetInputName);
        } else {
            reloadOpener(openerWindow);
        }

        closeForWindow(sourceWindow);
    }

    function reloadOpener(openerWindow) {
        const targetWindow = openerWindow || window;
        if (targetWindow && typeof targetWindow.ArborisReloadWithLongWait === "function") {
            targetWindow.ArborisReloadWithLongWait();
            return;
        }

        if (targetWindow && targetWindow.location) {
            targetWindow.location.reload();
        }
    }

    function handleReload(sourceWindow) {
        reloadOpener(getOpenerWindow(sourceWindow));
        closeForWindow(sourceWindow);
    }

    document.addEventListener("focusin", function (event) {
        if (!stack.length) {
            return;
        }

        const activeLayer = stack[stack.length - 1];
        if (activeLayer && activeLayer.node && !activeLayer.node.contains(event.target)) {
            event.preventDefault();
            focusTopLayer();
        }
    }, true);

    document.addEventListener("keydown", function (event) {
        if (!stack.length || event.key !== "Escape") {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        closeTopLayer();
    }, true);

    const api = {
        closeForWindow: closeForWindow,
        closeTopLayer: closeTopLayer,
        focusTopLayer: focusTopLayer,
        handleRelatedSelection: handleRelatedSelection,
        handleReload: handleReload,
        open: open,
    };

    return api;
})();
