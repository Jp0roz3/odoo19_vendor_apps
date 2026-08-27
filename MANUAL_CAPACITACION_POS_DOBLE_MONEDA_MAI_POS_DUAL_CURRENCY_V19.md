# 🛒 MANUAL MAESTRO DE CAPACITACIÓN: PUNTO DE VENTA DOBLE MONEDA ODOO 19 (`mai_pos_dual_currency_v19`)
**Versión del Sistema:** Odoo Enterprise 19.0 / Community 19.0  
**Módulo:** `mai_pos_dual_currency_v19` (VenPOS 360 Doble Moneda)  
**Marco Operativo:** Punto de Venta Dinámico Multimoneda (USD / Bs.F), IGTF 3% en Pagos en Divisas, Tasa BCV en Tiempo Real, Arqueo Dual y Cierre Z Fiscal.

---

## 📑 ÍNDICE DE CONTENIDOS

1. [Visión General del Punto de Venta Doble Moneda](#1-visión-general-del-punto-de-venta-doble-moneda)
2. [Configuración General del Punto de Venta](#2-configuración-general-del-punto-de-venta)
3. [Configuración de Métodos de Pago (Bs, Divisas e IGTF)](#3-configuración-de-métodos-de-pago-bs-divisas-e-igtf)
4. [Configuración del Producto de Impuesto IGTF 3%](#4-configuración-del-producto-de-impuesto-igtf-3)
5. [Apertura de Turno y Control de Efectivo Dual (USD / Bs.)](#5-apertura-de-turno-y-control-de-efectivo-dual-usd--bs)
6. [Interfaz de Ventas: Catálogo y Precios Duales en Vivo](#6-interfaz-de-ventas-catálogo-y-precios-duales-en-vivo)
7. [Carrito de Compras y Desglose de Totales Bimoneda](#7-carrito-de-compras-y-desglose-de-totales-bimoneda)
8. [Procesamiento de Pagos Mixtos y Cobro en Múltiples Monedas](#8-procesamiento-de-pagos-mixtos-y-cobro-en-múltiples-monedas)
9. [Cálculo Automático y Ajuste Manual de Base Imponible IGTF](#9-cálculo-automático-y-ajuste-manual-de-base-imponible-igtf)
10. [Emisión de Recibo de Venta (Ticket Dual Legal SENIAT)](#10-emisión-de-recibo-de-venta-ticket-dual-legal-seniat)
11. [Cierre de Turno, Reporte X y Reporte Z Bimoneda](#11-cierre-de-turno-reporte-x-y-reporte-z-bimoneda)
12. [Sincronización de Stock y Modo Offline](#12-sincronización-de-stock-y-modo-offline)
13. [Matriz de Solución de Problemas Operativos (Troubleshooting)](#13-matriz-de-solución-de-problemas-operativos-troubleshooting)

---

## 1. Visión General del Punto de Venta Doble Moneda

El módulo `mai_pos_dual_currency_v19` dota al Punto de Venta de Odoo 19 de la capacidad de operar en un entorno bimoneda fluido.

### Características Principales:
* **Fórmula de Precios en Vivo:** Las tarjetas del catálogo muestran simultáneamente el precio en Bolívares (`Bs.F`) y en Dólares (`$ USD`), sincronizados al milímetro con el inventario y la tasa BCV oficial.
* **Cobros Mixtos Multi-moneda:** Permite que un cliente pague una parte en Dólares efectivo, otra en Pago Móvil / Punto de Venta en Bolívares y otra en Zelle sin descuadres de caja.
* **Cálculo Preciso de IGTF 3%:** Detecta automáticamente los pagos en divisas en efectivo y aplica el 3% de IGTF sobre la fracción pagada en moneda extranjera.
* **Cierre y Arqueo Bimoneda:** Cuadre de caja discriminando billetes en USD y saldo en Bolívares.

---

## 2. Configuración General del Punto de Venta

Ubicación: **Punto de Venta ➔ Configuración ➔ Ajustes / Puntos de Venta ➔ [Seleccionar Caja]**.

### 2.1 Parámetros de Doble Moneda
| Parámetro | Configuración Recomendada | Descripción |
| :--- | :--- | :--- |
| **Habilitar Doble Moneda** | `[x] Activado` | Activa el motor bimoneda en la interfaz POS. |
| **Símbolo de Moneda Secundaria** | `Bs.F` (o `Bs.`) | Etiqueta visual para la moneda nacional. |
| **Posición del Símbolo** | `Después` (ej. `1.740,91 Bs.F`) | Formato de lectura contable. |
| **Tasa de Conversión POS** | `791.3248` (Tasa BCV del día) | Tasa de referencia utilizada por el POS. |
| **Almacén / Ubicación de Origen** | `Stock / Tienda Principal` | Filtra el stock en tiempo real en las tarjetas. |

---

## 3. Configuración de Métodos de Pago (Bs, Divisas e IGTF)

Ubicación: **Punto de Venta ➔ Configuración ➔ Métodos de Pago**.

Debe crear y clasificar correctamente cada método de pago disponible en caja:

### 3.1 Matriz de Métodos de Pago
```text
┌───────────────────────────┬──────────────┬──────────────────┬──────────────┐
│ Método de Pago            │ Moneda       │ Moneda Sec.?     │ Aplica IGTF? │
├───────────────────────────┼──────────────┼──────────────────┼──────────────┤
│ 💵 Efectivo Dólares (USD) │ USD ($)      │ [ ] No           │ [x] SÍ (3%)  │
│ 📱 Zelle / Wire USD       │ USD ($)      │ [ ] No           │ [ ] No       │
│ 💳 Punto de Venta Débito  │ Bolívares    │ [x] SÍ (pago_usd)│ [ ] No       │
│ 📲 Pago Móvil / Transfer. │ Bolívares    │ [x] SÍ (pago_usd)│ [ ] No       │
│ 💵 Efectivo Bolívares     │ Bolívares    │ [x] SÍ (pago_usd)│ [ ] No       │
└───────────────────────────┴──────────────┴──────────────────┴──────────────┘
```

* **`pago_usd = True`**: Informa al sistema que el cajero está ingresando un monto en Bolívares para que Odoo lo convierta automáticamente a la moneda base.
* **`is_igtf = True`**: Activa el cálculo automático del recargo del 3% de IGTF sobre el importe pagado con este medio.

---

## 4. Configuración del Producto de Impuesto IGTF 3%

1. Vaya a **Inventario ➔ Productos ➔ Productos ➔ Nuevo**:
   * **Nombre del Producto:** `IGTF 3% Percibido en Divisas`
   * **Tipo de Producto:** Servicio.
   * **Categoría:** Todos / Servicios.
   * **Precio de Venta:** `0.00` (El POS le asignará el valor dinámico).
   * **Impuestos de Cliente:** `0%` (El IGTF no devenga IVA sobre sí mismo).
2. En **Punto de Venta ➔ Configuración ➔ Ajustes ➔ Sección Impuesto a las Grandes Transacciones Financieras**:
   * **Producto IGTF:** Seleccione `IGTF 3% Percibido en Divisas`.
   * **Porcentaje IGTF:** `3.0%`.

---

## 5. Apertura de Turno y Control de Efectivo Dual (USD / Bs.)

Al iniciar la jornada laboral:

1. Ingrese a **Punto de Venta ➔ Abrir Sesión**.
2. Aparecerá el pop-up de **Control de Efectivo Inicial**:
   * **Fondo de Caja en USD ($):** Ingrese la cantidad de dólares físicos para dar cambio (ej: `$ 50,00`).
   * **Fondo de Caja en Bolívares (Bs.):** Ingrese el efectivo en Bolívares disponible (ej: `3.000,00 Bs.F`).
3. El sistema muestra la equivalencia total en la parte superior derecha (`1 USD = 791,32 Bs.F`).
4. Haga clic en **Abrir Sesión**.

---

## 6. Interfaz de Ventas: Catálogo y Precios Duales en Vivo

En la pantalla principal de ventas:

### 6.1 Anatomía de una Tarjeta de Producto
Cada producto muestra claramente:
```text
┌──────────────────────────────────────┐
│  [ Imagen del Producto ]             │
│  Cosmopolitan                        │
│                                      │
│  9.495,90 Bs.F  (Línea Principal Azul)│
│  $ 12,00 USD    (Subtítulo Rojo)      │
│  [ Stock: 15.00 Disp. ]              │
└──────────────────────────────────────┘
```

* **Precios Exactos:** Si en inventario el producto cuesta `$ 12.00` y la tasa BCV es `791.3248`, el POS mostrará `9.495,90 Bs.F` y `$ 12,00 USD`.
* **Filtros por Categoría:** Al navegar entre pestañas (ej: *Cocktails*, *Soft drinks*, *Comida*), los precios duales se mantienen reactivos e instantáneos.

---

## 7. Carrito de Compras y Desglose de Totales Bimoneda

Al tocar un producto, este se añade automáticamente al carrito (panel izquierdo).

### 7.1 Panel de la Orden
* **Línea del Carrito:**
  `1 x Coca-Cola ........................ 1.740,91 Bs.F / $ 2,20`
* **Cuadro de Totales Inferior:**
  ```text
  ┌─────────────────────────┬─────────────────────────┐
  │      MONEDA BASE        │    MONEDA SECUNDARIA    │
  │ SubTotal:      $ 2,20   │ SubTotal: 1.740,91 Bs.F │
  │ Impuestos:     $ 0,35   │ Impuestos:  278,55 Bs.F │
  │ Total:         $ 2,55   │ Total:    2.019,46 Bs.F │
  ├─────────────────────────┴─────────────────────────┤
  │ Total Artículos: 1        Cantidad Total: 1       │
  └───────────────────────────────────────────────────┘
  ```

---

## 8. Procesamiento de Pagos Mixtos y Cobro en Múltiples Monedas

Haga clic en el botón **Pago**:

### 8.1 Caso Práctico: Pago Mixto con IGTF
Supongamos una orden total de **$ 100.00** (Equivalente a **79.132,48 Bs.F**):

1. **Cliente paga $ 40.00 en Efectivo Dólares (Sujeto a IGTF):**
   * Seleccione el método **Efectivo Dólares**.
   * Ingrese `40.00`.
   * El POS calcula automáticamente:
     $$\text{IGTF (3\% de \$40.00)} = \$ 1.20$$
     El nuevo total a pagar se convierte en **$ 101.20**.
2. **Cliente paga el resto en Bolívares con Tarjeta de Débito:**
   * Saldo restante: `$ 61.20` $\times 791.3248 =$ **48.429,08 Bs.F**.
   * Seleccione el método **Punto de Venta Débito**.
   * Ingrese `48429.08` (en Bolívares).
   * El sistema convierte este monto y liquida el saldo exacto en USD.
3. El botón **Validar** se iluminará en verde con saldo pendiente **$ 0.00 / 0.00 Bs.F**.

---

## 9. Cálculo Automático y Ajuste Manual de Base Imponible IGTF

Si por alguna razón comercial el cajero requiere ajustar la base imponible del IGTF:
1. En la pantalla de pago, haga clic en el botón **Ajustar Base IGTF**.
2. Ingrese el monto en USD sobre el cual se calculará el 3%.
3. El sistema recalculará la línea de IGTF de inmediato.

---

## 10. Emisión de Recibo de Venta (Ticket Dual Legal SENIAT)

Al validar la venta, el sistema genera el ticket de venta cumpliendo los requisitos de la Providencia 00071:

### 10.1 Estructura del Recibo Impreso
```text
==================================================
                 MI EMPRESA, C.A.
               RIF: J-12345678-9
   Dirección: Av. Principal, Edif. Torre, Caracas
==================================================
TICKET DE VENTA Nº: POS/2026/00145
FECHA / HORA: 27/08/2026 15:30:00
CAJERO: Administrador | CAJA: Principal
TASA BCV APLICADA: 1 USD = 791,3248 Bs.F
==================================================
CANT  DESCRIPCIÓN             REF $     TOTAL BS.F
--------------------------------------------------
 1    Cosmopolitan           $ 12.00     9.495,90
 1    Coca-Cola              $  2.20     1.740,91
 1    IGTF Percibido (3%)    $  0.36       284,88
--------------------------------------------------
SUBTOTAL:                   $ 14.20    11.236,81
IVA (16%):                  $  2.27     1.796,30
IGTF (3%):                  $  0.36       284,88
--------------------------------------------------
TOTAL A PAGAR:              $ 16.83    13.317,99 Bs.F
==================================================
MÉTODOS DE PAGO:
 - Efectivo Dólares (USD):              $ 12.00
 - Punto de Venta Débito (VES):         3.822,09 Bs.F
==================================================
          ¡GRACIAS POR SU COMPRA!
==================================================
```

---

## 11. Cierre de Turno, Reporte X y Reporte Z Bimoneda

Al finalizar el turno o jornada:

1. En la esquina superior derecha, haga clic en el menú ➔ **Cerrar Sesión**.
2. Aparecerá la pantalla de **Arqueo y Cuadre de Caja**:
   * **Columna Efectivo USD:** Ingrese el total de billetes en Dólares contados en gaveta.
   * **Columna Efectivo VES:** Ingrese el total de Bolívares en efectivo contados.
3. El sistema contrastará el dinero esperado según las ventas del sistema vs. el dinero real contado, mostrando si hay diferencia cero (`0.00`).
4. Haga clic en **Cerrar Sesión y Publicar Entradas**:
   * Odoo genera automáticamente los asientos contables de ventas, cuentas por cobrar, IGTF por enterar y bancos.
   * Se genera el **Reporte Z Fiscal** con el resumen consolidado del día.

---

## 12. Sincronización de Stock y Modo Offline

* **Sincronización en Tiempo Real:** Al presionar el botón **Sync Productos** en la barra superior, el POS consulta la base de datos y actualiza las cantidades disponibles por almacén sin necesidad de recargar la página.
* **Resiliencia ante Caídas de Conexión:** Si el enlace a internet se interrumpe temporalmente, el POS almacena las órdenes en el navegador y las sincroniza automáticamente con el servidor en cuanto se restablece la conexión.

---

## 13. Matriz de Solución de Problemas Operativos (Troubleshooting)

| Síntoma | Causa Probable | Solución Paso a Paso |
| :--- | :--- | :--- |
| **La pantalla queda en blanco al abrir el POS.** | Error de caché de assets en el navegador. | Presione `Ctrl + Shift + R` en el navegador para recargar los scripts limpios. |
| **El precio de los productos sale en 0,00.** | La tasa de cambio del POS está en 0 o vacía. | Vaya a Configuración del POS y asegúrese de que la *Tasa de Conversión POS* sea superior a 1 (ej: `791.32`). |
| **El IGTF no se calcula al pagar en dólares.** | El método de pago no tiene marcada la casilla *Aplica IGTF*. | Ingrese a Métodos de Pago, edite *Efectivo Dólares* y active la casilla `[x] Aplica IGTF`. |
| **El arqueo en Bolívares no cuadra.** | Un pago en Bolívares fue registrado con un método configurado en USD. | Verifique que los métodos en Bolívares tengan `pago_usd = True`. |

---
*Manual elaborado por el equipo de ingeniería para el ecosistema Odoo 19 Localización Venezuela.*
