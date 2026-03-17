---
type: invoice_request
customer: Sadoon
customer_email: sadoon@example.com
status: approved
created_at: 2026-03-16 12:30:00+00:00
priority: high
items:
- description: Website Design Service
  quantity: 1
  price_unit: 50000
  percentage: 40
- description: UI/UX Design
  quantity: 2
  price_unit: 25000
  percentage: 33
- description: Consultation Hours
  quantity: 5
  price_unit: 10000
  percentage: 27
total_amount: 150000
currency: PKR
payment_terms: 30 days
notes: Thank you for your business!
---
## Invoice Request for Sadoon

**Customer:** Sadoon (sadoon@example.com)

**Items:**

| Description | Quantity | Price | Percentage | Total |
|-------------|----------|-------|------------|-------|
| Website Design Service | 1 | 50,000 PKR | 40% | 50,000 PKR |
| UI/UX Design | 2 | 25,000 PKR | 33% | 50,000 PKR |
| Consultation Hours | 5 | 10,000 PKR | 27% | 50,000 PKR |

**Total Amount:** 150,000 PKR

**Payment Terms:** 30 days

**Notes:** Thank you for your business!

---

## AI Actions (On Approve):

- [ ] Create customer "Sadoon" in Odoo (if not exists)
- [ ] Create invoice in Odoo
- [ ] Select customer: Sadoon
- [ ] Add invoice lines with quantity, price, percentage
- [ ] Post invoice
- [ ] Move file to Done/

