(function () {
    const DAY_NAMES_FULL = ["Domenica", "Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato"];
    const DAY_NAMES_SHORT = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
    const WEEKDAY_HEADERS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
    const MONTH_NAMES = [
        "Gennaio",
        "Febbraio",
        "Marzo",
        "Aprile",
        "Maggio",
        "Giugno",
        "Luglio",
        "Agosto",
        "Settembre",
        "Ottobre",
        "Novembre",
        "Dicembre",
    ];
    const WEEK_START_HOUR = 7;
    const WEEK_END_HOUR = 21;
    const MAX_MONTH_EVENTS_PER_DAY = 3;
    const DAY_SELECTION_RENDER_DELAY_MS = 260;
    const DEFAULT_EVENT_COLOR = "#3b82f6";

    function parseISODate(value) {
        if (!value) {
            return null;
        }

        const parts = value.split("-").map(Number);
        if (parts.length !== 3 || parts.some(Number.isNaN)) {
            return null;
        }

        return new Date(parts[0], parts[1] - 1, parts[2]);
    }

    function formatDateKey(value) {
        const year = value.getFullYear();
        const month = `${value.getMonth() + 1}`.padStart(2, "0");
        const day = `${value.getDate()}`.padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    function cloneDate(value) {
        return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }

    function addDays(value, days) {
        const next = cloneDate(value);
        next.setDate(next.getDate() + days);
        return next;
    }

    function addMonths(value, months) {
        return new Date(value.getFullYear(), value.getMonth() + months, 1);
    }

    function addYears(value, years) {
        return new Date(value.getFullYear() + years, value.getMonth(), value.getDate());
    }

    function startOfMonth(value) {
        return new Date(value.getFullYear(), value.getMonth(), 1);
    }

    function startOfWeek(value) {
        const next = cloneDate(value);
        const dayOffset = (next.getDay() + 6) % 7;
        next.setDate(next.getDate() - dayOffset);
        return next;
    }

    function isSameDay(left, right) {
        return (
            left.getFullYear() === right.getFullYear() &&
            left.getMonth() === right.getMonth() &&
            left.getDate() === right.getDate()
        );
    }

    function isSameMonth(left, right) {
        return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth();
    }

    function formatDateLabel(value) {
        return `${DAY_NAMES_FULL[value.getDay()]} ${value.getDate()} ${MONTH_NAMES[value.getMonth()]} ${value.getFullYear()}`;
    }

    function formatWeekTitle(value) {
        const start = startOfWeek(value);
        const end = addDays(start, 6);

        if (start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear()) {
            return `${start.getDate()} - ${end.getDate()} ${MONTH_NAMES[start.getMonth()]} ${start.getFullYear()}`;
        }

        if (start.getFullYear() === end.getFullYear()) {
            return `${start.getDate()} ${MONTH_NAMES[start.getMonth()]} - ${end.getDate()} ${MONTH_NAMES[end.getMonth()]} ${start.getFullYear()}`;
        }

        return `${start.getDate()} ${MONTH_NAMES[start.getMonth()]} ${start.getFullYear()} - ${end.getDate()} ${MONTH_NAMES[end.getMonth()]} ${end.getFullYear()}`;
    }

    function formatMonthTitle(value) {
        return `${MONTH_NAMES[value.getMonth()]} ${value.getFullYear()}`;
    }

    function formatYearTitle(value) {
        return `${value.getFullYear()}`;
    }

    function parseTimeToMinutes(value) {
        if (!value || !value.includes(":")) {
            return WEEK_START_HOUR * 60;
        }

        const parts = value.split(":").map(Number);
        return (parts[0] || 0) * 60 + (parts[1] || 0);
    }

    function normalizeEntry(entry) {
        const startDate = parseISODate(entry.start_date);
        const endDate = parseISODate(entry.end_date) || startDate;
        const startMinutes = parseTimeToMinutes(entry.start_time);
        let endMinutes = entry.end_time ? parseTimeToMinutes(entry.end_time) : startMinutes + 60;

        if (endMinutes <= startMinutes) {
            endMinutes = startMinutes + 60;
        }

        return {
            ...entry,
            color: entry.color || DEFAULT_EVENT_COLOR,
            startDate,
            endDate,
            startMinutes,
            endMinutes,
        };
    }

    function overlapsDay(entry, day) {
        return entry.startDate <= day && entry.endDate >= day;
    }

    function getEntriesForDay(entries, day) {
        return entries.filter((entry) => overlapsDay(entry, day));
    }

    function sortEntries(entries) {
        return [...entries].sort((left, right) => {
            if (left.all_day !== right.all_day) {
                return left.all_day ? -1 : 1;
            }

            if (left.startMinutes !== right.startMinutes) {
                return left.startMinutes - right.startMinutes;
            }

            return left.title.localeCompare(right.title, "it");
        });
    }

    function hexToRgb(hex) {
        const normalized = (hex || DEFAULT_EVENT_COLOR).replace("#", "").trim();
        if (normalized.length !== 6) {
            return { r: 59, g: 130, b: 246 };
        }

        const parsed = Number.parseInt(normalized, 16);
        if (Number.isNaN(parsed)) {
            return { r: 59, g: 130, b: 246 };
        }

        return {
            r: (parsed >> 16) & 255,
            g: (parsed >> 8) & 255,
            b: parsed & 255,
        };
    }

    function applyEntryPalette(element, color) {
        const rgb = hexToRgb(color);
        element.style.setProperty("--calendar-entry-color", color || DEFAULT_EVENT_COLOR);
        element.style.setProperty("--calendar-entry-color-rgb", `${rgb.r}, ${rgb.g}, ${rgb.b}`);
    }

    function buildPopupUrl(rawUrl) {
        const url = new URL(rawUrl, window.location.origin);
        url.searchParams.set("popup", "1");
        return `${url.pathname}${url.search}${url.hash}`;
    }

    function buildCalendarReturnUrl() {
        return `${window.location.pathname}${window.location.search}${window.location.hash}`;
    }

    function buildCalendarNavigationUrl(rawUrl) {
        const url = new URL(rawUrl, window.location.origin);
        if (url.origin !== window.location.origin) {
            return rawUrl;
        }
        url.searchParams.set("next", buildCalendarReturnUrl());
        return `${url.pathname}${url.search}${url.hash}`;
    }

    function canOpenEntryInPopup(entry) {
        if (!entry || !entry.url || !entry.open_in_popup || entry.external) {
            return false;
        }

        try {
            return new URL(entry.url, window.location.origin).origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    function canShowEntryContextAction(entry) {
        return canOpenEntryInPopup(entry) && entry.source === "locale";
    }

    function getEntryPopupTitle(entry) {
        if (entry && entry.popup_title) {
            return entry.popup_title;
        }
        return entry && entry.source === "locale" ? "Modifica evento calendario" : "Dettaglio calendario";
    }

    function createEntryLink(entry, className, label, meta, isBlock, state, contextDay) {
        const hasLink = Boolean(entry.url);
        const element = document.createElement(hasLink ? "a" : "div");
        element.className = className;
        element.dataset.calendarEntryId = entry.id;
        applyEntryPalette(element, entry.color);

        if (hasLink) {
            if (canOpenEntryInPopup(entry)) {
                element.href = buildPopupUrl(entry.url);
                element.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    openCalendarEntryPopup(entry);
                });
            } else {
                element.href = buildCalendarNavigationUrl(entry.url);
            }
            if (entry.external) {
                element.target = "_blank";
                element.rel = "noopener noreferrer";
            }
        }

        if (state && canShowEntryContextAction(entry)) {
            element.addEventListener("contextmenu", function (event) {
                openCalendarContextMenu(state, event, contextDay || entry.startDate, {
                    allDay: entry.all_day,
                    entry: entry,
                    updateCurrentDate: true,
                });
            });
        }

        const badge = document.createElement("span");
        badge.className = "calendar-entry-badge";
        badge.textContent = entry.badge_label;
        applyEntryPalette(badge, entry.color);
        element.appendChild(badge);

        const title = document.createElement("span");
        title.className = isBlock ? "calendar-entry-block-title" : "calendar-entry-title";
        title.textContent = label;
        element.appendChild(title);

        if (meta) {
            const metaLine = document.createElement("span");
            metaLine.className = isBlock ? "calendar-entry-block-meta" : "calendar-entry-meta";
            metaLine.textContent = meta;
            element.appendChild(metaLine);
        }

        return element;
    }

    function getTimeLabel(entry) {
        if (entry.all_day) {
            return "Intera giornata";
        }

        if (entry.start_time && entry.end_time) {
            return `${entry.start_time} - ${entry.end_time}`;
        }

        if (entry.start_time) {
            return entry.start_time;
        }

        return "";
    }

    function buildQuickCreateUrl(baseUrl, values) {
        const url = new URL(baseUrl, window.location.origin);

        if (values.date) {
            url.searchParams.set("date", values.date);
        }
        if (values.endDate) {
            url.searchParams.set("end_date", values.endDate);
        }
        if (values.time && !values.all_day) {
            url.searchParams.set("time", values.time);
        }
        if (values.duration && !values.all_day) {
            url.searchParams.set("duration", values.duration);
        }
        url.searchParams.set("all_day", values.all_day ? "1" : "0");

        if (values.categoryId) {
            url.searchParams.set("categoria_evento", values.categoryId);
        }

        return `${url.pathname}${url.search}`;
    }

    function openManagedCalendarPopup(url, title, features) {
        if (window.ArborisRelatedPopups && typeof window.ArborisRelatedPopups.openManagedPopup === "function") {
            window.ArborisRelatedPopups.openManagedPopup(
                url,
                "calendar_event_popup",
                features || "width=920,height=760,resizable=yes,scrollbars=yes",
                {
                    title: title || "Calendario Arboris",
                    lockMessage: "Completa il popup del calendario per continuare.",
                }
            );
            return;
        }

        if (window.ArborisModalPopups && typeof window.ArborisModalPopups.open === "function") {
            window.ArborisModalPopups.open(url, {
                features: features || "width=920,height=760,resizable=yes,scrollbars=yes",
                title: title || "Calendario Arboris",
            });
            return;
        }

        window.location.href = url;
    }

    function openEventCreatePopup(state, values) {
        if (!state.canManage || !state.categories.length) {
            return;
        }

        const config = values || {};
        const url = buildPopupUrl(buildQuickCreateUrl(state.fullCreateUrl, {
            date: config.date || formatDateKey(state.selectedDate),
            endDate: config.endDate,
            time: config.time,
            duration: config.duration,
            allDay: config.allDay !== false,
            categoryId: config.categoryId,
        }));
        openManagedCalendarPopup(url, "Nuovo evento calendario", "width=920,height=760,resizable=yes,scrollbars=yes");
    }

    function updateSelectedCreateLinks(state) {
        const selectedDateKey = formatDateKey(state.selectedDate);
        document.querySelectorAll("[data-calendar-selected-create='1']").forEach((trigger) => {
            const baseUrl = trigger.dataset.calendarBaseUrl
                || trigger.dataset.popupUrl
                || trigger.getAttribute("href")
                || state.fullCreateUrl;
            if (!baseUrl) {
                return;
            }

            if (!trigger.dataset.calendarBaseUrl) {
                trigger.dataset.calendarBaseUrl = baseUrl;
            }

            const selectedUrl = buildQuickCreateUrl(baseUrl, {
                date: selectedDateKey,
                allDay: true,
            });
            trigger.dataset.calendarSelectedDate = selectedDateKey;
            trigger.setAttribute("href", selectedUrl);
            if (trigger.hasAttribute("data-popup-url")) {
                trigger.dataset.popupUrl = selectedUrl;
            }
        });
    }

    function getSelectedCreateDate(trigger, state) {
        if (trigger.dataset.calendarSelectedDate) {
            return trigger.dataset.calendarSelectedDate;
        }

        const rawUrl = trigger.dataset.popupUrl || trigger.getAttribute("href");
        if (rawUrl) {
            try {
                const url = new URL(rawUrl, window.location.origin);
                const requestedDate = url.searchParams.get("date");
                if (requestedDate && parseISODate(requestedDate)) {
                    return requestedDate;
                }
            } catch (error) {
                // Keep the selected state as fallback when the link is not a valid URL.
            }
        }

        return formatDateKey(state.selectedDate);
    }

    function openCalendarEntryPopup(entry) {
        if (!entry || !entry.url) {
            return;
        }
        openManagedCalendarPopup(
            buildPopupUrl(entry.url),
            getEntryPopupTitle(entry),
            "width=920,height=760,resizable=yes,scrollbars=yes"
        );
    }

    function bindCalendarEventPopupLinks() {
        if (document.documentElement.dataset.calendarEventPopupLinksBound === "1") {
            return;
        }
        document.documentElement.dataset.calendarEventPopupLinksBound = "1";

        document.addEventListener("click", function (event) {
            const trigger = event.target.closest("[data-calendar-event-popup='1']");
            if (!trigger) {
                return;
            }

            const rawUrl = trigger.dataset.popupUrl || trigger.getAttribute("href");
            if (!rawUrl) {
                return;
            }

            event.preventDefault();
            event.stopImmediatePropagation();
            openManagedCalendarPopup(
                buildPopupUrl(rawUrl),
                trigger.dataset.popupTitle || "Dettaglio calendario",
                trigger.dataset.popupWindowFeatures || "width=920,height=760,resizable=yes,scrollbars=yes"
            );
        }, true);

    }

    function bindSelectedCreatePopupLinks(state) {
        if (document.documentElement.dataset.calendarSelectedCreateLinksBound === "1") {
            return;
        }
        document.documentElement.dataset.calendarSelectedCreateLinksBound = "1";

        document.addEventListener("click", function (event) {
            const trigger = event.target.closest("[data-calendar-selected-create='1']");
            if (!trigger) {
                return;
            }

            event.preventDefault();
            event.stopImmediatePropagation();
            openEventCreatePopup(state, {
                date: getSelectedCreateDate(trigger, state),
                allDay: true,
            });
        }, true);
    }

    function selectCalendarDay(state, day, options) {
        const config = options || {};
        clearPendingDayClick(state);
        state.selectedDate = cloneDate(day);
        if (config.updateCurrentDate) {
            state.currentDate = cloneDate(day);
        }
        updateSelectedCreateLinks(state);
        state.render();
    }

    function hideCalendarContextMenu(state) {
        if (!state.contextMenu) {
            return;
        }
        state.contextMenu.classList.remove("is-visible");
    }

    function getCalendarContextMenu(state) {
        if (state.contextMenu && state.contextMenu.parentNode) {
            return state.contextMenu;
        }

        const menu = document.createElement("div");
        menu.className = "calendar-context-menu";
        menu.setAttribute("role", "menu");
        menu.innerHTML = `
            <button type="button" class="calendar-context-menu-item" role="menuitem" data-calendar-context-create>
                Crea un evento
            </button>
            <button type="button" class="calendar-context-menu-item" role="menuitem" data-calendar-context-edit>
                Modifica Evento
            </button>
        `;
        document.body.appendChild(menu);

        menu.querySelector("[data-calendar-context-create]").addEventListener("click", function () {
            if (!state.contextMenuConfig) {
                hideCalendarContextMenu(state);
                return;
            }
            const config = state.contextMenuConfig;
            const options = config.options || {};
            hideCalendarContextMenu(state);
            selectCalendarDay(state, config.day, options);
            openEventCreatePopup(state, {
                date: formatDateKey(config.day),
                endDate: options.endDate,
                allDay: options.allDay !== false,
                time: options.time,
                duration: options.duration,
                categoryId: options.categoryId,
            });
        });

        menu.querySelector("[data-calendar-context-edit]").addEventListener("click", function () {
            if (!state.contextMenuConfig || !state.contextMenuConfig.options.entry) {
                hideCalendarContextMenu(state);
                return;
            }
            const entry = state.contextMenuConfig.options.entry;
            hideCalendarContextMenu(state);
            openCalendarEntryPopup(entry);
        });

        document.addEventListener("click", function (event) {
            if (!menu.contains(event.target)) {
                hideCalendarContextMenu(state);
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                hideCalendarContextMenu(state);
            }
        });
        window.addEventListener("scroll", function () {
            hideCalendarContextMenu(state);
        }, true);
        window.addEventListener("resize", function () {
            hideCalendarContextMenu(state);
        });

        state.contextMenu = menu;
        return menu;
    }

    function openCalendarContextMenu(state, event, day, options) {
        const configOptions = Object.assign({}, options || {});
        const hasEntryAction = canShowEntryContextAction(configOptions.entry);
        if (!state.canManage && !hasEntryAction) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        const menu = getCalendarContextMenu(state);
        if ((!state.canManage || !state.categories.length) && !hasEntryAction) {
            return;
        }
        state.contextMenuConfig = {
            day: cloneDate(day),
            options: configOptions,
        };

        const createButton = menu.querySelector("[data-calendar-context-create]");
        const editButton = menu.querySelector("[data-calendar-context-edit]");
        if (createButton) {
            createButton.hidden = !state.canManage || !state.categories.length;
        }
        if (editButton) {
            editButton.hidden = !hasEntryAction;
        }

        menu.style.left = "0";
        menu.style.top = "0";
        menu.classList.add("is-visible");

        const menuRect = menu.getBoundingClientRect();
        const viewportPadding = 10;
        const left = Math.min(
            event.clientX,
            window.innerWidth - menuRect.width - viewportPadding
        );
        const top = Math.min(
            event.clientY,
            window.innerHeight - menuRect.height - viewportPadding
        );
        menu.style.left = `${Math.max(viewportPadding, left)}px`;
        menu.style.top = `${Math.max(viewportPadding, top)}px`;
    }

    function openDayView(state, day) {
        clearPendingDayClick(state);
        state.selectedDate = cloneDate(day);
        state.currentDate = cloneDate(day);
        state.currentView = "day";
        state.render();
    }

    function clearPendingDayClick(state) {
        if (!state.pendingDayClickTimer) {
            return;
        }
        window.clearTimeout(state.pendingDayClickTimer);
        state.pendingDayClickTimer = null;
    }

    function updateRenderedDaySelection(state) {
        if (!state.renderTarget) {
            return;
        }

        const selectedDateKey = formatDateKey(state.selectedDate);
        state.renderTarget.querySelectorAll("[data-calendar-day-date]").forEach((node) => {
            node.classList.toggle("is-selected", node.dataset.calendarDayDate === selectedDateKey);
        });
    }

    function scheduleDaySelection(state, day, options) {
        const config = options || {};
        clearPendingDayClick(state);
        state.selectedDate = cloneDate(day);
        if (config.updateCurrentDate) {
            state.currentDate = cloneDate(day);
        }
        updateSelectedCreateLinks(state);
        updateToolbar(state);
        updateUrlState(state);
        updateRenderedDaySelection(state);
        updateSelectedDayPanel(state);
        state.pendingDayClickTimer = window.setTimeout(function () {
            state.pendingDayClickTimer = null;
            state.render();
        }, DAY_SELECTION_RENDER_DELAY_MS);
    }

    function updateSelectedDayPanel(state) {
        const panel = document.getElementById("calendar-selected-day-panel");
        if (!panel) {
            return;
        }

        const dayEntries = sortEntries(getEntriesForDay(state.entries, state.selectedDate));
        panel.innerHTML = "";

        const titleRow = document.createElement("div");
        titleRow.className = "calendar-selected-day-head";

        const title = document.createElement("div");
        title.className = "calendar-selected-day-title";
        title.textContent = formatDateLabel(state.selectedDate);
        titleRow.appendChild(title);

        if (state.canManage && state.categories.length) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-secondary btn-sm";
            button.textContent = "Nuovo evento";
            button.addEventListener("click", function () {
                state.quickDialog.open({
                    date: formatDateKey(state.selectedDate),
                    allDay: true,
                });
            });
            titleRow.appendChild(button);
        }

        panel.appendChild(titleRow);

        if (!dayEntries.length) {
            const empty = document.createElement("div");
            empty.className = "calendar-selected-day-empty";
            empty.textContent = "Nessun evento programmato per questo giorno.";
            panel.appendChild(empty);
            return;
        }

        dayEntries.forEach((entry) => {
            const item = document.createElement("div");
            item.className = "calendar-selected-day-item";

            const itemHead = document.createElement("div");
            itemHead.className = "calendar-selected-day-item-head";

            const badge = document.createElement("span");
            badge.className = "calendar-entry-badge";
            badge.textContent = entry.badge_label;
            applyEntryPalette(badge, entry.color);
            itemHead.appendChild(badge);

            const time = document.createElement("span");
            time.className = "calendar-selected-day-item-time";
            time.textContent = getTimeLabel(entry);
            itemHead.appendChild(time);
            item.appendChild(itemHead);

            const titleNode = document.createElement(entry.url ? "a" : "div");
            titleNode.className = "calendar-selected-day-item-title";
            titleNode.textContent = entry.title;
            if (entry.url) {
                if (canOpenEntryInPopup(entry)) {
                    titleNode.href = buildPopupUrl(entry.url);
                    titleNode.addEventListener("click", function (event) {
                        event.preventDefault();
                        openCalendarEntryPopup(entry);
                    });
                    if (canShowEntryContextAction(entry)) {
                        titleNode.addEventListener("contextmenu", function (event) {
                            openCalendarContextMenu(state, event, state.selectedDate, {
                                allDay: entry.all_day,
                                entry: entry,
                                updateCurrentDate: true,
                            });
                        });
                    }
                } else {
                    titleNode.href = buildCalendarNavigationUrl(entry.url);
                }
                if (entry.external) {
                    titleNode.target = "_blank";
                    titleNode.rel = "noopener noreferrer";
                }
            }
            item.appendChild(titleNode);

            const metaParts = [entry.category_label];
            if (entry.detail_label) {
                metaParts.push(entry.detail_label);
            }
            if (entry.location) {
                metaParts.push(entry.location);
            }

            const meta = document.createElement("div");
            meta.className = "calendar-selected-day-item-meta";
            meta.textContent = metaParts.join(" - ");
            item.appendChild(meta);

            if (entry.description) {
                const description = document.createElement("div");
                description.className = "calendar-selected-day-item-description";
                description.textContent = entry.description;
                item.appendChild(description);
            }

            panel.appendChild(item);
        });
    }

    function buildMonthView(state, renderTarget) {
        const monthStart = startOfMonth(state.currentDate);
        const gridStart = startOfWeek(monthStart);

        const wrapper = document.createElement("div");
        wrapper.className = "calendar-month-view";

        const weekdays = document.createElement("div");
        weekdays.className = "calendar-month-weekdays";
        WEEKDAY_HEADERS.forEach((dayName) => {
            const cell = document.createElement("div");
            cell.className = "calendar-month-weekday";
            cell.textContent = dayName;
            weekdays.appendChild(cell);
        });
        wrapper.appendChild(weekdays);

        const daysGrid = document.createElement("div");
        daysGrid.className = "calendar-month-days";

        for (let index = 0; index < 42; index += 1) {
            const day = addDays(gridStart, index);
            const dayEntries = sortEntries(getEntriesForDay(state.entries, day));
            const cell = document.createElement("div");
            cell.className = "calendar-month-cell";
            cell.dataset.calendarDayDate = formatDateKey(day);

            if (!isSameMonth(day, monthStart)) {
                cell.classList.add("is-other-month");
            }
            if (isSameDay(day, new Date())) {
                cell.classList.add("is-today");
            }
            if (isSameDay(day, state.selectedDate)) {
                cell.classList.add("is-selected");
            }

            cell.addEventListener("click", function (event) {
                if (event.target.closest("a, button")) {
                    return;
                }
                scheduleDaySelection(state, day, {
                    updateCurrentDate: !isSameMonth(day, monthStart),
                    allDay: true,
                });
            });

            cell.addEventListener("dblclick", function (event) {
                if (event.target.closest("a, button")) {
                    return;
                }
                event.preventDefault();
                openDayView(state, day);
            });

            cell.addEventListener("contextmenu", function (event) {
                if (event.target.closest("a, button")) {
                    return;
                }
                openCalendarContextMenu(state, event, day, {
                    updateCurrentDate: !isSameMonth(day, monthStart),
                    allDay: true,
                });
            });

            const dayButton = document.createElement("button");
            dayButton.type = "button";
            dayButton.className = "calendar-day-button";
            dayButton.dataset.calendarDayDate = formatDateKey(day);
            dayButton.textContent = `${day.getDate()}`;
            dayButton.addEventListener("click", (event) => {
                event.stopPropagation();
                scheduleDaySelection(state, day, {
                    updateCurrentDate: true,
                    allDay: true,
                });
            });
            dayButton.addEventListener("dblclick", (event) => {
                event.preventDefault();
                event.stopPropagation();
                openDayView(state, day);
            });
            dayButton.addEventListener("contextmenu", (event) => {
                openCalendarContextMenu(state, event, day, {
                    updateCurrentDate: true,
                    allDay: true,
                });
            });
            cell.appendChild(dayButton);

            const eventsBox = document.createElement("div");
            eventsBox.className = "calendar-month-events";

            dayEntries.slice(0, MAX_MONTH_EVENTS_PER_DAY).forEach((entry) => {
                const label = entry.all_day ? entry.title : `${entry.start_time || ""} ${entry.title}`.trim();
                eventsBox.appendChild(createEntryLink(entry, "calendar-entry-chip", label, "", false, state, day));
            });

            if (dayEntries.length > MAX_MONTH_EVENTS_PER_DAY) {
                const more = document.createElement("div");
                more.className = "calendar-month-more";
                more.textContent = `+${dayEntries.length - MAX_MONTH_EVENTS_PER_DAY} altri`;
                eventsBox.appendChild(more);
            }

            cell.appendChild(eventsBox);
            daysGrid.appendChild(cell);
        }

        wrapper.appendChild(daysGrid);
        renderTarget.appendChild(wrapper);
    }

    function assignWeekColumns(entries) {
        const activeColumns = [];
        let maxColumns = 1;

        entries.forEach((entry) => {
            let columnIndex = 0;
            while (activeColumns[columnIndex] > entry.startMinutes) {
                columnIndex += 1;
            }
            activeColumns[columnIndex] = entry.endMinutes;
            entry._columnIndex = columnIndex;
            maxColumns = Math.max(maxColumns, columnIndex + 1);
        });

        entries.forEach((entry) => {
            entry._columnCount = maxColumns;
        });
    }

    function buildWeekView(state, renderTarget) {
        const weekStart = startOfWeek(state.currentDate);
        const hours = [];
        for (let hour = WEEK_START_HOUR; hour < WEEK_END_HOUR; hour += 1) {
            hours.push(hour);
        }

        const wrapper = document.createElement("div");
        wrapper.className = "calendar-week-view";

        const header = document.createElement("div");
        header.className = "calendar-week-header";

        const spacer = document.createElement("div");
        spacer.className = "calendar-week-time-header";
        spacer.textContent = "Ora";
        header.appendChild(spacer);

        for (let offset = 0; offset < 7; offset += 1) {
            const day = addDays(weekStart, offset);
            const dayButton = document.createElement("button");
            dayButton.type = "button";
            dayButton.className = "calendar-week-day-button";
            dayButton.dataset.calendarDayDate = formatDateKey(day);
            if (isSameDay(day, state.selectedDate)) {
                dayButton.classList.add("is-selected");
            }
            if (isSameDay(day, new Date())) {
                dayButton.classList.add("is-today");
            }
            dayButton.innerHTML = `<span>${DAY_NAMES_SHORT[day.getDay()]}</span><strong>${day.getDate()}</strong>`;
            dayButton.addEventListener("click", () => {
                state.selectedDate = cloneDate(day);
                state.currentDate = cloneDate(day);
                state.render();
            });
            dayButton.addEventListener("dblclick", (event) => {
                event.preventDefault();
                openDayView(state, day);
            });
            dayButton.addEventListener("contextmenu", (event) => {
                openCalendarContextMenu(state, event, day, {
                    updateCurrentDate: true,
                    allDay: true,
                });
            });
            header.appendChild(dayButton);
        }

        wrapper.appendChild(header);

        const allDayRow = document.createElement("div");
        allDayRow.className = "calendar-week-all-day-row";

        const allDayLabel = document.createElement("div");
        allDayLabel.className = "calendar-week-all-day-label";
        allDayLabel.textContent = "Intera giornata";
        allDayRow.appendChild(allDayLabel);

        for (let offset = 0; offset < 7; offset += 1) {
            const day = addDays(weekStart, offset);
            const cell = document.createElement("div");
            cell.className = "calendar-week-all-day-cell";
            cell.dataset.calendarDayDate = formatDateKey(day);

            cell.addEventListener("click", function (event) {
                if (event.target.closest("a")) {
                    return;
                }
                state.selectedDate = cloneDate(day);
                state.render();
            });
            cell.addEventListener("contextmenu", function (event) {
                if (event.target.closest("a")) {
                    return;
                }
                openCalendarContextMenu(state, event, day, {
                    updateCurrentDate: true,
                    allDay: true,
                });
            });

            const allDayEntries = sortEntries(
                getEntriesForDay(state.entries, day).filter(
                    (entry) => entry.all_day || !isSameDay(entry.startDate, entry.endDate)
                )
            );

            if (!allDayEntries.length) {
                cell.innerHTML = `<div class="calendar-week-empty">${state.canManage ? "+" : "-"}</div>`;
            } else {
                allDayEntries.forEach((entry) => {
                    cell.appendChild(createEntryLink(entry, "calendar-entry-chip", entry.title, "", false, state, day));
                });
            }

            allDayRow.appendChild(cell);
        }

        wrapper.appendChild(allDayRow);

        const grid = document.createElement("div");
        grid.className = "calendar-week-grid";

        const timeColumn = document.createElement("div");
        timeColumn.className = "calendar-week-time-column";
        hours.forEach((hour) => {
            const label = document.createElement("div");
            label.className = "calendar-week-time-label";
            label.textContent = `${`${hour}`.padStart(2, "0")}:00`;
            timeColumn.appendChild(label);
        });
        grid.appendChild(timeColumn);

        const daysContainer = document.createElement("div");
        daysContainer.className = "calendar-week-days";
        const totalMinutes = (WEEK_END_HOUR - WEEK_START_HOUR) * 60;

        for (let offset = 0; offset < 7; offset += 1) {
            const day = addDays(weekStart, offset);
            const column = document.createElement("div");
            column.className = "calendar-week-day-column";
            column.dataset.calendarDayDate = formatDateKey(day);
            if (isSameDay(day, state.selectedDate)) {
                column.classList.add("is-selected");
            }

            hours.forEach((hour) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "calendar-week-hour-row";
                row.dataset.calendarDayDate = formatDateKey(day);
                row.addEventListener("click", function () {
                    state.selectedDate = cloneDate(day);
                    state.render();
                });
                row.addEventListener("contextmenu", function (event) {
                    openCalendarContextMenu(state, event, day, {
                        updateCurrentDate: true,
                        allDay: false,
                        time: `${`${hour}`.padStart(2, "0")}:00`,
                        duration: 60,
                    });
                });
                column.appendChild(row);
            });

            const eventsLayer = document.createElement("div");
            eventsLayer.className = "calendar-week-events-layer";

            const timedEntries = sortEntries(
                getEntriesForDay(state.entries, day).filter(
                    (entry) => !entry.all_day && isSameDay(entry.startDate, entry.endDate)
                )
            );
            assignWeekColumns(timedEntries);

            timedEntries.forEach((entry) => {
                const block = createEntryLink(
                    entry,
                    "calendar-week-event-block",
                    entry.title,
                    `${getTimeLabel(entry)}${entry.location ? ` - ${entry.location}` : ""}`,
                    true,
                    state,
                    day
                );

                const clampedStart = Math.max(entry.startMinutes, WEEK_START_HOUR * 60);
                const clampedEnd = Math.min(entry.endMinutes, WEEK_END_HOUR * 60);
                const top = ((clampedStart - WEEK_START_HOUR * 60) / totalMinutes) * 100;
                const height = Math.max(((clampedEnd - clampedStart) / totalMinutes) * 100, 6);
                const width = 100 / entry._columnCount;
                const left = width * entry._columnIndex;

                block.style.top = `${top}%`;
                block.style.height = `${height}%`;
                block.style.left = `calc(${left}% + 4px)`;
                block.style.width = `calc(${width}% - 8px)`;
                eventsLayer.appendChild(block);
            });

            column.appendChild(eventsLayer);
            daysContainer.appendChild(column);
        }

        grid.appendChild(daysContainer);
        wrapper.appendChild(grid);
        renderTarget.appendChild(wrapper);
    }

    function buildDayView(state, renderTarget) {
        const day = cloneDate(state.currentDate);
        const hours = [];
        for (let hour = WEEK_START_HOUR; hour < WEEK_END_HOUR; hour += 1) {
            hours.push(hour);
        }

        const wrapper = document.createElement("div");
        wrapper.className = "calendar-day-view";

        const hero = document.createElement("div");
        hero.className = "calendar-day-hero";
        hero.innerHTML = `
            <div class="calendar-day-hero-label">Vista giornaliera</div>
            <div class="calendar-day-hero-title">${formatDateLabel(day)}</div>
            <div class="calendar-day-hero-meta">${getEntriesForDay(state.entries, day).length} eventi e scadenze in programma</div>
        `;
        wrapper.appendChild(hero);

        const allDayRow = document.createElement("div");
        allDayRow.className = "calendar-day-all-day-row";

        const allDayLabel = document.createElement("div");
        allDayLabel.className = "calendar-day-all-day-label";
        allDayLabel.textContent = "Intera giornata";
        allDayRow.appendChild(allDayLabel);

        const allDayCell = document.createElement("div");
        allDayCell.className = "calendar-day-all-day-cell";
        allDayCell.dataset.calendarDayDate = formatDateKey(day);
        allDayCell.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                return;
            }
            state.selectedDate = cloneDate(day);
            state.render();
        });
        allDayCell.addEventListener("contextmenu", function (event) {
            if (event.target.closest("a")) {
                return;
            }
            openCalendarContextMenu(state, event, day, {
                updateCurrentDate: true,
                allDay: true,
            });
        });

        const allDayEntries = sortEntries(
            getEntriesForDay(state.entries, day).filter(
                (entry) => entry.all_day || !isSameDay(entry.startDate, entry.endDate)
            )
        );

        if (!allDayEntries.length) {
            allDayCell.innerHTML = `<div class="calendar-week-empty">${state.canManage ? "+" : "-"}</div>`;
        } else {
            allDayEntries.forEach((entry) => {
                allDayCell.appendChild(createEntryLink(entry, "calendar-entry-chip", entry.title, "", false, state, day));
            });
        }

        allDayRow.appendChild(allDayCell);
        wrapper.appendChild(allDayRow);

        const grid = document.createElement("div");
        grid.className = "calendar-day-grid";

        const timeColumn = document.createElement("div");
        timeColumn.className = "calendar-day-time-column";
        hours.forEach((hour) => {
            const label = document.createElement("div");
            label.className = "calendar-day-time-label";
            label.textContent = `${`${hour}`.padStart(2, "0")}:00`;
            timeColumn.appendChild(label);
        });
        grid.appendChild(timeColumn);

        const dayColumn = document.createElement("div");
        dayColumn.className = "calendar-day-column";

        hours.forEach((hour) => {
            const row = document.createElement("button");
            row.type = "button";
            row.className = "calendar-day-hour-row";
            row.dataset.calendarDayDate = formatDateKey(day);
            row.addEventListener("click", function () {
                state.selectedDate = cloneDate(day);
                state.render();
            });
            row.addEventListener("contextmenu", function (event) {
                openCalendarContextMenu(state, event, day, {
                    updateCurrentDate: true,
                    allDay: false,
                    time: `${`${hour}`.padStart(2, "0")}:00`,
                    duration: 60,
                });
            });
            dayColumn.appendChild(row);
        });

        const eventsLayer = document.createElement("div");
        eventsLayer.className = "calendar-day-events-layer";

        const totalMinutes = (WEEK_END_HOUR - WEEK_START_HOUR) * 60;
        const timedEntries = sortEntries(
            getEntriesForDay(state.entries, day).filter(
                (entry) => !entry.all_day && isSameDay(entry.startDate, entry.endDate)
            )
        );
        assignWeekColumns(timedEntries);

        timedEntries.forEach((entry) => {
            const block = createEntryLink(
                entry,
                "calendar-day-event-block",
                entry.title,
                `${getTimeLabel(entry)}${entry.location ? ` - ${entry.location}` : ""}`,
                true,
                state,
                day
            );

            const clampedStart = Math.max(entry.startMinutes, WEEK_START_HOUR * 60);
            const clampedEnd = Math.min(entry.endMinutes, WEEK_END_HOUR * 60);
            const top = ((clampedStart - WEEK_START_HOUR * 60) / totalMinutes) * 100;
            const height = Math.max(((clampedEnd - clampedStart) / totalMinutes) * 100, 6);
            const width = 100 / entry._columnCount;
            const left = width * entry._columnIndex;

            block.style.top = `${top}%`;
            block.style.height = `${height}%`;
            block.style.left = `calc(${left}% + 6px)`;
            block.style.width = `calc(${width}% - 12px)`;
            eventsLayer.appendChild(block);
        });

        dayColumn.appendChild(eventsLayer);
        grid.appendChild(dayColumn);
        wrapper.appendChild(grid);
        renderTarget.appendChild(wrapper);
    }

    function buildYearView(state, renderTarget) {
        const year = state.currentDate.getFullYear();
        const wrapper = document.createElement("div");
        wrapper.className = "calendar-year-view";

        for (let monthIndex = 0; monthIndex < 12; monthIndex += 1) {
            const monthDate = new Date(year, monthIndex, 1);
            const monthCard = document.createElement("section");
            monthCard.className = "calendar-year-card";

            const monthTitle = document.createElement("div");
            monthTitle.className = "calendar-year-card-title";
            monthTitle.textContent = `${MONTH_NAMES[monthIndex]} ${year}`;
            monthCard.appendChild(monthTitle);

            const weekdays = document.createElement("div");
            weekdays.className = "calendar-year-weekdays";
            WEEKDAY_HEADERS.forEach((dayName) => {
                const weekday = document.createElement("div");
                weekday.className = "calendar-year-weekday";
                weekday.textContent = dayName;
                weekdays.appendChild(weekday);
            });
            monthCard.appendChild(weekdays);

            const daysGrid = document.createElement("div");
            daysGrid.className = "calendar-year-days";
            const gridStart = startOfWeek(monthDate);

            for (let index = 0; index < 42; index += 1) {
                const day = addDays(gridStart, index);
                const dayEntries = sortEntries(getEntriesForDay(state.entries, day));
                const dayButton = document.createElement("button");
                dayButton.type = "button";
                dayButton.className = "calendar-year-day";
                dayButton.dataset.calendarDayDate = formatDateKey(day);

                if (!isSameMonth(day, monthDate)) {
                    dayButton.classList.add("is-other-month");
                }
                if (isSameDay(day, new Date())) {
                    dayButton.classList.add("is-today");
                }
                if (isSameDay(day, state.selectedDate)) {
                    dayButton.classList.add("is-selected");
                }

                dayButton.addEventListener("click", () => {
                    scheduleDaySelection(state, day, {
                        updateCurrentDate: true,
                    });
                });
                dayButton.addEventListener("dblclick", (event) => {
                    event.preventDefault();
                    openDayView(state, day);
                });
                dayButton.addEventListener("contextmenu", (event) => {
                    openCalendarContextMenu(state, event, day, {
                        updateCurrentDate: true,
                        allDay: true,
                    });
                });

                const number = document.createElement("span");
                number.className = "calendar-year-day-number";
                number.textContent = `${day.getDate()}`;
                dayButton.appendChild(number);

                if (dayEntries.length) {
                    const dots = document.createElement("div");
                    dots.className = "calendar-year-day-dots";

                    dayEntries.slice(0, 3).forEach((entry) => {
                        const dot = document.createElement("span");
                        dot.className = "calendar-year-day-dot";
                        dot.style.background = entry.color;
                        dots.appendChild(dot);
                    });

                    if (dayEntries.length > 3) {
                        const more = document.createElement("span");
                        more.className = "calendar-year-day-more";
                        more.textContent = `+${dayEntries.length - 3}`;
                        dots.appendChild(more);
                    }

                    dayButton.appendChild(dots);
                }

                daysGrid.appendChild(dayButton);
            }

            monthCard.appendChild(daysGrid);
            wrapper.appendChild(monthCard);
        }

        renderTarget.appendChild(wrapper);
    }

    function updateToolbar(state) {
        const title = document.getElementById("calendar-toolbar-title");
        if (title) {
            if (state.currentView === "day") {
                title.textContent = formatDateLabel(state.currentDate);
            } else if (state.currentView === "week") {
                title.textContent = formatWeekTitle(state.currentDate);
            } else if (state.currentView === "year") {
                title.textContent = formatYearTitle(state.currentDate);
            } else {
                title.textContent = formatMonthTitle(state.currentDate);
            }
        }

        document.querySelectorAll("[data-calendar-view]").forEach((button) => {
            button.classList.toggle("is-active", button.dataset.calendarView === state.currentView);
        });
    }

    function updateUrlState(state) {
        const url = new URL(window.location.href);
        url.searchParams.set("view", state.currentView);
        url.searchParams.set("date", formatDateKey(state.currentDate));
        window.history.replaceState({}, "", url.toString());
    }

    function initCalendarAgenda() {
        const root = document.getElementById("calendar-agenda-app");
        const dataNode = document.getElementById("calendar-agenda-data");
        const categoriesNode = document.getElementById("calendar-categories-data");
        const renderTarget = document.getElementById("calendar-agenda-render");

        bindCalendarEventPopupLinks();

        if (!root || !dataNode || !categoriesNode || !renderTarget) {
            return;
        }

        const state = {
            entries: JSON.parse(dataNode.textContent || "[]").map(normalizeEntry),
            categories: JSON.parse(categoriesNode.textContent || "[]"),
            currentDate: parseISODate(root.dataset.initialDate) || new Date(),
            selectedDate: parseISODate(root.dataset.initialDate) || new Date(),
            currentView: ["day", "month", "week", "year"].includes(root.dataset.initialView) ? root.dataset.initialView : "month",
            canManage: root.dataset.canManage === "true",
            createUrl: root.dataset.createUrl,
            fullCreateUrl: root.dataset.fullCreateUrl,
            csrfToken: root.dataset.csrfToken,
            renderTarget: renderTarget,
            pendingDayClickTimer: null,
            contextMenu: null,
            contextMenuConfig: null,
            quickDialog: null,
            render: null,
        };

        function findRenderedEntry(event) {
            const entryNode = event.target.closest("[data-calendar-entry-id]");
            if (!entryNode || !renderTarget.contains(entryNode)) {
                return null;
            }

            return state.entries.find((entry) => `${entry.id}` === entryNode.dataset.calendarEntryId) || null;
        }

        renderTarget.addEventListener("click", function (event) {
            const entry = findRenderedEntry(event);
            if (!canOpenEntryInPopup(entry)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            openCalendarEntryPopup(entry);
        }, true);

        renderTarget.addEventListener("contextmenu", function (event) {
            const entry = findRenderedEntry(event);
            if (!canShowEntryContextAction(entry)) {
                return;
            }
            openCalendarContextMenu(state, event, entry.startDate || state.selectedDate, {
                allDay: entry.all_day,
                entry: entry,
                updateCurrentDate: true,
            });
        }, true);

        state.quickDialog = {
            open: function (config) {
                openEventCreatePopup(state, config || {});
            },
            close: function () {},
        };

        bindSelectedCreatePopupLinks(state);

        state.render = function render() {
            renderTarget.innerHTML = "";
            updateToolbar(state);
            updateUrlState(state);
            updateSelectedCreateLinks(state);

            if (state.currentView === "day") {
                buildDayView(state, renderTarget);
            } else if (state.currentView === "week") {
                buildWeekView(state, renderTarget);
            } else if (state.currentView === "year") {
                buildYearView(state, renderTarget);
            } else {
                buildMonthView(state, renderTarget);
            }

            updateSelectedDayPanel(state);
        };

        document.querySelectorAll("[data-calendar-nav]").forEach((button) => {
            button.addEventListener("click", () => {
                clearPendingDayClick(state);
                const action = button.dataset.calendarNav;

                if (action === "today") {
                    state.currentDate = cloneDate(new Date());
                    state.selectedDate = cloneDate(new Date());
                } else if (action === "prev") {
                    if (state.currentView === "day") {
                        state.currentDate = addDays(state.currentDate, -1);
                    } else if (state.currentView === "week") {
                        state.currentDate = addDays(state.currentDate, -7);
                    } else if (state.currentView === "year") {
                        state.currentDate = addYears(state.currentDate, -1);
                    } else {
                        state.currentDate = addMonths(state.currentDate, -1);
                    }
                    state.selectedDate = cloneDate(state.currentDate);
                } else if (action === "next") {
                    if (state.currentView === "day") {
                        state.currentDate = addDays(state.currentDate, 1);
                    } else if (state.currentView === "week") {
                        state.currentDate = addDays(state.currentDate, 7);
                    } else if (state.currentView === "year") {
                        state.currentDate = addYears(state.currentDate, 1);
                    } else {
                        state.currentDate = addMonths(state.currentDate, 1);
                    }
                    state.selectedDate = cloneDate(state.currentDate);
                }

                state.render();
            });
        });

        document.querySelectorAll("[data-calendar-view]").forEach((button) => {
            button.addEventListener("click", () => {
                clearPendingDayClick(state);
                const nextView = button.dataset.calendarView;
                if (!["day", "month", "week", "year"].includes(nextView)) {
                    return;
                }
                state.currentView = nextView;
                state.currentDate = cloneDate(state.selectedDate);
                state.render();
            });
        });

        state.render();
    }

    document.addEventListener("DOMContentLoaded", initCalendarAgenda);
})();
