# Requirements traceability (backend)

Generated from SRS Appendix A. Status reflects the backend only, as of this commit.

* **Done, tested**: implemented and covered by an automated test in `backend/tests`.
* **Done**: implemented, no dedicated test yet.
* **Partial**: some of the requirement is implemented (see README, 'Known gaps').
* **Not started**: no backend code yet (mostly Phase 3 and Could-have items).

| Status | Count |
|---|---|
| Done | 88 |
| Done, tested | 138 |
| Not started | 74 |
| Partial | 32 |
| **Total** | **332** |

| ID | Module | Priority | Requirement | Status | Acceptance test |
|---|---|---|---|---|---|
| FR-DASH-001 | DASH | Must | The system shall display dashboard widgets according to the user’s role permissions and branch scope. | Done, tested | AT-DASH-02 |
| FR-DASH-002 | DASH | Must | The system shall display gross sales, discounts, refunds and net sales for the selected period using the defin… | Done, tested | AT-DASH-01 |
| FR-DASH-003 | DASH | Must | The system shall display service charges and taxes for the period separately from net sales. | Done, tested | AT-DASH-01 |
| FR-DASH-004 | DASH | Must | The system shall display payments collected for the period by payment method and currency, separately from sal… | Done, tested | AT-DASH-101 |
| FR-DASH-005 | DASH | Must | The system shall display counts of orders received, completed and cancelled and the average order value for th… | Done | AT-DASH-102 |
| FR-DASH-006 | DASH | Must | The system shall display the top 10 menu items by quantity and by net sales, and net sales by category, for th… | Partial | AT-DASH-103 |
| FR-DASH-007 | DASH | Should | The system shall display live table occupancy (occupied tables ÷ active tables) when table management is enabl… | Done | AT-DASH-104 |
| FR-DASH-008 | DASH | Must | The system shall display pending kitchen tickets by station with the age of the oldest ticket, refreshed autom… | Done | AT-DASH-03 |
| FR-DASH-009 | DASH | Should | The system shall display the number of low-stock ingredients and the current inventory valuation for the branc… | Done | AT-DASH-105 |
| FR-DASH-010 | DASH | Should | The system shall display theoretical food cost percentage and approved expenses for the period. | Done, tested | AT-DASH-106 |
| FR-DASH-011 | DASH | Could | The system shall display an indicative operating result labelled “indicative — not accounting profit”, visible… | Done, tested | AT-DASH-02 |
| FR-DASH-012 | DASH | Must | The system shall display cashier session summaries (open sessions with expected cash; closed sessions with var… | Done | AT-DASH-107 |
| FR-DASH-013 | DASH | Should | The system shall display daily, weekly and monthly trend charts of net sales and order counts for the selected… | Done, tested | AT-DASH-108 |
| FR-DASH-014 | DASH | Must | The system shall provide date-range and branch filters applied consistently to all period-based widgets and sh… | Done | AT-DASH-109 |
| FR-DASH-015 | DASH | Should | The system shall allow the user to open the underlying filtered list or report from each indicator. | Not started | AT-DASH-110 |
| FR-MENU-001 | MENU | Must | The system shall allow authorised users to create, edit, order and deactivate menu categories with Khmer and E… | Done | AT-MENU-101 |
| FR-MENU-002 | MENU | Must | The system shall allow authorised users to create menu items with code, Khmer and English names, descriptions,… | Done | AT-MENU-102 |
| FR-MENU-003 | MENU | Must | The system shall support item variants (e.g., size or portion) each with its own price and optional recipe. | Done | AT-MENU-103 |
| FR-MENU-004 | MENU | Must | The system shall support modifier groups with minimum and maximum selections, required or optional status, and… | Done, tested | AT-MENU-02 |
| FR-MENU-005 | MENU | Should | The system shall support combo and set-menu items consisting of slots with eligible items and optional price a… | Not started | AT-MENU-104 |
| FR-MENU-006 | MENU | Must | The system shall store prices per item variant, price list and branch with effective-from and effective-to tim… | Done, tested | AT-MENU-01, AT-MENU-04 |
| FR-MENU-007 | MENU | Must | The system shall maintain a complete price history showing old price, new price, effective time, user and appr… | Done, tested | AT-MENU-01 |
| FR-MENU-008 | MENU | Should | The system shall support time-based price lists (e.g., happy hour) and menu schedules by day of week, time win… | Not started | AT-MENU-105 |
| FR-MENU-009 | MENU | Must | The system shall allow kitchen and floor managers to mark an item or modifier unavailable for a branch until a… | Done, tested | AT-MENU-03 |
| FR-MENU-010 | MENU | Must | The system shall copy item name, variant, modifiers, prices, tax profile and station to the order item when it… | Done, tested | AT-MENU-01 |
| FR-MENU-011 | MENU | Must | The system shall prevent deletion of menu items that have been ordered; such items may only be deactivated. | Done | AT-MENU-106 |
| FR-MENU-012 | MENU | Must | The system shall provide menu search and filtering by name (Khmer or English), code, category, status and stat… | Done | AT-MENU-107 |
| FR-MENU-013 | MENU | Should | The system shall allow assignment of menu items to branches and to channels (POS, online, delivery platforms). | Partial | AT-MENU-108 |
| FR-MENU-014 | MENU | Should | The system shall require approval for price changes when price-approval is enabled, and apply approved changes… | Not started | AT-MENU-109 |
| FR-MENU-015 | MENU | Could | The system shall allow bulk import and export of menu items and prices from a template spreadsheet with row-le… | Not started | AT-MENU-110 |
| FR-POS-001 | POS | Must | The system shall provide a POS screen with a category bar, product grid with images and prices, search box and… | Done | AT-POS-01 |
| FR-POS-002 | POS | Must | The system shall allow users to add items by tapping a product, by search (Khmer or English, minimum 2 charact… | Partial | AT-POS-101 |
| FR-POS-003 | POS | Must | The system shall prompt for variant and modifier selection when an item has variants or modifier groups, enfor… | Done, tested | AT-POS-01 |
| FR-POS-004 | POS | Must | The system shall allow changing quantities and removing items that have not been sent to the kitchen without a… | Done, tested | AT-POS-102 |
| FR-POS-005 | POS | Must | The system shall allow adding item-level and order-level notes (e.g., “no chilli”) that are shown on kitchen t… | Done | AT-POS-103 |
| FR-POS-006 | POS | Must | The system shall allow assigning a table, guest count, server and customer to the order. | Done | AT-POS-104 |
| FR-POS-007 | POS | Must | The system shall allow applying authorised item-level and order-level discounts, requesting manager approval o… | Done, tested | AT-POS-03 |
| FR-POS-008 | POS | Must | The system shall send unsent items to the kitchen in one action, routing each item to its configured station a… | Done, tested | AT-POS-02 |
| FR-POS-009 | POS | Must | The system shall allow holding an order with a label and resuming it later from a held-orders list. | Done | AT-POS-105 |
| FR-POS-010 | POS | Must | The system shall allow splitting a bill by selected items, by seat number, or into N equal shares, and merging… | Done, tested | AT-POS-04 |
| FR-POS-011 | POS | Must | The system shall allow transferring an order to another table and moving selected unpaid items between orders … | Partial | AT-POS-106 |
| FR-POS-012 | POS | Must | The system shall allow taking payment from the POS using any enabled payment method, including split and mixed… | Done, tested | AT-POS-107 |
| FR-POS-013 | POS | Must | The system shall print, reprint (marked COPY) and optionally email or display a QR link to a receipt. | Partial | AT-POS-108 |
| FR-POS-014 | POS | Must | The system shall allow cancelling items and orders according to BR-006, requiring a reason code and approval w… | Done, tested | AT-POS-109 |
| FR-POS-015 | POS | Must | The system shall allow requesting refunds of completed transactions, routed for approval per BR-012. | Done, tested | AT-POS-110 |
| FR-POS-016 | POS | Must | The system shall attach an idempotency key to every create-order, send-order, payment and refund request and d… | Done, tested | AT-POS-02 |
| FR-POS-017 | POS | Must | The system shall support a pay-first counter mode in which payment is completed before items are sent to the k… | Done, tested | AT-POS-111 |
| FR-POS-018 | POS | Should | The system shall allow fast user switching on a shared terminal by personal PIN, with automatic lock after a c… | Partial | AT-POS-112 |
| FR-POS-019 | POS | Should | The system shall continue to accept orders and cash payments in degraded mode during internet loss when the on… | Not started | AT-POS-05 |
| FR-POS-020 | POS | Could | The system shall support weighed items with a decimal quantity entered manually or from a connected scale wher… | Not started | AT-POS-113 |
| FR-TBL-001 | TBL | Must | The system shall allow authorised users to create, edit and deactivate dining areas (e.g., indoor, outdoor, VI… | Done | AT-TBL-101 |
| FR-TBL-002 | TBL | Must | The system shall allow registering tables with a unique code per branch, area, seating capacity, shape and pos… | Done | AT-TBL-102 |
| FR-TBL-003 | TBL | Must | The system shall display a floor plan per area showing each table’s state, guest count, assigned server, order… | Done | AT-TBL-02 |
| FR-TBL-004 | TBL | Must | The system shall enforce the table state machine in Section 6.4 and reject invalid transitions. | Done, tested | AT-TBL-01 |
| FR-TBL-005 | TBL | Should | The system shall calculate live table occupancy as occupied tables ÷ active tables and seat occupancy as seate… | Done | AT-TBL-103 |
| FR-TBL-006 | TBL | Must | The system shall allow seating a party at an available table with guest count and open an order linked to that… | Done, tested | AT-TBL-02 |
| FR-TBL-007 | TBL | Should | The system shall allow combining two or more tables into a table group for one party and splitting the group, … | Done | AT-TBL-104 |
| FR-TBL-008 | TBL | Must | The system shall allow transferring a party and its open orders to another available table with audit of the m… | Done, tested | AT-TBL-03 |
| FR-TBL-009 | TBL | Must | The system shall allow marking a table Out of Service with reason and returning it to service. | Done | AT-TBL-105 |
| FR-TBL-010 | TBL | Should | The system shall show reserved tables and upcoming reservations on the floor plan when reservations are enable… | Not started | AT-TBL-106 |
| FR-TBL-011 | TBL | Should | The system shall record table service history (seated time, guests, server, orders, cleared time) for reportin… | Partial | AT-TBL-107 |
| FR-TBL-012 | TBL | Should | The system shall flag inconsistent states (e.g., Available table with an open order) on the floor plan for sup… | Done | AT-TBL-108 |
| FR-TBL-013 | TBL | Must | The system shall support a counter mode without tables in which dine-in orders use a table tag or number enter… | Done, tested | AT-TBL-109 |
| FR-ORD-001 | ORD | Must | The system shall create orders of type dine-in, takeaway or delivery from POS and online channels, each with a… | Done, tested | AT-ORD-101 |
| FR-ORD-002 | ORD | Must | The system shall maintain order status, derived kitchen status and derived payment status as separate fields p… | Done, tested | AT-ORD-01 |
| FR-ORD-003 | ORD | Must | The system shall maintain a status per order item and record each status change with user, device and timestam… | Done | AT-ORD-01 |
| FR-ORD-004 | ORD | Must | The system shall store order-time snapshots of item name, variant, modifiers, unit price, tax profile and stat… | Done, tested | AT-ORD-102 |
| FR-ORD-005 | ORD | Must | The system shall calculate line totals (unit price + modifier deltas) × quantity and order totals through the … | Done, tested | AT-ORD-103 |
| FR-ORD-006 | ORD | Must | The system shall record order notes, item notes, guest count, server, table and customer on the order. | Done | AT-ORD-104 |
| FR-ORD-007 | ORD | Must | The system shall reject in-place changes to item, variant, modifiers, quantity or price for items whose status… | Done, tested | AT-ORD-02 |
| FR-ORD-008 | ORD | Must | The system shall implement modification of sent items as cancellation of the original quantity plus a new item… | Partial | AT-ORD-02 |
| FR-ORD-009 | ORD | Must | The system shall require a reason code and, depending on item status, approval for cancellation of sent items,… | Done, tested | AT-ORD-105 |
| FR-ORD-010 | ORD | Must | The system shall allow cancelling an entire order only when it has no unrefunded payments, cancelling all its … | Done, tested | AT-ORD-03 |
| FR-ORD-011 | ORD | Must | The system shall split an order into separate orders or bills, merge orders, and move items between orders whi… | Partial | AT-ORD-106 |
| FR-ORD-012 | ORD | Must | The system shall mark an order Completed automatically when all non-cancelled items are Served/Collected and t… | Done, tested | AT-ORD-04 |
| FR-ORD-013 | ORD | Must | The system shall provide an order list and order history with search by number, date, table, customer, type, s… | Done | AT-ORD-107 |
| FR-ORD-014 | ORD | Should | The system shall show an order timeline listing all events (created, items added, sent, status changes, discou… | Done | AT-ORD-108 |
| FR-ORD-015 | ORD | Must | The system shall list open orders at day end and require manager acknowledgement to close the business day wit… | Done, tested | AT-ORD-109 |
| FR-ORD-016 | ORD | Must | The system shall use optimistic version checks so that concurrent updates to the same order cannot overwrite e… | Done, tested | AT-ORD-110 |
| FR-KDS-001 | KDS | Must | The system shall create kitchen tickets on order submission, grouping items by station, and deliver them to th… | Done, tested | AT-KDS-01 |
| FR-KDS-002 | KDS | Must | The system shall display tickets per station in queue order with order number, order type, table or pickup nam… | Done | AT-KDS-101 |
| FR-KDS-003 | KDS | Must | The system shall display preparation instructions and notes prominently and highlight allergy notes in a disti… | Done | AT-KDS-102 |
| FR-KDS-004 | KDS | Must | The system shall allow kitchen users to start preparation and mark items or whole tickets Ready (bump), and to… | Done, tested | AT-KDS-03 |
| FR-KDS-005 | KDS | Must | The system shall record timestamps for Sent, Started, Ready and Served/Collected for each item and calculate p… | Done | AT-KDS-03 |
| FR-KDS-006 | KDS | Must | The system shall colour-code tickets by age using configurable warning and critical thresholds per station and… | Partial | AT-KDS-103 |
| FR-KDS-007 | KDS | Should | The system shall allow prioritising tickets (rush) by supervisors and kitchen managers, moving them to the top… | Done | AT-KDS-104 |
| FR-KDS-008 | KDS | Must | The system shall display cancellations and modifications on the affected ticket immediately, with a strike-thr… | Done | AT-KDS-02 |
| FR-KDS-009 | KDS | Must | The system shall notify the assigned waiter (or the counter screen for takeaway) when items of their orders ar… | Done, tested | AT-KDS-03 |
| FR-KDS-010 | KDS | Should | The system shall provide an expo screen showing all stations’ progress for each order. | Not started | AT-KDS-105 |
| FR-KDS-011 | KDS | Must | The system shall support multiple stations (e.g., hot, cold, beverage, dessert, bar) with routing rules by ite… | Done | AT-KDS-01 |
| FR-KDS-012 | KDS | Must | The system shall fall back to a configured kitchen printer when a station screen is offline for longer than a … | Not started | AT-KDS-04 |
| FR-KDS-013 | KDS | Should | The system shall keep kitchen ticket history searchable by date, station, order number and status. | Not started | AT-KDS-106 |
| FR-KDS-014 | KDS | Should | The system shall allow kitchen users to mark an item that was prepared but cancelled as wastage or reusable. | Done, tested | AT-KDS-02 |
| FR-KDS-015 | KDS | Could | The system shall show an all-day count of items currently in the queue per station (e.g., 7 × Fried Rice). | Not started | AT-KDS-107 |
| FR-CUST-001 | CUST | Must | The system shall allow registering customers with name, phone, optional email, optional addresses, preferred l… | Done, tested | AT-CUST-101 |
| FR-CUST-002 | CUST | Must | The system shall allow orders without a customer record unless the order type requires contact data. | Done | AT-CUST-102 |
| FR-CUST-003 | CUST | Must | The system shall search customers by phone, name or customer code within 1 second for up to 50,000 customers. | Partial | AT-CUST-103 |
| FR-CUST-004 | CUST | Should | The system shall detect potential duplicates by normalised phone or email and allow authorised users to merge … | Done, tested | AT-CUST-01 |
| FR-CUST-005 | CUST | Should | The system shall show a customer’s order history, total visits, total spend and last visit to permitted roles. | Done, tested | AT-CUST-104 |
| FR-CUST-006 | CUST | Should | The system shall record customer preferences (e.g., spice level, seating) and allergy notes and display them o… | Done | AT-CUST-105 |
| FR-CUST-007 | CUST | Could | The system shall allow classifying customers (e.g., regular, VIP, corporate) for promotions and reporting. | Done | AT-CUST-106 |
| FR-CUST-008 | CUST | Could | The system shall maintain loyalty point balances and transactions when the loyalty feature is enabled. | Not started | AT-CUST-107 |
| FR-CUST-009 | CUST | Must | The system shall mask phone and email for roles without customer.contact.view permission. | Done, tested | AT-CUST-02 |
| FR-CUST-010 | CUST | Should | The system shall anonymise a customer on approved request, retaining financial records linked to an anonymised… | Done, tested | AT-CUST-03 |
| FR-CUST-011 | CUST | Could | The system shall maintain credit accounts for approved customers or companies with credit limit and balance wh… | Not started | AT-CUST-108 |
| FR-RSV-001 | RSV | Must | The system shall allow creating reservations with date, time, party size, customer name and phone, special req… | Done, tested | AT-RSV-101 |
| FR-RSV-002 | RSV | Must | The system shall show available tables and table combinations for the requested time and party size based on d… | Done, tested | AT-RSV-01 |
| FR-RSV-003 | RSV | Must | The system shall prevent assigning a table to overlapping reservation windows using a database constraint. | Done, tested | AT-RSV-01 |
| FR-RSV-004 | RSV | Must | The system shall allow modifying and cancelling reservations with reason and record the history of changes. | Done | AT-RSV-102 |
| FR-RSV-005 | RSV | Should | The system shall set the assigned table to Reserved at the configured hold window before the reservation time … | Done | AT-RSV-103 |
| FR-RSV-006 | RSV | Should | The system shall mark reservations as No-show after the configured grace period when not seated, and track no-… | Done, tested | AT-RSV-02 |
| FR-RSV-007 | RSV | Must | The system shall seat a reservation in one action, linking the reservation to the table and the new order. | Done, tested | AT-RSV-104 |
| FR-RSV-008 | RSV | Should | The system shall maintain a waiting list with party name, size, phone, time added and quoted wait time, and es… | Done, tested | AT-RSV-03 |
| FR-RSV-009 | RSV | Could | The system shall notify waiting-list parties and reservation customers by the configured channels when enabled… | Partial | AT-RSV-03 |
| FR-RSV-010 | RSV | Should | The system shall provide a reservation calendar and list view with search by date, name, phone and status. | Done | AT-RSV-105 |
| FR-RSV-011 | RSV | Should | The system shall warn staff when a walk-in is seated at a table reserved within the next configurable interval… | Done, tested | AT-RSV-106 |
| FR-BILL-001 | BILL | Must | The system shall generate one or more bills for an order, each listing items, modifiers, quantities, unit pric… | Done, tested | AT-BILL-101 |
| FR-BILL-002 | BILL | Must | The system shall perform all bill calculations in the backend calculation engine using the order-time snapshot… | Done, tested | AT-BILL-01 |
| FR-BILL-003 | BILL | Must | The system shall apply the calculation order of BR-008, including pro rata allocation of order-level discounts… | Done, tested | AT-BILL-01 |
| FR-BILL-004 | BILL | Must | The system shall support tax-exclusive and tax-inclusive price lists and show the tax amount on the bill and r… | Partial | AT-BILL-102 |
| FR-BILL-005 | BILL | Must | The system shall calculate service charges and taxes using effective-dated tax profiles that define rate, base… | Done, tested | AT-BILL-01 |
| FR-BILL-006 | BILL | Must | The system shall round amounts per currency rules and show any rounding difference as a separate line. | Partial | AT-BILL-103 |
| FR-BILL-007 | BILL | Must | The system shall support split bills by item, seat, or equal shares, and merged bills, with the sum of split b… | Done, tested | AT-BILL-104 |
| FR-BILL-008 | BILL | Must | The system shall record payments by cash (USD, KHR), bank transfer, card (terminal reference) and QR/digital m… | Done, tested | AT-BILL-02 |
| FR-BILL-009 | BILL | Must | The system shall allocate a payment to one or more bills and support multiple payments per bill, including mix… | Partial | AT-BILL-02 |
| FR-BILL-010 | BILL | Must | The system shall calculate change for cash payments in the selected change currency, with KHR rounding to the … | Done, tested | AT-BILL-02 |
| FR-BILL-011 | BILL | Should | The system shall support partial payments when enabled, keeping the bill Partially Paid until the outstanding … | Done, tested | AT-BILL-105 |
| FR-BILL-012 | BILL | Must | The system shall issue receipts with sequential numbers per branch, in Khmer and/or English, with the fields c… | Partial | AT-BILL-106 |
| FR-BILL-013 | BILL | Must | The system shall reprint receipts marked “COPY” with reprint count and audit entry. | Done | AT-BILL-107 |
| FR-BILL-014 | BILL | Must | The system shall process full and partial refunds referencing the original payment, with reason, approval and … | Done, tested | AT-BILL-04 |
| FR-BILL-015 | BILL | Must | The system shall void an unfinalised payment entered in error within the same cashier session only with superv… | Done | AT-BILL-108 |
| FR-BILL-016 | BILL | Should | The system shall handle electronic payments via provider integration where available, recording Pending, Confi… | Not started | AT-BILL-03, AT-BILL-05 |
| FR-BILL-017 | BILL | Could | The system shall transfer an unpaid bill to an approved credit account within its credit limit and record sett… | Not started | AT-BILL-109 |
| FR-BILL-018 | BILL | Should | The system shall provide a payment reconciliation view per business day comparing recorded electronic payments… | Not started | AT-BILL-110 |
| FR-BILL-019 | BILL | Could | The system shall record tips separately from sales when tip recording is enabled. | Not started | AT-BILL-111 |
| FR-BILL-020 | BILL | Should | The system shall issue credit notes for refunds where required by configuration (subject to V-02). | Not started | AT-BILL-112 |
| FR-INV-001 | INV | Must | The system shall allow registering ingredients and stock items with code, Khmer and English names, category, s… | Done | AT-INV-101 |
| FR-INV-002 | INV | Must | The system shall maintain storage locations (e.g., dry store, chiller, freezer, bar) per branch. | Done | AT-INV-102 |
| FR-INV-003 | INV | Must | The system shall record all stock changes as append-only inventory transactions with type, quantity, unit, uni… | Done, tested | AT-INV-01 |
| FR-INV-004 | INV | Must | The system shall provide no function to edit on-hand quantities directly. | Done, tested | AT-INV-02 |
| FR-INV-005 | INV | Must | The system shall record opening stock per location once, with cost. | Done | AT-INV-103 |
| FR-INV-006 | INV | Must | The system shall post stock receipts from goods receipts and record manual issues with reason. | Done, tested | AT-INV-01 |
| FR-INV-007 | INV | Should | The system shall record stock transfers between locations and, when multi-branch is enabled, between branches … | Partial | AT-INV-104 |
| FR-INV-008 | INV | Must | The system shall record manual adjustments with reason code and route adjustments above the value threshold fo… | Done, tested | AT-INV-02 |
| FR-INV-009 | INV | Must | The system shall record wastage of ingredients or prepared menu items with reason; menu-item wastage is conver… | Done, tested | AT-INV-105 |
| FR-INV-010 | INV | Should | The system shall support stock counts (full or partial, by location or category) with blind entry, variance ca… | Done, tested | AT-INV-03 |
| FR-INV-011 | INV | Should | The system shall track batches and expiry dates for configured items, issue stock first-expiry-first-out by de… | Partial | AT-INV-106 |
| FR-INV-012 | INV | Must | The system shall show stock on hand by ingredient and location, with value at weighted average cost, and calcu… | Done | AT-INV-107 |
| FR-INV-013 | INV | Must | The system shall raise low-stock alerts when on-hand reaches or falls below the reorder level. | Done | AT-INV-108 |
| FR-INV-014 | INV | Must | The system shall show complete stock movement history per ingredient with running balance. | Done, tested | AT-INV-109 |
| FR-INV-015 | INV | Must | The system shall reverse an erroneous transaction by posting a referencing reversal, with reason and permissio… | Done, tested | AT-INV-04 |
| FR-INV-016 | INV | Must | The system shall prevent manual issues and transfers that would make stock negative, and handle sales consumpt… | Done, tested | AT-INV-110 |
| FR-RCP-001 | RCP | Must | The system shall allow creating recipes for menu item variants and modifiers with yield, portion size and ingr… | Done, tested | AT-RCP-101 |
| FR-RCP-002 | RCP | Should | The system shall support sub-recipes (prepared items) that can be used as ingredients in other recipes and pro… | Not started | AT-RCP-102 |
| FR-RCP-003 | RCP | Must | The system shall maintain recipe versions with status Draft, Active or Retired and effective-from time; publis… | Done, tested | AT-RCP-04 |
| FR-RCP-004 | RCP | Must | The system shall support units of mass (g, kg), volume (ml, L) and count (piece) with fixed intra-dimension fa… | Done, tested | AT-RCP-02 |
| FR-RCP-005 | RCP | Must | The system shall calculate ingredient gross quantity from net quantity and loss percentages and convert it to … | Done, tested | AT-RCP-01 |
| FR-RCP-006 | RCP | Must | The system shall post SALE_CONSUMPTION inventory transactions from the active recipe version, including modifi… | Done, tested | AT-RCP-01 |
| FR-RCP-007 | RCP | Must | The system shall calculate recipe cost per portion from current weighted average ingredient costs and show it … | Done, tested | AT-RCP-03 |
| FR-RCP-008 | RCP | Must | The system shall calculate food cost percentage and gross margin per menu item (selling price excluding tax − … | Done, tested | AT-RCP-03 |
| FR-RCP-009 | RCP | Must | The system shall record recipe modification history (who, when, what changed, previous version). | Done | AT-RCP-04 |
| FR-RCP-010 | RCP | Must | The system shall list menu items sold without an active recipe (“unmapped items”). | Done, tested | AT-RCP-103 |
| FR-RCP-011 | RCP | Should | The system shall produce theoretical consumption, actual usage and variance by ingredient for a period based o… | Done, tested | AT-RCP-104 |
| FR-RCP-012 | RCP | Could | The system shall allow recording production of sub-recipe batches, consuming ingredients and increasing the pr… | Not started | AT-RCP-105 |
| FR-RCP-013 | RCP | Could | The system shall display preparation method text and photos for recipes to kitchen users. | Partial | AT-RCP-106 |
| FR-PUR-001 | PUR | Must | The system shall maintain suppliers with name, contact person, phone, email, address, tax identification (if p… | Done, tested | AT-PUR-101 |
| FR-PUR-002 | PUR | Should | The system shall allow users to create purchase requests manually or from low-stock alerts with suggested quan… | Done, tested | AT-PUR-102 |
| FR-PUR-003 | PUR | Must | The system shall create purchase orders from requests or directly, with supplier, delivery date, lines, unit p… | Done, tested | AT-PUR-103 |
| FR-PUR-004 | PUR | Must | The system shall route purchase orders for approval according to configurable value bands and prevent the crea… | Done, tested | AT-PUR-01 |
| FR-PUR-005 | PUR | Should | The system shall produce a purchase order document (print and PDF, Khmer and English) and optionally email it … | Partial | AT-PUR-104 |
| FR-PUR-006 | PUR | Must | The system shall record goods receipts against a PO or as direct receipts, capturing received quantity, unit, … | Done, tested | AT-PUR-105 |
| FR-PUR-007 | PUR | Must | The system shall validate receipts against PO quantities and price tolerance and require approval beyond toler… | Done, tested | AT-PUR-03 |
| FR-PUR-008 | PUR | Must | The system shall post a goods receipt to inventory exactly once, updating stock and weighted average cost in o… | Done, tested | AT-PUR-02 |
| FR-PUR-009 | PUR | Should | The system shall record purchase returns referencing the goods receipt and reduce stock accordingly. | Done, tested | AT-PUR-106 |
| FR-PUR-010 | PUR | Should | The system shall record supplier invoices, match them to receipts and flag differences. | Done, tested | AT-PUR-107 |
| FR-PUR-011 | PUR | Should | The system shall record supplier payments against invoices and show supplier balances and ageing. | Done, tested | AT-PUR-108 |
| FR-PUR-012 | PUR | Should | The system shall show supplier history (POs, receipts, invoices, returns, price history per item). | Done, tested | AT-PUR-109 |
| FR-PUR-013 | PUR | Must | The system shall maintain PO status Draft, Submitted, Approved, Sent, Partially Received, Received, Closed and… | Done | AT-PUR-110 |
| FR-EXP-001 | EXP | Must | The system shall maintain expense categories with Khmer and English names, attachment requirement and active s… | Done | AT-EXP-101 |
| FR-EXP-002 | EXP | Must | The system shall allow recording expenses with branch, category, date, description, amount, currency, payee an… | Done, tested | AT-EXP-03 |
| FR-EXP-003 | EXP | Must | The system shall route expenses above the submitter’s limit for approval by a different user and record approv… | Done, tested | AT-EXP-01 |
| FR-EXP-004 | EXP | Must | The system shall record payment method, payment date and reference for approved expenses. | Done | AT-EXP-102 |
| FR-EXP-005 | EXP | Must | The system shall record cash paid-outs from an open cashier session as cash movements linked to the expense. | Done, tested | AT-EXP-02 |
| FR-EXP-006 | EXP | Must | The system shall reverse paid expenses only with approval, retaining the original record. | Done | AT-EXP-103 |
| FR-EXP-007 | EXP | Must | The system shall provide daily and monthly expense summaries by category, branch and payment method. | Done, tested | AT-EXP-104 |
| FR-EXP-008 | EXP | Could | The system shall support recurring expense templates that generate draft expenses on a schedule. | Not started | AT-EXP-105 |
| FR-EXP-009 | EXP | Must | The system shall store attachments securely with access only for permitted roles. | Done, tested | AT-EXP-106 |
| FR-STAFF-001 | STAFF | Should | The system shall maintain employee profiles (name, Khmer name, employee code, department, position, branch, em… | Done, tested | AT-STAFF-101 |
| FR-STAFF-002 | STAFF | Should | The system shall maintain departments and positions. | Done | AT-STAFF-102 |
| FR-STAFF-003 | STAFF | Should | The system shall allow scheduling shifts per employee and branch and show a weekly schedule view. | Done, tested | AT-STAFF-103 |
| FR-STAFF-004 | STAFF | Could | The system shall record shift attendance (clock in and out) when enabled. | Done | AT-STAFF-104 |
| FR-STAFF-005 | STAFF | Must | The system shall require an open cashier session for cash payments, refunds, paid-outs and paid-ins, allowing … | Done, tested | AT-STAFF-03 |
| FR-STAFF-006 | STAFF | Must | The system shall record the opening float per currency, optionally by denomination, with the opening time, use… | Done | AT-STAFF-105 |
| FR-STAFF-007 | STAFF | Must | The system shall link each cash payment, change given, cash refund and cash movement to the active cashier ses… | Done, tested | AT-STAFF-106 |
| FR-STAFF-008 | STAFF | Must | The system shall record paid-outs, paid-ins and cash drops with reason and approval where required. | Done | AT-STAFF-107 |
| FR-STAFF-009 | STAFF | Must | The system shall capture a blind closing count per currency without showing the expected amount until the coun… | Done, tested | AT-STAFF-01, AT-STAFF-04 |
| FR-STAFF-010 | STAFF | Must | The system shall calculate expected cash and variance per currency using the formula in Section 6.14 and show … | Done, tested | AT-STAFF-01 |
| FR-STAFF-011 | STAFF | Must | The system shall require manager approval with reason for variances beyond the configured tolerance before the… | Done, tested | AT-STAFF-02 |
| FR-STAFF-012 | STAFF | Must | The system shall produce a session (X and Z) report showing sales, payments by method and currency, refunds, d… | Done | AT-STAFF-108 |
| FR-STAFF-013 | STAFF | Should | The system shall allow managers to force-close abandoned sessions, flagging them for later count. | Done | AT-STAFF-109 |
| FR-STAFF-014 | STAFF | Should | The system shall record staff activity history (sessions, sales, voids, discounts, refunds) per employee for a… | Done | AT-STAFF-110 |
| FR-DLV-001 | DLV | Must | The system shall create takeaway orders with pickup name or number and optional scheduled pickup time. | Done | AT-DLV-101 |
| FR-DLV-002 | DLV | Could | The system shall create delivery orders with customer phone, address, landmark notes, map location (optional) … | Partial | AT-DLV-102 |
| FR-DLV-003 | DLV | Could | The system shall calculate delivery fees from zone and order-value rules, add them as a separate charge with i… | Not started | AT-DLV-01 |
| FR-DLV-004 | DLV | Could | The system shall assign delivery orders to riders and track statuses with timestamps. | Not started | AT-DLV-103 |
| FR-DLV-005 | DLV | Could | The system shall allow riders to confirm delivery (status and optional photo or customer name) on a mobile bro… | Not started | AT-DLV-104 |
| FR-DLV-006 | DLV | Should | The system shall show a takeaway ready board or notify customers when takeaway orders are ready. | Not started | AT-DLV-03 |
| FR-DLV-007 | DLV | Could | The system shall record third-party platform orders with platform, platform order reference, commission and se… | Not started | AT-DLV-02 |
| FR-DLV-008 | DLV | Could | The system shall import or receive third-party platform orders through integration adapters where available. | Not started | AT-DLV-105 |
| FR-DLV-009 | DLV | Could | The system shall process delivery cancellations and failed deliveries with reason, applying refund and wastage… | Not started | AT-DLV-106 |
| FR-DLV-010 | DLV | Could | The system shall reconcile platform settlements against recorded platform orders and commissions and list diff… | Not started | AT-DLV-02 |
| FR-DLV-011 | DLV | Could | The system shall report delivery performance (orders, average preparation and delivery times, late deliveries,… | Not started | AT-DLV-107 |
| FR-PROMO-001 | PROMO | Must | The system shall support manual percentage and fixed-amount discounts at item level and order level with reaso… | Done, tested | AT-PROMO-101 |
| FR-PROMO-002 | PROMO | Must | The system shall enforce per-role discount limits (maximum percentage, maximum amount per bill, maximum total … | Done, tested | AT-PROMO-102 |
| FR-PROMO-003 | PROMO | Must | The system shall apply discounts before service charge and tax per BR-008 and allocate order-level discounts t… | Done, tested | AT-PROMO-103 |
| FR-PROMO-004 | PROMO | Should | The system shall define promotions with type (percentage, amount, fixed price, buy-X-get-Y, combo price), scop… | Partial | AT-PROMO-104 |
| FR-PROMO-005 | PROMO | Should | The system shall evaluate automatic promotions when items are added and show applied and non-applied promotion… | Done, tested | AT-PROMO-01 |
| FR-PROMO-006 | PROMO | Should | The system shall support promotion codes (single-use or multi-use with limits per code and per customer) with … | Done, tested | AT-PROMO-03 |
| FR-PROMO-007 | PROMO | Could | The system shall support customer-specific promotions by customer classification. | Done | AT-PROMO-105 |
| FR-PROMO-008 | PROMO | Must | The system shall enforce combination rules (combinable flag, priority, maximum one order-level discount by def… | Done, tested | AT-PROMO-01 |
| FR-PROMO-009 | PROMO | Must | The system shall record every discount and promotion application with order, bill, value, user, approver, reas… | Done, tested | AT-PROMO-106 |
| FR-PROMO-010 | PROMO | Must | The system shall prevent the same promotion or manual discount from being applied twice to the same line or bi… | Done, tested | AT-PROMO-02 |
| FR-PROMO-011 | PROMO | Could | The system shall support loyalty earning and redemption rules when loyalty is enabled (D-14). | Not started | AT-PROMO-107 |
| FR-PROMO-012 | PROMO | Should | The system shall support staff meal and complimentary (comp) discounts with dedicated reasons, limits and repo… | Partial | AT-PROMO-108 |
| FR-RPT-001 | RPT | Must | The system shall produce a daily sales report (RPT-01) with gross sales, discounts, refunds, net sales, servic… | Done | AT-RPT-01 |
| FR-RPT-002 | RPT | Must | The system shall produce monthly sales reports (RPT-02) summarising daily figures for a month. | Done | AT-RPT-101 |
| FR-RPT-003 | RPT | Must | The system shall produce sales by menu category and by menu item reports (RPT-03, RPT-04) with quantity, gross… | Done | AT-RPT-04 |
| FR-RPT-004 | RPT | Should | The system shall produce sales by employee (server and cashier) report (RPT-05). | Done, tested | AT-RPT-102 |
| FR-RPT-005 | RPT | Could | The system shall produce sales by branch and branch comparison reports (RPT-06) when multi-branch is enabled. | Not started | AT-RPT-103 |
| FR-RPT-006 | RPT | Must | The system shall produce a sales by payment method report (RPT-07) by currency with base equivalents, distingu… | Done, tested | AT-RPT-104 |
| FR-RPT-007 | RPT | Should | The system shall produce order volume, average order value and peak-hour analysis reports (RPT-08, RPT-09) by … | Done, tested | AT-RPT-105 |
| FR-RPT-008 | RPT | Could | The system shall produce a table turnover report (RPT-10) with covers, average dining time and turns per table… | Done, tested | AT-RPT-106 |
| FR-RPT-009 | RPT | Must | The system shall produce a cancelled and voided items report (RPT-11) with reason, status at cancellation, use… | Done | AT-RPT-107 |
| FR-RPT-010 | RPT | Must | The system shall produce a refund report (RPT-12) with original payment, amount, method, reason, requester and… | Done | AT-RPT-108 |
| FR-RPT-011 | RPT | Must | The system shall produce a discount and promotion report (RPT-13) by type, reason, user, approver and value. | Done | AT-RPT-109 |
| FR-RPT-012 | RPT | Must | The system shall produce a tax and service-charge summary report (RPT-14) by tax profile, rate and order type,… | Done, tested | AT-RPT-110 |
| FR-RPT-013 | RPT | Could | The system shall produce a customer purchase history report (RPT-25) for permitted roles. | Done, tested | AT-RPT-111 |
| FR-RPT-014 | RPT | Should | The system shall produce a kitchen preparation-time report (RPT-15) by station, item and hour with average, 90… | Done, tested | AT-RPT-112 |
| FR-RPT-015 | RPT | Should | The system shall produce ingredient consumption, actual usage and variance reports (RPT-16). | Done, tested | AT-RPT-113 |
| FR-RPT-016 | RPT | Must | The system shall produce inventory valuation and low-stock reports (RPT-17, RPT-18). | Done | AT-RPT-114 |
| FR-RPT-017 | RPT | Should | The system shall produce a wastage report (RPT-19) by ingredient, item, reason, station and value. | Done, tested | AT-RPT-115 |
| FR-RPT-018 | RPT | Should | The system shall produce purchase and supplier reports (RPT-20, RPT-21). | Done, tested | AT-RPT-116 |
| FR-RPT-019 | RPT | Should | The system shall produce an expense report (RPT-22) by category, branch, period and payment method. | Done, tested | AT-RPT-117 |
| FR-RPT-020 | RPT | Should | The system shall produce food cost and gross margin reports (RPT-23) per item and category using theoretical a… | Done, tested | AT-RPT-118 |
| FR-RPT-021 | RPT | Must | The system shall produce a cashier shift report (RPT-24) with expected and counted cash and variance per sessi… | Done | AT-RPT-119 |
| FR-RPT-022 | RPT | Must | The system shall support filters for date, time, branch, category, employee, order type and payment method whe… | Partial | AT-RPT-03 |
| FR-RPT-023 | RPT | Must | The system shall export reports to PDF (with Khmer text) and Excel (.xlsx) and support printing, with exported… | Partial | AT-RPT-02 |
| FR-RPT-024 | RPT | Must | The system shall restrict each report by permission and branch scope and record exports of financial reports i… | Done, tested | AT-RPT-03 |
| FR-RPT-025 | RPT | Should | The system shall run reports exceeding 10 seconds as background jobs and notify the user when ready. | Not started | AT-RPT-120 |
| FR-RPT-026 | RPT | Should | The system shall produce a control exceptions report (RPT-26) listing self-approvals, forced session closures,… | Not started | AT-RPT-121 |
| FR-RPT-027 | RPT | Could | The system shall allow scheduling reports for email delivery to permitted users. | Not started | AT-RPT-122 |
| FR-USER-001 | USER | Must | The system shall allow administrators to create and edit user accounts with name, username, email, phone, pref… | Done, tested | AT-USER-101 |
| FR-USER-002 | USER | Must | The system shall allow activating and deactivating accounts, revoking all sessions on deactivation; accounts a… | Done, tested | AT-USER-102 |
| FR-USER-003 | USER | Must | The system shall provide predefined roles (Section 4.1) and allow custom roles composed of permissions from th… | Done | AT-USER-103 |
| FR-USER-004 | USER | Must | The system shall support personal PIN login on registered POS and KDS devices for quick user switching, in add… | Done | AT-USER-104 |
| FR-USER-005 | USER | Must | The system shall store passwords and PINs using Argon2id (or bcrypt) hashing and enforce the password policy. | Done | AT-USER-105 |
| FR-USER-006 | USER | Must | The system shall provide self-service password reset by email or administrator reset with forced change at nex… | Done | AT-USER-106 |
| FR-USER-007 | USER | Should | The system shall support multi-factor authentication (TOTP) for Owner, GM, Accountant and System Administrator… | Not started | AT-USER-107 |
| FR-USER-008 | USER | Must | The system shall enforce permissions, branch scope and ownership scope in the backend on every API request. | Done, tested | AT-USER-01 |
| FR-USER-009 | USER | Must | The system shall manage sessions with idle timeout, absolute timeout, device binding for POS/KDS and the abili… | Partial | AT-USER-108 |
| FR-USER-010 | USER | Must | The system shall lock accounts after a configurable number of failed attempts (proposed 5 within 15 minutes) f… | Done, tested | AT-USER-02 |
| FR-USER-011 | USER | Must | The system shall provide an approval service that evaluates approval limits by role and requires an approver d… | Done, tested | AT-USER-04 |
| FR-USER-012 | USER | Must | The system shall record authentication history including successful logins, logouts, failed attempts, lockouts… | Done | AT-USER-02 |
| FR-USER-013 | USER | Must | The system shall prevent users from changing their own roles, permissions or approval limits. | Done, tested | AT-USER-03 |
| FR-USER-014 | USER | Should | The system shall provide a user-access review report listing users, roles, branches, sensitive permissions and… | Not started | AT-USER-109 |
| FR-NOTIF-001 | NOTIF | Must | The system shall push real-time events (new orders, item status changes, menu availability changes, table stat… | Done, tested | AT-NOTIF-101 |
| FR-NOTIF-002 | NOTIF | Must | The system shall notify waiters or counter screens when items are ready. | Done, tested | AT-NOTIF-102 |
| FR-NOTIF-003 | NOTIF | Must | The system shall alert supervisors and kitchen managers when tickets exceed delay thresholds. | Not started | AT-NOTIF-103 |
| FR-NOTIF-004 | NOTIF | Must | The system shall notify approvers of pending discount, refund, void, adjustment, purchase-order and expense ap… | Done | AT-NOTIF-104 |
| FR-NOTIF-005 | NOTIF | Must | The system shall notify inventory officers and kitchen managers of low-stock and expiring items daily and when… | Done | AT-NOTIF-01 |
| FR-NOTIF-006 | NOTIF | Should | The system shall alert cashiers and managers of failed or pending electronic payments. | Not started | AT-NOTIF-105 |
| FR-NOTIF-007 | NOTIF | Could | The system shall send reservation confirmations, reminders and waiting-list messages through configured channe… | Not started | AT-NOTIF-03 |
| FR-NOTIF-008 | NOTIF | Should | The system shall send emails (e.g., purchase orders, scheduled reports, password resets) through a configured … | Done | AT-NOTIF-106 |
| FR-NOTIF-009 | NOTIF | Should | The system shall remind cashiers and managers of sessions still open after the scheduled shift end or day-end … | Not started | AT-NOTIF-107 |
| FR-NOTIF-010 | NOTIF | Must | The system shall send system alerts for printer offline, KDS offline, synchronisation errors, backup failures … | Partial | AT-NOTIF-02 |
| FR-NOTIF-011 | NOTIF | Could | The system shall allow users to configure which non-mandatory notifications they receive. | Not started | AT-NOTIF-108 |
| FR-NOTIF-012 | NOTIF | Must | The system shall provide a notification centre with unread count, read/unread state and links to the related r… | Done | AT-NOTIF-109 |
| FR-NOTIF-013 | NOTIF | Should | The system shall log external message deliveries with status and retry failed deliveries with exponential back… | Partial | AT-NOTIF-03 |
| FR-CFG-001 | CFG | Must | The system shall maintain the restaurant profile (legal name, trade name in Khmer and English, address, phone,… | Not started | AT-CFG-101 |
| FR-CFG-002 | CFG | Must | The system shall allow enabling and disabling optional modules and features and applying a business-type profi… | Not started | AT-CFG-102 |
| FR-CFG-003 | CFG | Must | The system shall maintain branch information (name, address, phone, opening hours, receipt header) for each br… | Done | AT-CFG-103 |
| FR-CFG-004 | CFG | Must | The system shall configure currencies (base USD, KHR), display symbols, decimals and exchange rates with effec… | Done, tested | AT-CFG-02 |
| FR-CFG-005 | CFG | Must | The system shall configure tax and service-charge profiles with rate, base, inclusive/exclusive mode, applicab… | Done, tested | AT-CFG-01 |
| FR-CFG-006 | CFG | Must | The system shall configure rounding rules per currency (decimals and cash rounding increment). | Done | AT-CFG-104 |
| FR-CFG-007 | CFG | Must | The system shall configure receipt and invoice templates (language, header, footer, fields, logo, paper width)… | Not started | AT-CFG-105 |
| FR-CFG-008 | CFG | Must | The system shall configure numbering series for orders, receipts, invoices, credit notes, purchase orders and … | Not started | AT-CFG-106 |
| FR-CFG-009 | CFG | Must | The system shall configure kitchen stations, routing rules, delay thresholds and backup printers. | Done | AT-CFG-107 |
| FR-CFG-010 | CFG | Must | The system shall configure the service model (pay-first or pay-later) per branch and order type. | Partial | AT-CFG-108 |
| FR-CFG-011 | CFG | Should | The system shall configure dining settings: table numbering, default dining duration, reservation hold time, g… | Not started | AT-CFG-109 |
| FR-CFG-012 | CFG | Must | The system shall configure payment methods per branch (type, currencies, reference required, provider integrat… | Done | AT-CFG-110 |
| FR-CFG-013 | CFG | Must | The system shall configure languages (default and available), date format (default DD/MM/YYYY), time format an… | Not started | AT-CFG-111 |
| FR-CFG-014 | CFG | Should | The system shall configure inventory settings: consumption point, negative-stock policy, valuation method, adj… | Partial | AT-CFG-112 |
| FR-CFG-015 | CFG | Must | The system shall configure printers (network or USB through a print agent), paper width, copies per document t… | Not started | AT-CFG-113 |
| FR-CFG-016 | CFG | Must | The system shall configure the business day-end time and provide a day-end close procedure that checks open or… | Done, tested | AT-CFG-03 |
| FR-CFG-017 | CFG | Must | The system shall configure approval limits by role for discounts, voids, refunds, adjustments, purchase orders… | Done | AT-CFG-114 |
| FR-CFG-018 | CFG | Must | The system shall require approval for changes to tax, service-charge, exchange-rate, payment-method, rounding … | Partial | AT-CFG-01 |
| FR-CFG-019 | CFG | Must | The system shall register devices (POS terminals, KDS screens, print agents) with branch, name and status, and… | Done | AT-CFG-115 |
| FR-CFG-020 | CFG | Should | The system shall configure notification rules and external channel credentials (stored as secrets, not display… | Not started | AT-CFG-116 |
| FR-AUD-001 | AUD | Must | The system shall create an audit entry for each event in Section 6.21 with actor, timestamp, action, affected … | Done, tested | AT-AUD-01 |
| FR-AUD-002 | AUD | Must | The system shall record authentication events (login, logout, failed login, lockout, PIN switch). | Done | AT-AUD-101 |
| FR-AUD-003 | AUD | Must | The system shall record order, kitchen, discount, payment, refund, receipt and invoice events. | Done | AT-AUD-102 |
| FR-AUD-004 | AUD | Must | The system shall record inventory, purchasing, expense, cashier session, user, role and configuration events. | Done | AT-AUD-103 |
| FR-AUD-005 | AUD | Must | The system shall record exports of financial reports and audit logs. | Done, tested | AT-AUD-104 |
| FR-AUD-006 | AUD | Must | The system shall store audit entries in an append-only table protected by database privileges and a per-entry … | Done, tested | AT-AUD-02 |
| FR-AUD-007 | AUD | Must | The system shall provide audit search by date range, user, action, entity type, entity ID and branch with pagi… | Done | AT-AUD-105 |
| FR-AUD-008 | AUD | Should | The system shall export audit search results to Excel or CSV for permitted users. | Done | AT-AUD-106 |
| FR-AUD-009 | AUD | Must | The system shall retain audit entries for the retention period in Section 10.10 and archive older entries with… | Not started | AT-AUD-107 |
| FR-AUD-010 | AUD | Should | The system shall verify the hash chain daily and alert administrators and the Owner on any break. | Done | AT-AUD-03 |
| FR-BRN-001 | BRN | Could | The system shall allow registering branches with code, names, address, contact, opening hours, time zone and s… | Not started | AT-BRN-101 |
| FR-BRN-002 | BRN | Must | The system shall scope all operational records by branch and apply branch filters in the data-access layer for… | Done, tested | AT-BRN-01 |
| FR-BRN-003 | BRN | Could | The system shall support branch-specific menu assignment, availability and prices overriding restaurant-level … | Not started | AT-BRN-02 |
| FR-BRN-004 | BRN | Could | The system shall maintain inventory balances and transactions per branch and location. | Not started | AT-BRN-102 |
| FR-BRN-005 | BRN | Could | The system shall allow suppliers to be shared or restricted to specific branches. | Not started | AT-BRN-103 |
| FR-BRN-006 | BRN | Could | The system shall support inter-branch stock transfers with dispatch, in-transit and receipt steps and variance… | Not started | AT-BRN-03 |
| FR-BRN-007 | BRN | Could | The system shall assign users to branches and require a cross-branch permission for viewing other branches’ da… | Partial | AT-BRN-01 |
| FR-BRN-008 | BRN | Could | The system shall produce consolidated reports across permitted branches with per-branch breakdown. | Not started | AT-BRN-104 |
| FR-BRN-009 | BRN | Could | The system shall provide a branch comparison dashboard (net sales, orders, AOV, food cost %, labour hours if r… | Not started | AT-BRN-105 |
| FR-BRN-010 | BRN | Could | The system shall allow branch-level overrides of operational settings (receipt header, printers, stations, ser… | Not started | AT-BRN-106 |
| FR-ONL-001 | ONL | Could | The system shall publish a public menu per branch showing available items, images, descriptions, online prices… | Not started | AT-ONL-101 |
| FR-ONL-002 | ONL | Could | The system shall provide a cart with item customisation enforcing modifier rules and quantity limits. | Not started | AT-ONL-102 |
| FR-ONL-003 | ONL | Could | The system shall allow selecting pickup or delivery and an ASAP or scheduled time within opening hours and pre… | Not started | AT-ONL-103 |
| FR-ONL-004 | ONL | Could | The system shall support guest checkout with name and phone and optional customer accounts with email or phone… | Not started | AT-ONL-104 |
| FR-ONL-005 | ONL | Could | The system shall validate availability, prices, opening hours, minimum order and delivery zone in the backend … | Not started | AT-ONL-02 |
| FR-ONL-006 | ONL | Could | The system shall apply promotion codes with server-side validation. | Not started | AT-ONL-105 |
| FR-ONL-007 | ONL | Could | The system shall integrate with a payment gateway using hosted payment pages or tokens so that card data never… | Not started | AT-ONL-04 |
| FR-ONL-008 | ONL | Could | The system shall show an order confirmation with order number and send it by the configured channel. | Not started | AT-ONL-106 |
| FR-ONL-009 | ONL | Could | The system shall provide order status tracking (Received, Accepted, Preparing, Ready, Out for Delivery, Comple… | Not started | AT-ONL-01 |
| FR-ONL-010 | ONL | Could | The system shall show order history to signed-in customers for their own orders only. | Not started | AT-ONL-01 |
| FR-ONL-011 | ONL | Could | The system shall allow staff to accept or reject online orders (or auto-accept by configuration) and send acce… | Not started | AT-ONL-107 |
| FR-ONL-012 | ONL | Could | The system shall protect public endpoints with rate limiting, input validation, bot protection when abuse is d… | Not started | AT-ONL-03 |
| FR-ONL-013 | ONL | Could | The system shall support QR table ordering in which a table-specific QR code opens the menu and creates or add… | Not started | AT-ONL-108 |
| FR-ONL-014 | ONL | Could | The system shall allow managers to pause and resume online ordering per branch. | Not started | AT-ONL-109 |
