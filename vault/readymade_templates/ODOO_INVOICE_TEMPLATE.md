---
type: odoo_invoice
status: approved
customer_name: Farral
invoice_date: '2026-03-05'
lines:
- product: website
  quantity: 1
  price_unit: 1000.0
approved_at: '2026-03-05'
---
# Invoice Review

**Customer**: Farral
**Date**: 2026-03-05

## Line Items

- website x 1 @ $1000.00

**Estimated Total**: $1000.00

---
## How to use:
## 1. Copy this file to vault/Approved/
## 2. Rename it to ODOO_INVOICE_<date>_<name>.md
## 3. Replace all CHANGE_ME with your values
## 4. Run: uv run python -m backend.orchestrator
## 5. Customer is auto-created in Odoo if not exists
## 6. File moves to vault/Done/ when processed
