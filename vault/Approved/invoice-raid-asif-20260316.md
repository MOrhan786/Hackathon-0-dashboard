---
type: invoice_request
customer: Raid Asif
customer_email: raid.asif@example.com
status: approved
created_at: 2026-03-16 18:00:00+00:00
priority: high
items:
- description: Website Development
  quantity: 1
  price_unit: 75000
  percentage: 37.5
- description: Mobile App Design
  quantity: 1
  price_unit: 50000
  percentage: 25
- description: SEO Services
  quantity: 3
  price_unit: 25000
  percentage: 37.5
total_amount: 200000
currency: PKR
payment_terms: 30 days
notes: Thank you for your business!
---
## Invoice Request for Raid Asif

**Customer:** Raid Asif (raid.asif@example.com)

**Items:**

| Description | Quantity | Price | Percentage | Total |
|-------------|----------|-------|------------|-------|
| Website Development | 1 | 75,000 PKR | 37.5% | 75,000 PKR |
| Mobile App Design | 1 | 50,000 PKR | 25% | 50,000 PKR |
| SEO Services | 3 | 25,000 PKR | 37.5% | 75,000 PKR |

**Total Amount:** 200,000 PKR

**Payment Terms:** 30 days

**Notes:** Thank you for your business!

---

## AI Actions (On Approve):

- [ ] Create customer "Raid Asif" in Odoo (if not exists)
- [ ] Create invoice in Odoo
- [ ] Select customer: Raid Asif
- [ ] Add invoice lines with quantity, price, percentage
- [ ] Post invoice
- [ ] Move file to Done/

