/**
 * Mostra il velo di caricamento quando navigazioni, form o richieste dati
 * superano una soglia percepibile.
 *
 * Navigazione via location.assign / href / click su riga (data-row-href): stesso
 * timer di attesa dei link.
 *
 * location.reload() è sincrono rispetto al paint: si arma il velo e si
 * rimanda il reload (doppio rAF + setTimeout(0)) così il browser può ridisegnare.
 */
(function () {
    const NAV_DELAY_MS = 180;
    const FORM_DELAY_MS = 180;
    const FETCH_DELAY_MS = 700;
    const MIN_VISIBLE_MS = 320;
    const BOOT_RELEASE_DELAY_MS = 120;
    const NEXT_PAGE_WAIT_TTL_MS = 8000;
    const CLASS_NAME = "arboris-long-wait";
    const BOOT_CLASS_NAME = "arboris-page-boot-loading";
    const NEXT_PAGE_WAIT_KEY = "arboris-next-page-loading-until";

    let formTimer = null;
    let formArmed = false;

    let navTimer = null;
    let navArmed = false;
    let navClickPending = false;

    let bootArmed = false;
    let hideVisualTimer = null;
    let visualShownAt = 0;

    function nowMs() {
        return Date.now();
    }

    function rememberNextPageLoading() {
        try {
            window.sessionStorage.setItem(NEXT_PAGE_WAIT_KEY, String(nowMs() + NEXT_PAGE_WAIT_TTL_MS));
        } catch (e) {
            /* ignore */
        }
    }

    function clearNextPageLoading() {
        try {
            window.sessionStorage.removeItem(NEXT_PAGE_WAIT_KEY);
        } catch (e) {
            /* ignore */
        }
    }

    function hasPendingNextPageLoading() {
        let value = null;
        try {
            value = window.sessionStorage.getItem(NEXT_PAGE_WAIT_KEY);
        } catch (e) {
            return false;
        }
        if (!value) {
            return false;
        }

        const expiresAt = Number(value);
        if (expiresAt && nowMs() <= expiresAt) {
            return true;
        }

        clearNextPageLoading();
        return false;
    }

    function ensureOverlay(doc) {
        const targetDoc = doc || document;
        if (!targetDoc || !targetDoc.getElementById) {
            return null;
        }

        let overlay = targetDoc.getElementById("arboris-page-loading-overlay");
        if (overlay) {
            return overlay;
        }
        if (!targetDoc.createElement) {
            return null;
        }

        const container = targetDoc.body || targetDoc.documentElement;
        if (!container || !container.appendChild) {
            return null;
        }

        overlay = targetDoc.createElement("div");
        overlay.id = "arboris-page-loading-overlay";
        overlay.className = "page-loading-overlay";
        overlay.setAttribute("role", "status");
        overlay.setAttribute("aria-live", "polite");
        overlay.setAttribute("aria-atomic", "true");
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML =
            '<div class="page-loading-overlay-card">' +
            '<span class="page-loading-spinner" aria-hidden="true"></span>' +
            '<span class="page-loading-text">Caricamento<span class="page-loading-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span></span>' +
            "</div>";
        container.appendChild(overlay);
        return overlay;
    }

    function setDocumentVisualActive(doc, active, immediate) {
        const targetDoc = doc || document;
        if (!targetDoc || !targetDoc.documentElement || !targetDoc.documentElement.classList) {
            return;
        }

        const root = targetDoc.documentElement;
        const overlay = ensureOverlay(targetDoc);
        if (hideVisualTimer) {
            clearTimeout(hideVisualTimer);
            hideVisualTimer = null;
        }

        if (active) {
            if (!root.classList.contains(CLASS_NAME) || !visualShownAt) {
                visualShownAt = nowMs();
            }
            root.classList.add(CLASS_NAME);
            if (overlay) {
                overlay.setAttribute("aria-hidden", "false");
            }
            return;
        }

        const hide = function () {
            root.classList.remove(CLASS_NAME);
            root.classList.remove(BOOT_CLASS_NAME);
            if (overlay) {
                overlay.setAttribute("aria-hidden", "true");
            }
            visualShownAt = 0;
            hideVisualTimer = null;
        };

        if (immediate || !root.classList.contains(CLASS_NAME)) {
            hide();
            return;
        }

        const visibleFor = nowMs() - visualShownAt;
        const delay = Math.max(0, MIN_VISIBLE_MS - visibleFor);
        if (delay > 0) {
            hideVisualTimer = setTimeout(hide, delay);
        } else {
            hide();
        }
    }

    function setVisualActive(active, immediate) {
        setDocumentVisualActive(document, active, immediate);
    }

    function armNavigationLongWait() {
        if (navTimer) {
            clearTimeout(navTimer);
        }
        navArmed = false;
        navClickPending = true;
        rememberNextPageLoading();
        updateVisual();
        navTimer = setTimeout(function () {
            navTimer = null;
            if (navClickPending) {
                navArmed = true;
                updateVisual();
            }
        }, NAV_DELAY_MS);
    }

    /**
     * Chiamare prima di navigazioni programmatiche same-origin (es. location.href = …).
     * @returns {void}
     */
    function armLongWaitIfSameOriginFullNavigation(destUrlString, baseHref) {
        let url;
        try {
            url = new URL(String(destUrlString), baseHref || window.location.href);
        } catch (err) {
            return;
        }
        if (url.protocol === "mailto:" || url.protocol === "tel:") {
            return;
        }
        if (url.origin !== window.location.origin) {
            return;
        }
        if (
            url.pathname === window.location.pathname &&
            url.search === window.location.search &&
            url.hash !== window.location.hash
        ) {
            return;
        }
        armNavigationLongWait();
    }

    let fetchTimer = null;
    let fetchArmed = false;
    let activeFetchCount = 0;

    let nativeLocationReload = null;
    if (typeof Location !== "undefined" && Location.prototype && typeof Location.prototype.reload === "function") {
        nativeLocationReload = Location.prototype.reload;
    }

    function updateVisual() {
        setVisualActive(bootArmed || formArmed || navArmed || fetchArmed);
    }

    function resetFormWait() {
        if (formTimer) {
            clearTimeout(formTimer);
            formTimer = null;
        }
        formArmed = false;
        updateVisual();
    }

    function resetAll() {
        if (formTimer) {
            clearTimeout(formTimer);
            formTimer = null;
        }
        if (navTimer) {
            clearTimeout(navTimer);
            navTimer = null;
        }
        if (fetchTimer) {
            clearTimeout(fetchTimer);
            fetchTimer = null;
        }
        formArmed = false;
        navArmed = false;
        navClickPending = false;
        bootArmed = false;
        fetchArmed = false;
        activeFetchCount = 0;
        setVisualActive(false, true);
    }

    function documentForReloadLocation(loc) {
        try {
            if (loc === window.location) {
                return document;
            }
            if (window.opener && window.opener.location === loc) {
                return window.opener.document;
            }
        } catch (e) {
            /* ignore */
        }
        return document;
    }

    function reloadWithWaitCursor(loc) {
        loc = loc || window.location;
        const doc = documentForReloadLocation(loc);
        rememberNextPageLoading();
        try {
            setDocumentVisualActive(doc, true, true);
        } catch (e) {
            /* ignore */
        }
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                setTimeout(function () {
                    if (nativeLocationReload) {
                        nativeLocationReload.call(loc);
                    } else {
                        loc.reload();
                    }
                }, 0);
            });
        });
    }

    function releaseBootWaitAfterReady() {
        let released = false;
        const release = function () {
            if (released) {
                return;
            }
            released = true;
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    setTimeout(function () {
                        bootArmed = false;
                        updateVisual();
                    }, BOOT_RELEASE_DELAY_MS);
                });
            });
        };

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", release, { once: true });
        } else {
            release();
        }

        setTimeout(function () {
            if (bootArmed) {
                bootArmed = false;
                updateVisual();
            }
        }, 2500);
    }

    function consumeBootWaitIfNeeded() {
        const root = document.documentElement;
        const hasEarlyClass = root && root.classList && root.classList.contains(BOOT_CLASS_NAME);
        if (!hasPendingNextPageLoading() && !hasEarlyClass) {
            return;
        }

        clearNextPageLoading();
        bootArmed = true;
        setVisualActive(true, true);
        releaseBootWaitAfterReady();
    }

    window.ArborisReloadWithLongWait = function (optLocation) {
        reloadWithWaitCursor(optLocation || window.location);
    };

    if (nativeLocationReload && !Location.prototype.__arborisReloadPatched) {
        Location.prototype.reload = function () {
            reloadWithWaitCursor(this);
        };
        Location.prototype.__arborisReloadPatched = true;
    }

    window.ArborisArmLongWaitNavigation = armNavigationLongWait;

    /** Per navigazioni JS (es. click su riga tabella con data-row-href). */
    window.ArborisArmLongWaitForNavigationUrl = function (destUrlString) {
        armLongWaitIfSameOriginFullNavigation(destUrlString, window.location.href);
    };

    window.ArborisResetLongWaitCursor = resetAll;
    consumeBootWaitIfNeeded();

    function isPopupOrModalLink(anchor) {
        if (!anchor || !anchor.dataset) {
            return false;
        }

        if (
            anchor.dataset.windowPopup === "1" ||
            anchor.dataset.calendarEventPopup === "1" ||
            anchor.dataset.calendarSelectedCreate === "1" ||
            anchor.dataset.popupUrl
        ) {
            return true;
        }

        try {
            const url = new URL(anchor.href, window.location.href);
            return url.searchParams.get("popup") === "1";
        } catch (e) {
            return false;
        }
    }

    function shouldSkipLongWaitForLink(anchor) {
        if (!anchor) {
            return false;
        }

        if (anchor.hasAttribute("download")) {
            return true;
        }

        if (!anchor.dataset) {
            return false;
        }

        return anchor.dataset.longWaitSkip === "1" || anchor.dataset.noLongWait === "1";
    }

    function isCurrentWindowLocation(loc) {
        try {
            return loc === window.location || (typeof document !== "undefined" && loc === document.location);
        } catch (e) {
            return false;
        }
    }

    if (typeof Location !== "undefined" && Location.prototype) {
        const L = Location.prototype;
        if (typeof L.assign === "function" && !L.__arborisAssignPatched) {
            const nativeAssign = L.assign;
            L.assign = function (url) {
                if (isCurrentWindowLocation(this)) {
                    armLongWaitIfSameOriginFullNavigation(url, this.href);
                }
                return nativeAssign.call(this, url);
            };
            L.__arborisAssignPatched = true;
        }
        if (typeof L.replace === "function" && !L.__arborisReplacePatched) {
            const nativeReplace = L.replace;
            L.replace = function (url) {
                if (isCurrentWindowLocation(this)) {
                    armLongWaitIfSameOriginFullNavigation(url, this.href);
                }
                return nativeReplace.call(this, url);
            };
            L.__arborisReplacePatched = true;
        }
        try {
            const hrefDesc = Object.getOwnPropertyDescriptor(L, "href");
            if (hrefDesc && typeof hrefDesc.set === "function" && !L.__arborisHrefSetPatched) {
                const nativeHrefSet = hrefDesc.set;
                Object.defineProperty(L, "href", {
                    configurable: true,
                    enumerable: hrefDesc.enumerable,
                    get: hrefDesc.get,
                    set: function (v) {
                        if (isCurrentWindowLocation(this)) {
                            armLongWaitIfSameOriginFullNavigation(v, this.href);
                        }
                        nativeHrefSet.call(this, v);
                    },
                });
                L.__arborisHrefSetPatched = true;
            }
        } catch (e) {
            /* Location.href non ridefinibile in alcuni browser */
        }
    }

    document.addEventListener(
        "submit",
        function (event) {
            if (formTimer) {
                clearTimeout(formTimer);
            }
            formArmed = false;
            rememberNextPageLoading();
            updateVisual();
            formTimer = setTimeout(function () {
                formTimer = null;
                formArmed = true;
                updateVisual();
            }, FORM_DELAY_MS);

            setTimeout(function () {
                if (event.defaultPrevented) {
                    clearNextPageLoading();
                    resetFormWait();
                }
            }, 0);
        },
        true
    );

    document.addEventListener(
        "click",
        function (e) {
            if (!e.target || !e.target.closest) {
                return;
            }
            const a = e.target.closest("a");
            if (!a) {
                return;
            }
            if (e.defaultPrevented || e.button !== 0) {
                return;
            }
            if (a.target === "_blank" || shouldSkipLongWaitForLink(a)) {
                return;
            }
            if (isPopupOrModalLink(a)) {
                return;
            }
            const hrefAttr = (a.getAttribute("href") || "").trim();
            if (!hrefAttr || hrefAttr === "#" || hrefAttr.toLowerCase().startsWith("javascript:")) {
                return;
            }
            armLongWaitIfSameOriginFullNavigation(a.href, window.location.href);
        },
        true
    );

    document.addEventListener(
        "click",
        function (e) {
            if (navClickPending && e.defaultPrevented) {
                if (navTimer) {
                    clearTimeout(navTimer);
                    navTimer = null;
                }
                clearNextPageLoading();
                navClickPending = false;
                navArmed = false;
                updateVisual();
            }
        },
        false
    );

    window.addEventListener("beforeunload", rememberNextPageLoading);
    window.addEventListener("pagehide", resetAll);
    window.addEventListener("pageshow", resetAll);

    function scheduleFetchWaitArmed() {
        activeFetchCount++;
        if (activeFetchCount === 1) {
            fetchTimer = setTimeout(function () {
                fetchTimer = null;
                if (activeFetchCount > 0) {
                    fetchArmed = true;
                    updateVisual();
                }
            }, FETCH_DELAY_MS);
        }
    }

    function releaseFetchWait() {
        activeFetchCount = Math.max(0, activeFetchCount - 1);
        if (activeFetchCount === 0) {
            if (fetchTimer) {
                clearTimeout(fetchTimer);
                fetchTimer = null;
            }
            fetchArmed = false;
            updateVisual();
        }
    }

    if (typeof window.fetch === "function" && !window.__arborisLongWaitFetchPatched) {
        window.__arborisLongWaitFetchPatched = true;
        const nativeFetch = window.fetch.bind(window);
        window.fetch = function () {
            scheduleFetchWaitArmed();
            return nativeFetch.apply(this, arguments).finally(function () {
                releaseFetchWait();
            });
        };
    }
})();
