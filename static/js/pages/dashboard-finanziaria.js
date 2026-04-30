window.ArborisDashboardFinanziaria = (function () {
    const INCOME_COLOR = "#2e9f8d";
    const EXPENSE_COLOR = "#c7465a";
    const GRID_COLOR = "#d8e1e6";
    const TEXT_COLOR = "#52636e";

    function formatCurrency(value) {
        const formatter = new Intl.NumberFormat("it-IT", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return `EUR ${formatter.format(Number(value || 0))}`;
    }

    function readChartData() {
        const script = document.getElementById("dashboard-finance-chart-data");
        if (!script) {
            return null;
        }

        try {
            return JSON.parse(script.textContent || "{}");
        } catch (error) {
            return null;
        }
    }

    function getPeriodLabel(period, data) {
        return data.periodLabel || (period === "annual" ? "anno" : "mese");
    }

    function updateButtons(root, selector, activeValue, dataAttribute) {
        root.querySelectorAll(selector).forEach((button) => {
            button.classList.toggle("is-active", button.dataset[dataAttribute] === activeValue);
        });
    }

    function updateSummary(root, period, dataSet) {
        root.querySelectorAll("[data-finance-active-period-label]").forEach((item) => {
            item.textContent = getPeriodLabel(period, dataSet);
        });

        const incomeTotal = root.querySelector("[data-finance-total-income]");
        const expenseTotal = root.querySelector("[data-finance-total-expense]");
        const balance = root.querySelector("[data-finance-period-balance]");
        const movementCount = root.querySelector("[data-finance-movement-count]");

        if (incomeTotal) {
            incomeTotal.textContent = formatCurrency(dataSet.totaleEntrate);
        }
        if (expenseTotal) {
            expenseTotal.textContent = formatCurrency(dataSet.totaleUscite);
        }
        if (balance) {
            balance.textContent = formatCurrency(dataSet.saldo);
        }
        if (movementCount) {
            const label = dataSet.movimenti === 1 ? "movimento" : "movimenti";
            movementCount.textContent = `${dataSet.movimenti} ${label}`;
        }
    }

    function drawRoundedBar(ctx, x, y, width, height, color) {
        const radius = Math.min(4, width / 2, height / 2);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height);
        ctx.lineTo(x, y + height);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
        ctx.fill();
    }

    function drawEmptyState(ctx, width, height) {
        ctx.fillStyle = TEXT_COLOR;
        ctx.font = "14px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Nessun movimento nel periodo selezionato.", width / 2, height / 2);
    }

    function drawChart(root, chartData, state) {
        const canvas = root.querySelector("[data-finance-chart]");
        if (!canvas) {
            return;
        }

        const dataSet = chartData[state.period] || chartData.monthly;
        const labels = dataSet.labels || [];
        const incomeValues = dataSet.entrate || [];
        const expenseValues = dataSet.uscite || [];
        const visibleIncome = state.kind === "all" || state.kind === "income";
        const visibleExpense = state.kind === "all" || state.kind === "expense";

        const rect = canvas.getBoundingClientRect();
        const width = Math.max(Math.floor(rect.width), 320);
        const height = Math.max(Math.floor(rect.height), 260);
        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;

        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const padding = {
            top: 24,
            right: 18,
            bottom: 38,
            left: 76,
        };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const baseline = padding.top + chartHeight;
        const valuesForMax = [];
        if (visibleIncome) {
            valuesForMax.push(...incomeValues);
        }
        if (visibleExpense) {
            valuesForMax.push(...expenseValues);
        }
        const maxValue = Math.max(...valuesForMax, 0);
        const paddedMax = maxValue > 0 ? maxValue * 1.12 : 0;

        ctx.strokeStyle = GRID_COLOR;
        ctx.lineWidth = 1;
        ctx.fillStyle = TEXT_COLOR;
        ctx.font = "12px sans-serif";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";

        for (let i = 0; i <= 4; i += 1) {
            const y = padding.top + (chartHeight / 4) * i;
            const value = paddedMax - (paddedMax / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();
            ctx.fillText(formatCurrency(value).replace("EUR ", ""), padding.left - 12, y);
        }

        if (!labels.length || maxValue <= 0) {
            drawEmptyState(ctx, width, height);
            updateSummary(root, state.period, dataSet);
            return;
        }

        const slotWidth = chartWidth / labels.length;
        const barCount = visibleIncome && visibleExpense ? 2 : 1;
        const barWidth = Math.max(4, Math.min(18, slotWidth * (barCount === 2 ? 0.28 : 0.46)));
        const groupWidth = barWidth * barCount + (barCount - 1) * 4;
        const labelStep = labels.length > 14 ? Math.ceil(labels.length / 12) : 1;

        labels.forEach((label, index) => {
            const groupLeft = padding.left + (slotWidth * index) + (slotWidth - groupWidth) / 2;
            let barIndex = 0;

            if (visibleIncome) {
                const value = incomeValues[index] || 0;
                const barHeight = value > 0 ? (value / paddedMax) * chartHeight : 0;
                drawRoundedBar(ctx, groupLeft + barIndex * (barWidth + 4), baseline - barHeight, barWidth, barHeight, INCOME_COLOR);
                barIndex += 1;
            }

            if (visibleExpense) {
                const value = expenseValues[index] || 0;
                const barHeight = value > 0 ? (value / paddedMax) * chartHeight : 0;
                drawRoundedBar(ctx, groupLeft + barIndex * (barWidth + 4), baseline - barHeight, barWidth, barHeight, EXPENSE_COLOR);
            }

            if (index % labelStep === 0 || index === labels.length - 1) {
                ctx.fillStyle = TEXT_COLOR;
                ctx.font = "12px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                ctx.fillText(label, padding.left + slotWidth * index + slotWidth / 2, baseline + 12);
            }
        });

        updateSummary(root, state.period, dataSet);
    }

    function bindDashboard(root, chartData) {
        if (root.dataset.financeDashboardBound === "1") {
            return;
        }
        root.dataset.financeDashboardBound = "1";

        const state = {
            period: "monthly",
            kind: "all",
        };

        function render() {
            updateButtons(root, "[data-finance-period]", state.period, "financePeriod");
            updateButtons(root, "[data-finance-kind]", state.kind, "financeKind");
            drawChart(root, chartData, state);
        }

        root.querySelectorAll("[data-finance-period]").forEach((button) => {
            button.addEventListener("click", function () {
                state.period = button.dataset.financePeriod || "monthly";
                render();
            });
        });

        root.querySelectorAll("[data-finance-kind]").forEach((button) => {
            button.addEventListener("click", function () {
                state.kind = button.dataset.financeKind || "all";
                render();
            });
        });

        let resizeTimer = null;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(render, 120);
        });

        render();
    }

    function init(container = document) {
        const chartData = readChartData();
        if (!chartData) {
            return;
        }

        container.querySelectorAll(".js-financial-dashboard").forEach((root) => {
            bindDashboard(root, chartData);
        });
    }

    return {
        init,
    };
})();
