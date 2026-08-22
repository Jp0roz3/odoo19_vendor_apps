/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💵 Moneda: Bs.F / $] en Reportes Financieros
 * ==============================================================================
 * Conecta el selector de moneda interactivo con los 5 Reportes Contables autorizados:
 *   1. Balance General (Balance Sheet)
 *   2. Estado de Resultados / Ganancias y Pérdidas (Profit and Loss)
 *   3. Estado de Flujo de Efectivo (Cash Flow)
 *   4. Resumen Ejecutivo (Executive Summary)
 *   5. Declaración Fiscal / Reporte de Impuestos (Tax Report)
 *
 * Moneda Principal: Dólares ($ / USD)
 * Moneda Secundaria: Bolívares (Bs.F) a Tasa Oficial BCV
 *
 * Autor: JeanPerozo / Nubelco
 */

import { patch } from "@web/core/utils/patch";

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

// Formateador estándar de moneda venezolana e internacional
function formatNumberVE(value) {
    if (isNaN(value)) return "0,00";
    const parts = Math.abs(value).toFixed(2).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const formatted = parts.join(",");
    return value < 0 ? `-${formatted}` : formatted;
}

// Transformar celdas de la tabla del reporte activo
function transformReportTableCells(currency) {
    if (isTransforming) return;
    isTransforming = true;

    try {
        const rate = extractBcvRate();
        const table = document.querySelector(".o_account_reports_table, .o_account_report_table, table.o_report_table");
        if (!table) {
            isTransforming = false;
            return;
        }

        const cells = table.querySelectorAll("td.number, td.o_account_report_cell, td.o_account_reports_domain_cell, span.o_account_report_column_value, .o_account_report_cell_value");

        cells.forEach((cell) => {
            if (cell.classList.contains("o_account_report_name")) return;

            let origVal = cell.getAttribute("data-original-usd-val");
            const text = (cell.textContent || "").trim();

            if (origVal === null) {
                const cleanStr = text.replace(/[\$\s]/g, "").replace(/\./g, "").replace(/,/g, ".");
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
                        cell.innerText = formatNumberVE(inBs);
                        cell.style.fontWeight = "bold";
                    } else {
                        const origHTML = cell.getAttribute("data-original-usd-html");
                        if (origHTML) {
                            cell.innerHTML = origHTML;
                        } else {
                            cell.innerText = formatNumberVE(baseUSD);
                        }
                        cell.style.fontWeight = "";
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

// Validar si estamos exactamente en uno de los 5 reportes autorizados
function isAllowedFinancialReport() {
    // Si estamos en un formulario estándar (ej: account.journal form, res.partner form) -> NO inyectar
    if (document.querySelector(".o_form_view:not(.o_account_reports_page)")) {
        const isTrueReport = document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table");
        if (!isTrueReport) return false;
    }

    const cp = document.querySelector(".o_control_panel");
    if (!cp) return false;

    const cpText = (cp.textContent || "").toLowerCase();
    const docText = (document.querySelector(".o_account_reports_page, .o_account_reports_body, .o_content")?.textContent || "").toLowerCase();
    const combined = cpText + " " + docText;

    const allowed = [
        "balance general",
        "balance sheet",
        "estado de resultado",
        "ganancias y pérdidas",
        "pérdidas y ganancias",
        "profit and loss",
        "flujo de efectivo",
        "cash flow",
        "resumen ejecutivo",
        "executive summary",
        "declaración fiscal",
        "reporte de impuestos",
        "tax report"
    ];

    const hasAllowedKeyword = allowed.some(keyword => combined.includes(keyword));
    const hasReportDOM = document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table, .o_account_reports_page, .o_account_report_page") !== null;

    return hasAllowedKeyword && hasReportDOM;
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

// Inyector de botón bimoneda en la barra de control de los 5 reportes autorizados
function injectCurrencyWidgetToDOM() {
    try {
        if (typeof document === "undefined" || !document.body) return;

        // Validar que estemos en uno de los 5 reportes autorizados
        if (!isAllowedFinancialReport()) {
            // Si salimos del reporte, remover cualquier widget residual
            const existingWidget = document.querySelector(".l10n_ve_currency_widget");
            if (existingWidget && !document.querySelector(".o_account_reports_body, .o_account_reports_table")) {
                existingWidget.remove();
            }
            return;
        }

        ensureAccountReportPatched();

        const cp = document.querySelector(".o_control_panel");
        if (!cp) return;

        // Encontrar el contenedor de filtros en el header
        let filterTarget = null;
        const buttonsAndPills = cp.querySelectorAll("button, .btn, .badge, .dropdown, div");
        for (const el of buttonsAndPills) {
            const txt = el.textContent || "";
            if (txt.includes("diarios") || txt.includes("Comparación") || txt.includes("Asientos") || txt.includes("Base de acumulación")) {
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
                label.style.color = curr === "usd" ? "#2563eb" : "#dc3545";
            }
            const badge = widget.querySelector(".l10n_ve_badge");
            if (badge) badge.textContent = curr === "usd" ? "En .$" : "En .Bs.F";

            const checkBs = widget.querySelector(".l10n_ve_check_bs");
            const checkUsd = widget.querySelector(".l10n_ve_check_usd");
            if (checkBs) checkBs.textContent = curr !== "usd" ? "✓" : "";
            if (checkUsd) checkUsd.textContent = curr === "usd" ? "✓" : "";
            return;
        }

        // Crear el widget idéntico a la Imagen 2 de Referencia
        widget = document.createElement("div");
        widget.className = "btn-group dropdown l10n_ve_currency_widget d-inline-flex align-items-center ms-1 me-1";
        widget.style.cssText = "display: inline-flex !important; align-items: center; z-index: 1050; margin: 0 4px; vertical-align: middle;";

        widget.innerHTML = `
            <button class="btn btn-secondary dropdown-toggle l10n_ve_btn"
                    type="button"
                    style="display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 5px 12px; border: 1px solid #008784; background-color: #e6f4f1; color: #1f2937; border-radius: 4px; cursor: pointer;">
                <span style="font-size: 14px;">💵</span>
                <span>Moneda:</span>
                <span class="l10n_ve_curr_label" style="color: ${curr === "usd" ? "#2563eb" : "#dc3545"}; font-weight: 800;">${curr === "usd" ? "$" : "Bs.F"}</span>
            </button>
            <ul class="dropdown-menu dropdown-menu-end shadow l10n_ve_menu" style="min-width: 140px; position: absolute; z-index: 1090; display: none; top: 100%; left: 0; background-color: #ffffff; border: 1px solid rgba(0,0,0,0.15); border-radius: 6px; padding: 6px 0; box-shadow: 0 10px 25px rgba(0,0,0,0.2);">
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="bs" style="cursor: pointer; color: #1f2937; font-weight: 600; padding: 8px 16px;">
                        <span class="l10n_ve_check_bs" style="color: #059669; font-weight: bold; width: 16px;">${curr !== "usd" ? "✓" : ""}</span>
                        <span>Bs.F</span>
                    </a>
                </li>
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="usd" style="cursor: pointer; color: #1f2937; font-weight: 600; padding: 8px 16px;">
                        <span class="l10n_ve_check_usd" style="color: #059669; font-weight: bold; width: 16px;">${curr === "usd" ? "✓" : ""}</span>
                        <span>$</span>
                    </a>
                </li>
            </ul>
            <span class="badge rounded-pill align-self-center ms-1 l10n_ve_badge"
                  style="background-color: #f1f5f9; color: #334155; font-weight: 700; padding: 6px 12px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 50rem; display: inline-block;">
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
                    label.style.color = chosen === "usd" ? "#2563eb" : "#dc3545";
                }
                const badge = widget.querySelector(".l10n_ve_badge");
                if (badge) badge.textContent = chosen === "usd" ? "En .$" : "En .Bs.F";

                const checkBs = widget.querySelector(".l10n_ve_check_bs");
                const checkUsd = widget.querySelector(".l10n_ve_check_usd");
                if (checkBs) checkBs.textContent = chosen !== "usd" ? "✓" : "";
                if (checkUsd) checkUsd.textContent = chosen === "usd" ? "✓" : "";

                // Transformar inmediatamente todos los valores de las celdas en pantalla
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
