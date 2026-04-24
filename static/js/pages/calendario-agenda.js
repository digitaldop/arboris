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

    function createEntryLink(entry, className, label, meta, isBlock) {
        const hasLink = Boolean(entry.url);
        const element = document.createElement(hasLink ? "a" : "div");
        element.className = className;
        applyEntryPalette(element, entry.color);

        if (hasLink) {
            element.href = entry.url;
            if (entry.external) {
                element.target = "_blank";
                element.rel = "noopener noreferrer";
            }
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

    function openDayView(state, day) {
        state.selectedDate = cloneDate(day);
        state.currentDate = cloneDate(day);
        state.currentView = "day";
        state.render();
    }

    function getQuickCreateDialog(root, state) {
        let overlay = document.getElementById("calendar-quick-create-overlay");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "calendar-quick-create-overlay";
            overlay.className = "app-dialog-overlay is-hidden";
            overlay.innerHTML = `
                <div class="app-dialog calendar-quick-dialog" role="dialog" aria-modal="true" aria-labelledby="calendar-quick-dialog-title">
                    <div class="app-dialog-header">
                        <h2 class="app-dialog-title" id="calendar-quick-dialog-title">Nuovo evento</h2>
                    </div>
                    <div class="app-dialog-body calendar-quick-dialog-body">
                        <div class="calendar-quick-dialog-errors is-hidden" data-calendar-quick-errors="1"></div>
                        <div class="calendar-quick-grid">
                            <label class="calendar-quick-field">
                                <span>Titolo</span>
                                <input type="text" class="app-dialog-input" data-calendar-quick-field="titolo" maxlength="200">
                            </label>
                            <label class="calendar-quick-field">
                                <span>Categoria</span>
                                <select class="app-dialog-input" data-calendar-quick-field="categoria_evento"></select>
                            </label>
                            <label class="calendar-quick-field calendar-quick-field-checkbox">
                                <input type="checkbox" data-calendar-quick-field="intera_giornata">
                                <span>Intera giornata</span>
                            </label>
                            <label class="calendar-quick-field">
                                <span>Data inizio</span>
                                <input type="date" class="app-dialog-input" data-calendar-quick-field="data_inizio">
                            </label>
                            <label class="calendar-quick-field calendar-quick-all-day-row">
                                <span>Data fine</span>
                                <input type="date" class="app-dialog-input" data-calendar-quick-field="data_fine">
                            </label>
                            <label class="calendar-quick-field calendar-quick-time-row">
                                <span>Ora inizio</span>
                                <input type="time" class="app-dialog-input" data-calendar-quick-field="ora_inizio">
                            </label>
                            <label class="calendar-quick-field calendar-quick-time-row">
                                <span>Durata (minuti)</span>
                                <input type="number" class="app-dialog-input" data-calendar-quick-field="durata_minuti" min="15" max="1440" step="15">
                            </label>
                            <label class="calendar-quick-field calendar-quick-field-wide">
                                <span>Luogo</span>
                                <input type="text" class="app-dialog-input" data-calendar-quick-field="luogo" maxlength="200">
                            </label>
                            <label class="calendar-quick-field calendar-quick-field-wide">
                                <span>Descrizione</span>
                                <textarea class="app-dialog-input calendar-quick-textarea" data-calendar-quick-field="descrizione" rows="4"></textarea>
                            </label>
                        </div>
                    </div>
                    <div class="app-dialog-actions calendar-quick-actions">
                        <a href="#" class="btn btn-secondary" data-calendar-quick-full="1">Apri scheda completa</a>
                        <div class="calendar-quick-actions-right">
                            <button type="button" class="btn btn-secondary" data-calendar-quick-cancel="1">Annulla</button>
                            <button type="button" class="btn btn-primary" data-calendar-quick-save="1">Crea evento</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        const fields = {
            title: overlay.querySelector('[data-calendar-quick-field="titolo"]'),
            category: overlay.querySelector('[data-calendar-quick-field="categoria_evento"]'),
            allDay: overlay.querySelector('[data-calendar-quick-field="intera_giornata"]'),
            date: overlay.querySelector('[data-calendar-quick-field="data_inizio"]'),
            endDate: overlay.querySelector('[data-calendar-quick-field="data_fine"]'),
            time: overlay.querySelector('[data-calendar-quick-field="ora_inizio"]'),
            duration: overlay.querySelector('[data-calendar-quick-field="durata_minuti"]'),
            location: overlay.querySelector('[data-calendar-quick-field="luogo"]'),
            description: overlay.querySelector('[data-calendar-quick-field="descrizione"]'),
        };
        const errorsBox = overlay.querySelector('[data-calendar-quick-errors="1"]');
        const cancelButton = overlay.querySelector('[data-calendar-quick-cancel="1"]');
        const saveButton = overlay.querySelector('[data-calendar-quick-save="1"]');
        const fullButton = overlay.querySelector('[data-calendar-quick-full="1"]');
        const timeRows = overlay.querySelectorAll(".calendar-quick-time-row");
        const allDayRows = overlay.querySelectorAll(".calendar-quick-all-day-row");

        function syncFieldRows() {
            timeRows.forEach((row) => {
                row.style.display = fields.allDay.checked ? "none" : "";
            });
            allDayRows.forEach((row) => {
                row.style.display = fields.allDay.checked ? "" : "none";
            });
        }

        function hideErrors() {
            errorsBox.classList.add("is-hidden");
            errorsBox.innerHTML = "";
        }

        function showErrors(messages) {
            errorsBox.innerHTML = "";
            const list = document.createElement("ul");
            messages.forEach((message) => {
                const item = document.createElement("li");
                item.textContent = message;
                list.appendChild(item);
            });
            errorsBox.appendChild(list);
            errorsBox.classList.remove("is-hidden");
        }

        function syncFullLink() {
            fullButton.href = buildQuickCreateUrl(state.fullCreateUrl, {
                date: fields.date.value,
                endDate: fields.endDate.value,
                time: fields.time.value,
                duration: fields.duration.value,
                allDay: fields.allDay.checked,
                categoryId: fields.category.value,
            });
        }

        async function saveEntry() {
            hideErrors();
            saveButton.disabled = true;

            const formData = new FormData();
            formData.append("titolo", fields.title.value.trim());
            formData.append("categoria_evento", fields.category.value);
            formData.append("intera_giornata", fields.allDay.checked ? "on" : "");
            formData.append("data_inizio", fields.date.value);
            formData.append("data_fine", fields.endDate.value || fields.date.value);
            formData.append("ora_inizio", fields.time.value);
            formData.append("durata_minuti", fields.duration.value || "60");
            formData.append("luogo", fields.location.value.trim());
            formData.append("descrizione", fields.description.value.trim());
            formData.append("visibile", "on");

            try {
                const response = await fetch(state.createUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": state.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: formData,
                });
                const payload = await response.json();

                if (!response.ok || !payload.success) {
                    showErrors(payload.error_messages || ["Impossibile creare l'evento."]);
                    return;
                }

                state.entries.push(normalizeEntry(payload.entry));
                state.selectedDate = parseISODate(payload.entry.start_date) || state.selectedDate;
                state.currentDate = cloneDate(state.selectedDate);
                closeDialog();
                state.render();
            } catch (error) {
                showErrors(["Si e verificato un errore durante il salvataggio rapido dell'evento."]);
            } finally {
                saveButton.disabled = false;
            }
        }

        function openDialog(config) {
            hideErrors();

            fields.category.innerHTML = "";
            state.categories.forEach((category) => {
                const option = document.createElement("option");
                option.value = `${category.id}`;
                option.textContent = category.name;
                fields.category.appendChild(option);
            });

            fields.title.value = "";
            fields.category.value = config.categoryId || (state.categories[0] ? `${state.categories[0].id}` : "");
            fields.allDay.checked = Boolean(config.allDay);
            fields.date.value = config.date || formatDateKey(state.selectedDate);
            fields.endDate.value = config.endDate || fields.date.value;
            fields.time.value = config.time || "09:00";
            fields.duration.value = `${config.duration || 60}`;
            fields.location.value = "";
            fields.description.value = "";
            syncFieldRows();
            syncFullLink();

            saveButton.disabled = !state.categories.length;
            overlay.classList.remove("is-hidden");
            document.body.classList.add("app-dialog-open");
            window.setTimeout(() => fields.title.focus(), 0);
        }

        function closeDialog() {
            overlay.classList.add("is-hidden");
            document.body.classList.remove("app-dialog-open");
        }

        if (!overlay.dataset.calendarQuickBound) {
            overlay.dataset.calendarQuickBound = "1";
            cancelButton.addEventListener("click", closeDialog);
            saveButton.addEventListener("click", saveEntry);
            overlay.addEventListener("click", function (event) {
                if (event.target === overlay) {
                    closeDialog();
                }
            });
            document.addEventListener("keydown", function (event) {
                if (event.key === "Escape" && !overlay.classList.contains("is-hidden")) {
                    closeDialog();
                }
            });

            fields.allDay.addEventListener("change", function () {
                if (!fields.endDate.value) {
                    fields.endDate.value = fields.date.value;
                }
                syncFieldRows();
                syncFullLink();
            });
            fields.date.addEventListener("input", syncFullLink);
            fields.date.addEventListener("change", function () {
                if (fields.allDay.checked && (!fields.endDate.value || fields.endDate.value < fields.date.value)) {
                    fields.endDate.value = fields.date.value;
                }
                syncFullLink();
            });
            fields.endDate.addEventListener("input", syncFullLink);
            fields.time.addEventListener("input", syncFullLink);
            fields.duration.addEventListener("input", syncFullLink);
            fields.category.addEventListener("change", syncFullLink);
        }

        return {
            open: openDialog,
            close: closeDialog,
        };
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
                titleNode.href = entry.url;
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
                state.selectedDate = cloneDate(day);
                if (!isSameMonth(day, monthStart)) {
                    state.currentDate = cloneDate(day);
                }
                state.render();
            });

            cell.addEventListener("dblclick", function (event) {
                if (event.target.closest("a, button")) {
                    return;
                }
                openDayView(state, day);
            });

            const dayButton = document.createElement("button");
            dayButton.type = "button";
            dayButton.className = "calendar-day-button";
            dayButton.textContent = `${day.getDate()}`;
            dayButton.addEventListener("click", (event) => {
                event.stopPropagation();
                state.selectedDate = cloneDate(day);
                state.currentDate = cloneDate(day);
                state.render();
            });
            dayButton.addEventListener("dblclick", (event) => {
                event.preventDefault();
                event.stopPropagation();
                openDayView(state, day);
            });
            cell.appendChild(dayButton);

            const eventsBox = document.createElement("div");
            eventsBox.className = "calendar-month-events";

            dayEntries.slice(0, MAX_MONTH_EVENTS_PER_DAY).forEach((entry) => {
                const label = entry.all_day ? entry.title : `${entry.start_time || ""} ${entry.title}`.trim();
                eventsBox.appendChild(createEntryLink(entry, "calendar-entry-chip", label, "", false));
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

            cell.addEventListener("click", function (event) {
                if (event.target.closest("a")) {
                    return;
                }
                state.selectedDate = cloneDate(day);
                if (state.canManage && state.categories.length) {
                    state.quickDialog.open({
                        date: formatDateKey(day),
                        allDay: true,
                    });
                }
                state.render();
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
                    cell.appendChild(createEntryLink(entry, "calendar-entry-chip", entry.title, "", false));
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
            if (isSameDay(day, state.selectedDate)) {
                column.classList.add("is-selected");
            }

            hours.forEach((hour) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "calendar-week-hour-row";
                row.addEventListener("click", function () {
                    state.selectedDate = cloneDate(day);
                    if (state.canManage && state.categories.length) {
                        state.quickDialog.open({
                            date: formatDateKey(day),
                            allDay: false,
                            time: `${`${hour}`.padStart(2, "0")}:00`,
                            duration: 60,
                        });
                    }
                    state.render();
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
                    true
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
        allDayCell.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                return;
            }
            state.selectedDate = cloneDate(day);
            if (state.canManage && state.categories.length) {
                state.quickDialog.open({
                    date: formatDateKey(day),
                    allDay: true,
                });
            }
            state.render();
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
                allDayCell.appendChild(createEntryLink(entry, "calendar-entry-chip", entry.title, "", false));
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
            row.addEventListener("click", function () {
                state.selectedDate = cloneDate(day);
                if (state.canManage && state.categories.length) {
                    state.quickDialog.open({
                        date: formatDateKey(day),
                        allDay: false,
                        time: `${`${hour}`.padStart(2, "0")}:00`,
                        duration: 60,
                    });
                }
                state.render();
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
                true
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
                    state.selectedDate = cloneDate(day);
                    state.currentDate = cloneDate(day);
                    state.render();
                });
                dayButton.addEventListener("dblclick", (event) => {
                    event.preventDefault();
                    openDayView(state, day);
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
            quickDialog: null,
            render: null,
        };

        state.quickDialog = getQuickCreateDialog(root, state);

        state.render = function render() {
            renderTarget.innerHTML = "";
            updateToolbar(state);
            updateUrlState(state);

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
