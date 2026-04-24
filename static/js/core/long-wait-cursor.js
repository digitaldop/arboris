/**
 * Mostra il cursore di attesa (wait) se un'azione impiega più di 1 secondo:
 * invio form, navigazione con link interni, richieste fetch in corso.
 *
 * Navigazione via location.assign / href / click su riga (data-row-href): stesso
 * timer di attesa dei link.
 *
 * location.reload() è sincrono rispetto al paint: si arma il cursore e si
 * rimanda il reload (doppio rAF + setTimeout(0)) così il browser può ridisegnare.
 */
(function () {
    const DELAY_MS = 1000;
    const CLASS_NAME = "arboris-long-wait";

    let formTimer = null;
    let formArmed = false;

    let navTimer = null;
    let navArmed = false;
    let navClickPending = false;

    function armNavigationLongWait() {
        if (navTimer) {
            clearTimeout(navTimer);
        }
        navArmed = false;
        navClickPending = true;
        updateVisual();
        navTimer = setTimeout(function () {
            navTimer = null;
            if (navClickPending) {
                navArmed = true;
                updateVisual();
            }
        }, DELAY_MS);
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
        if (formArmed || navArmed || fetchArmed) {
            document.documentElement.classList.add(CLASS_NAME);
        } else {
            document.documentElement.classList.remove(CLASS_NAME);
        }
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
        fetchArmed = false;
        activeFetchCount = 0;
        document.documentElement.classList.remove(CLASS_NAME);
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
        try {
            if (doc.documentElement) {
                doc.documentElement.classList.add(CLASS_NAME);
            }
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
        function () {
            if (formTimer) {
                clearTimeout(formTimer);
            }
            formArmed = false;
            updateVisual();
            formTimer = setTimeout(function () {
                formTimer = null;
                formArmed = true;
                updateVisual();
            }, DELAY_MS);
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
            if (a.target === "_blank" || a.hasAttribute("download")) {
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
                navClickPending = false;
                navArmed = false;
                updateVisual();
            }
        },
        false
    );

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
            }, DELAY_MS);
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
