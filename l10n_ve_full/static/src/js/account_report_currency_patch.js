/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💱 Moneda: $ / Bs.F] en Reportes Financieros
 * ==============================================================================
 * Conecta el selector de moneda interactivo con el controlador AccountReport
 * de Odoo Enterprise, permitiendo alternar al instante entre USD y Bs.F.
 *
 * Soporte Integral para TODOS los Reportes Contables y Financieros de Odoo 19:
 *   - Balance General (Balance Sheet)
 *   - Estado de Resultados / Ganancias y Pérdidas (Profit and Loss)
 *   - Estado de Flujo de Efectivo (Cash Flow)
 *   - Libro Mayor (General Ledger)
 *   - Balance de Comprobación (Trial Balance)
 *   - Libro Diario (Journal Report)
 *   - Libro Mayor de Socios (Partner Ledger)
 *   - Resumen Ejecutivo (Executive Summary)
 *   - Antigüedad de Saldos por Cobrar / Pagar (Aged Receivables / Payables)
 *
 * Moneda Principal por Defecto: Dólares ($ / USD)
 * Moneda Secundaria Bimoneda: Bolívares (Bs.F) a Tasa Oficial BCV
 *
 * Autor: JeanPerozo / Nubelco
 */

import { patch } from "@web/core/utils/patch";

// Moneda inicial por defecto: USD ($)
let currentSelectedCurrency = "usd";
let currentBcvRate = 779.9522;
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

// Parsear número con formato contable/venezolano a float
function parseVeNumber(str) {
    if (!str) return null;
    let clean = str.replace(/Bs\.F|\$|EUR|\s/g, "").trim();
    if (!clean) return null;
    const isNeg = clean.startsWith("-") || clean.startsWith("(");
    clean = clean.replace(/[\(\)-]/g, "").trim();
    clean = clean.replace(/\./g, "").replace(/,/g, ".");
    const val = parseFloat(clean);
    if (isNaN(val)) return null;
    return isNeg ? -val : val;
}

// Formatear número con estándar venezolano: 2339.86 -> "2.339,86"
function formatVeNumber(num) {
    if (num === null || isNaN(num)) return "0,00";
    const isNeg = num < 0;
    const absNum = Math.abs(num);
    const parts = absNum.toFixed(2).split(".");
    const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const decPart = parts[1];
    const res = `${intPart},${decPart}`;
    return isNeg ? `-${res}` : res;
}

// Transformación directa e instantánea de todas las celdas numéricas de la tabla
function transformReportTableCells(currency) {
    try {
        const rate = extractBcvRate();
        const tables = document.querySelectorAll(
            ".o_account_reports_table, .o_account_reports_body table, .o_account_report table, .o_account_reports_page table, table"
        );
        
        tables.forEach(table => {
            const cells = table.querySelectorAll(
                "td, th, span.o_account_report_column_value, div.o_account_report_column_value"
            );
            cells.forEach(cell => {
                // Evitar celdas que son títulos de cuentas o encabezados con texto puro
                if (cell.children.length > 2) return;
                const txt = cell.textContent.trim();
                if (!txt) return;

                // Capturar el valor base en USD en el primer parseo
                if (!cell.hasAttribute("data-original-usd")) {
                    const parsed = parseVeNumber(txt);
                    if (parsed !== null && (txt.match(/^-?[\d\.,]+$/) || txt.includes("$") || txt.includes("Bs.F"))) {
                        cell.setAttribute("data-original-usd", parsed.toString());
                    }
                }

                if (cell.hasAttribute("data-original-usd")) {
                    const usdVal = parseFloat(cell.getAttribute("data-original-usd"));
                    if (!isNaN(usdVal)) {
                        if (currency === "bs") {
                            const bsVal = Math.round(usdVal * rate * 100) / 100;
                            cell.textContent = `${formatVeNumber(bsVal)} Bs.F`;
                        } else {
                            cell.textContent = `${formatVeNumber(usdVal)} $`;
                        }
                    }
                }
            });
        });

        // Observar dinámicamente cuando el usuario despliega o expande cuentas hijas (unfold)
        const reportBody = document.querySelector(".o_account_reports_body, .o_account_report, .o_content");
        if (reportBody && !tableObserver) {
            tableObserver = new MutationObserver(() => {
                if (currentSelectedCurrency === "bs") {
                    transformReportTableCells("bs");
                }
            });
            tableObserver.observe(reportBody, { childList: true, subtree: true });
        }
    } catch (e) {
        console.warn("[Venezuela360] transformReportTableCells error:", e);
    }
}

// Ejecutar recarga del reporte de forma segura y sincronizada
async function triggerReportReload(reportComp, currency) {
    currentSelectedCurrency = currency;
    cleanCorruptedSessionStorage();
    transformReportTableCells(currency);

    if (!reportComp) return;

    const options = reportComp.options || (reportComp.controller && reportComp.controller.options) || {};
    options.l10n_ve_currency = currency;
    options.l10n_ve_currency_label = currency === "usd" ? "$" : "Bs.F";
    options.l10n_ve_badge_label = currency === "usd" ? "En .$" : "En .Bs.F";

    reportComp.options = options;
    if (reportComp.controller) reportComp.controller.options = options;
    if (reportComp.report) reportComp.report.options = options;

    const reportId = reportComp.props?.reportId 
        || reportComp.props?.action?.context?.report_id 
        || options.report_id 
        || reportComp.reportId;

    if (reportComp.env?.services?.orm && reportId) {
        try {
            const info = await reportComp.env.services.orm.call(
                "account.report",
                "get_report_information",
                [reportId, options]
            );
            if (info && info.lines) {
                if (reportComp.controller) {
                    reportComp.controller.lines = info.lines;
                    reportComp.controller.options = info.options || options;
                }
                reportComp.lines = info.lines;
                reportComp.options = info.options || options;

                if (typeof reportComp.render === "function") {
                    reportComp.render(true);
                    setTimeout(() => transformReportTableCells(currency), 50);
                }
            }
        } catch (eA) {
            console.warn("[Venezuela360] ORM direct reload fallback:", eA);
        }
    }
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
                    await triggerReportReload(this, currency);
                },
            });
        }
    } catch (e) {}
}

// Inyector universal de botón bimoneda en la barra de control de TODOS los reportes financieros
function injectCurrencyWidgetToDOM() {
    try {
        if (typeof document === "undefined" || !document.body) return;

        ensureAccountReportPatched();

        const cp = document.querySelector(".o_control_panel");
        if (!cp) return;

        const cpText = cp.textContent || "";
        const isFinancialReport = cpText.includes("PDF") 
            || cpText.includes("XLSX")
            || cpText.includes("Balance")
            || cpText.includes("Resultados")
            || cpText.includes("flujo")
            || cpText.includes("Mayor")
            || cpText.includes("Diario")
            || cpText.includes("Socios")
            || cpText.includes("Ejecutivo")
            || cpText.includes("Antigüedad")
            || document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table, .o_account_reports_page");

        if (!isFinancialReport) return;

        // Encontrar el contenedor exacto de las píldoras de filtro en el header
        let filterTarget = null;
        const buttonsAndPills = cp.querySelectorAll("button, .btn, .badge, .dropdown, div");
        for (const el of buttonsAndPills) {
            const txt = el.textContent || "";
            if (txt.includes("diarios") || txt.includes("Comparación") || txt.includes("Asientos") || txt.includes("En .")) {
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
            item.addEventListener("click", async (e) => {
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

                // Obtener la instancia activa del reporte y sincronizar con el backend
                let activeReport = window.__activeAccountReport;
                if (!activeReport) {
                    const reportNodes = document.querySelectorAll(".o_account_reports_body, .o_account_report, .o_content, .o_action_manager");
                    for (const node of reportNodes) {
                        if (node.__owl__ && node.__owl__.component) {
                            activeReport = node.__owl__.component;
                            break;
                        }
                    }
                }

                if (activeReport) {
                    await triggerReportReload(activeReport, chosen);
                }
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
