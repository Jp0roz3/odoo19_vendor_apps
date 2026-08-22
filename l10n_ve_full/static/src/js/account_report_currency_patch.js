/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💵 Moneda: $ / Bs.F] en Reportes Financieros
 * ==============================================================================
 * Conecta el selector de moneda interactivo con los 5 Reportes Contables autorizados:
 *   1. Balance General (Balance Sheet)
 *   2. Estado de Resultados / Ganancias y Pérdidas (Profit and Loss)
 *   3. Estado de Flujo de Efectivo (Cash Flow)
 *   4. Resumen Ejecutivo (Executive Summary)
 *   5. Declaración Fiscal / Reporte de Impuestos (Tax Report)
 *
 * Moneda Principal por Defecto: Dólares ($ / USD)
 * Moneda Secundaria Bimoneda: Bolívares (Bs.F) a Tasa Oficial BCV
 *
// Estado global de moneda y tasa
let currentSelectedCurrency = "usd";
let currentBcvRate = 779.9522;
let isTransforming = false;
let observerDebounce = null;
let tableObserver = null;

// Limpiar cualquier clave corrupta en sessionStorage
function cleanCorruptedSessionStorage() {
    try {
        if (typeof sessionStorage === "undefined") return;
        for (let i = sessionStorage.length - 1; i >= 0; i--) {
            const k = sessionStorage.key(i);
            if (k) {
                const val = sessionStorage.getItem(k);
                if (val === "undefined" || val === "null" || val === "") {
                    sessionStorage.removeItem(k);
                }
            }
        }
    } catch (e) {}
}

// Obtener la tasa BCV activa desde el systray o estado
function extractBcvRate() {
    try {
        const systrayEl = document.querySelector(".o_bcv_rate_systray, [class*='bcv'], .o_menu_systray");
        if (systrayEl) {
            const match = (systrayEl.textContent || "").match(/BCV:\s*([\d\.,]+)/i);
            if (match && match[1]) {
                const clean = match[1].replace(/\./g, "").replace(/,/g, ".");
                const val = parseFloat(clean);
                if (!isNaN(val) && val > 0) {
                    currentBcvRate = val;
                    return val;
                }
            }
        }
    } catch (e) {}
    return currentBcvRate;
}

// Formateador estándar con símbolo de moneda ($ para USD, Bs. para Bolívares)
function formatNumberWithSymbol(value, currency) {
    if (isNaN(value)) return currency === "bs" ? "Bs. 0,00" : "$ 0,00";
    const isNeg = value < 0;
    const absVal = Math.abs(value);
    const parts = absVal.toFixed(2).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const numFormatted = `${parts[0]},${parts[1]}`;

    if (currency === "bs") {
        return isNeg ? `-Bs. ${numFormatted}` : `Bs. ${numFormatted}`;
    } else {
        return isNeg ? `-$ ${numFormatted}` : `$ ${numFormatted}`;
    }
}

// Transformar celdas de la tabla del reporte activo
function transformReportTableCells(currency) {
    if (isTransforming) return;
    isTransforming = true;

    try {
        const rate = extractBcvRate();
        
        // Seleccionar todas las celdas de tabla en el cuerpo del reporte
        const cells = document.querySelectorAll(
            ".o_account_reports_page td, .o_account_reports_body td, .o_account_report td, table.o_report_table td, .o_content table td, td.number, td.text-end, td.o_account_report_column_value, .o_account_report_cell_value"
        );

        if (!cells || cells.length === 0) {
            isTransforming = false;
            return;
        }

        cells.forEach((cell) => {
            // Ignorar la columna izquierda (nombre de cuenta / etiqueta)
            if (cell.classList.contains("o_account_report_name") || cell.classList.contains("o_account_report_line_name")) return;
            
            // Ignorar celdas que son solo iconos o botones sin dígitos
            const rawText = (cell.textContent || "").trim();
            if (!/\d/.test(rawText)) return;

            let origVal = cell.getAttribute("data-original-usd-val");

            if (origVal === null) {
                // Parsear formato: ej: "2.152,00", "$ 2.152,00", "-2.342,29"
                const cleanStr = rawText
                    .replace(/[^\d\.,\-]/g, "")
                    .replace(/\.(?=\d{3})/g, "")
                    .replace(/,/g, ".");

                const num = parseFloat(cleanStr);
                if (!isNaN(num)) {
                    origVal = String(num);
                    cell.setAttribute("data-original-usd-val", origVal);
                    cell.setAttribute("data-original-usd-html", cell.innerHTML);
                }
            }

            if (origVal !== null) {
                const baseUSD = parseFloat(origVal);
                if (!isNaN(baseUSD)) {
                    if (currency === "bs") {
                        const inBs = baseUSD * rate;
                        cell.innerText = formatNumberWithSymbol(inBs, "bs");
                        cell.style.fontWeight = "bold";
                        if (baseUSD < 0) {
                            cell.style.color = "#dc3545";
                        }
                    } else {
                        cell.innerText = formatNumberWithSymbol(baseUSD, "usd");
                        cell.style.fontWeight = "";
                        if (baseUSD < 0) {
                            cell.style.color = "#dc3545";
                        } else {
                            cell.style.color = "";
                        }
                    }
                }
            }
        });
    } catch (e) {
        console.warn("[Venezuela360] Transform cells error:", e);
    } finally {
        isTransforming = false;
    }
}

// Observador continuo para formatear nuevas filas que se expandan (Lazy Loading / Cuentas Hijas)
function setupTableObserver() {
    if (tableObserver) return;
    const table = document.querySelector(".o_account_reports_table, .o_account_report_table, .o_account_reports_body, .o_account_reports_page, .o_content");
    if (!table) return;

    tableObserver = new MutationObserver((mutations) => {
        if (isTransforming) return;
        let shouldTransform = false;
        for (const mut of mutations) {
            if (mut.addedNodes.length > 0) {
                for (const node of mut.addedNodes) {
                    if (node.nodeType === 1 && (node.tagName === "TR" || node.querySelector?.("td"))) {
                        shouldTransform = true;
                        break;
                    }
                }
            }
            if (shouldTransform) break;
        }

        if (shouldTransform && currentSelectedCurrency === "bs") {
            clearTimeout(observerDebounce);
            observerDebounce = setTimeout(() => {
                transformReportTableCells("bs");
            }, 60);
        }
    });

    tableObserver.observe(table, { childList: true, subtree: true });
}

// Parchear componentes de reportes contables para capturar la instancia activa
function ensureAccountReportPatched() {
    try {
        cleanCorruptedSessionStorage();
        const reportMod = odoo?.loader?.modules?.get("@account_reports/components/account_report/account_report");
        if (reportMod && reportMod.AccountReport && !reportMod.AccountReport._l10n_ve_patched) {
            reportMod.AccountReport._l10n_ve_patched = true;
            patch(reportMod.AccountReport.prototype, {
                setup() {
                    super.setup(...arguments);
                    cleanCorruptedSessionStorage();
                    window.__activeAccountReport = this;
                },
                async setL10nVeCurrency(currency) {
                    currentSelectedCurrency = currency;
                    transformReportTableCells(currency);
                },
            });
        }
    } catch (e) {}
}

// Inyector universal de botón bimoneda en la barra de control de reportes financieros
function injectCurrencyWidgetToDOM() {
    try {
        if (typeof document === "undefined" || !document.body) return;

        // Guard: Nunca inyectar en vistas de formulario (ej: account.journal form, res.partner form)
        if (document.querySelector(".o_form_view:not(.o_account_reports_page)")) {
            const isTrueReport = document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table");
            if (!isTrueReport) return;
        }

        const cp = document.querySelector(".o_control_panel");
        if (!cp) return;

        const cpText = (cp.textContent || "").toLowerCase();
        const docText = (document.querySelector(".o_account_reports_page, .o_account_reports_body, .o_content")?.textContent || "").toLowerCase();
        const isFinancialReport = cpText.includes("pdf") 
            || cpText.includes("xlsx")
            || cpText.includes("balance")
            || cpText.includes("resultados")
            || cpText.includes("ganancias")
            || cpText.includes("pérdidas")
            || cpText.includes("flujo")
            || cpText.includes("mayor")
            || cpText.includes("ejecutivo")
            || cpText.includes("fiscal")
            || cpText.includes("impuestos")
            || cpText.includes("asientos registrados")
            || document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table, .o_account_reports_page");

        if (!isFinancialReport) return;

        ensureAccountReportPatched();
        setupTableObserver();

        // Encontrar el contenedor exacto de las píldoras de filtro en el header
        let filterTarget = null;
        const buttonsAndPills = cp.querySelectorAll("button, .btn, .badge, .dropdown, div");
        for (const el of buttonsAndPills) {
            const txt = el.textContent || "";
            if (txt.includes("diarios") || txt.includes("Comparación") || txt.includes("Asientos") || txt.includes("Base de acumulación") || txt.includes("En .")) {
                filterTarget = el.parentElement;
                break;
            }
        }

        if (!filterTarget) {
            filterTarget = cp.querySelector(".o_control_panel_navigation")
                        || cp.querySelector(".o_account_reports_filters")
                        || cp.querySelector(".o_control_panel_actions")
                        || cp.querySelector(".d-flex.flex-wrap")
                        || cp;
        }

        if (!filterTarget) return;

        const curr = currentSelectedCurrency;

        // Si ya existe el widget, sincronizar etiquetas según currentSelectedCurrency
        let widget = cp.querySelector(".l10n_ve_currency_widget");
        if (widget) {
            const label = widget.querySelector(".l10n_ve_curr_label");
            if (label) {
                label.textContent = curr === "usd" ? "$" : "Bs.F";
                label.style.color = curr === "usd" ? "#212529" : "#dc3545";
            }
            const badge = widget.querySelector(".l10n_ve_badge");
            if (badge) badge.textContent = curr === "usd" ? "En .$" : "En .Bs.F";

            widget.querySelectorAll("[data-curr]").forEach(el => {
                const isThis = el.getAttribute("data-curr") === curr;
                const icon = el.querySelector("i");
                if (icon) icon.className = isThis ? "fa fa-check text-success me-1" : "fa fa-fw me-1";
            });
            return;
        }

        // Crear el widget con USD ($) seleccionado por defecto
        widget = document.createElement("div");
        widget.className = "l10n_ve_currency_widget d-inline-flex align-items-center ms-1 me-1";
        widget.style.cssText = "display: inline-flex !important; align-items: center; z-index: 1050; margin: 2px 4px; vertical-align: middle;";

        widget.innerHTML = `
            <div class="btn-group dropdown" style="position: relative; display: inline-flex;">
                <button class="btn btn-secondary dropdown-toggle l10n_ve_btn"
                        type="button"
                        style="display: inline-flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 500; padding: 4px 10px; border: 1px solid #ced4da; cursor: pointer; background-color: #ffffff; color: #212529; border-radius: 4px;">
                    <i class="fa fa-money me-1" style="color: #0d6efd;"></i>
                    <span>Moneda:</span>
                    <span class="ms-1 fw-bold l10n_ve_curr_label" style="color: ${curr === "usd" ? "#212529" : "#dc3545"};">${curr === "usd" ? "$" : "Bs.F"}</span>
                </button>
                <ul class="dropdown-menu dropdown-menu-end shadow l10n_ve_menu" style="min-width: 140px; position: absolute; z-index: 1090; display: none; top: 100%; right: 0; background-color: #ffffff; border: 1px solid rgba(0,0,0,0.15); border-radius: 4px; box-shadow: 0 0.5rem 1rem rgba(0,0,0,0.15);">
                    <li>
                        <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="usd" style="cursor: pointer; color: #212529;">
                            <i class="fa ${curr === "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                            <span class="fw-bold">$</span>
                        </a>
                    </li>
                    <li>
                        <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="bs" style="cursor: pointer; color: #212529;">
                            <i class="fa ${curr !== "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                            <span class="fw-bold">Bs.F</span>
                        </a>
                    </li>
                </ul>
            </div>
            <span class="badge rounded-pill align-self-center ms-1 me-1 l10n_ve_badge"
                  style="background-color: #f1f3f5; color: #495057; font-weight: 600; padding: 6px 10px; font-size: 12px; border: 1px solid #ced4da; border-radius: 50rem; display: inline-block;">
                ${curr === "usd" ? "En .$" : "En .Bs.F"}
            </span>
        `;

        const toggleBtn = widget.querySelector(".l10n_ve_btn");
        const menu = widget.querySelector(".l10n_ve_menu");

        toggleBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = menu.style.display === "block";
            document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
            menu.style.display = isOpen ? "none" : "block";
        });

        widget.querySelectorAll("[data-curr]").forEach((item) => {
            item.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                menu.style.display = "none";
                const chosen = item.getAttribute("data-curr");

                currentSelectedCurrency = chosen;
                cleanCorruptedSessionStorage();

                // Actualizar inmediatamente etiquetas visuales
                const label = widget.querySelector(".l10n_ve_curr_label");
                if (label) {
                    label.textContent = chosen === "usd" ? "$" : "Bs.F";
                    label.style.color = chosen === "usd" ? "#212529" : "#dc3545";
                }
                const badge = widget.querySelector(".l10n_ve_badge");
                if (badge) badge.textContent = chosen === "usd" ? "En .$" : "En .Bs.F";

                widget.querySelectorAll("[data-curr]").forEach(el => {
                    const isThis = el.getAttribute("data-curr") === chosen;
                    const icon = el.querySelector("i");
                    if (icon) icon.className = isThis ? "fa fa-check text-success me-1" : "fa fa-fw me-1";
                });

                // Transformar inmediatamente todos los valores en pantalla
                transformReportTableCells(chosen);
            });
        });

        filterTarget.appendChild(widget);
    } catch (err) {
        console.warn("[Venezuela360] Error in injectCurrencyWidgetToDOM:", err);
    }
}

// Cerrar menús abiertos al hacer clic fuera
if (typeof document !== "undefined") {
    document.addEventListener("click", () => {
        document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
    });
}

// Iniciar monitoreo activo para montar en SPA
setInterval(injectCurrencyWidgetToDOM, 250);
