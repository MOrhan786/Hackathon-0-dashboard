"""Odoo Invoice Auto-Creation Module"""

import xmlrpc.client
import os
from typing import Optional, Dict, Any

class OdooInvoiceClient:
    """Client for creating invoices in Odoo via XML-RPC"""
    
    def __init__(self):
        self.url = os.getenv("ODOO_URL", "http://localhost:8069")
        self.db = os.getenv("ODOO_DATABASE", "ai_employee")
        self.username = os.getenv("ODOO_USERNAME", "admin@example.com")
        self.password = os.getenv("ODOO_PASSWORD", "admin")
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        self.uid = None
        
    def authenticate(self) -> bool:
        """Authenticate with Odoo"""
        try:
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            return self.uid > 0
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False
    
    def create_customer(self, name: str, email: str = "", phone: str = "") -> Optional[int]:
        """Create a new customer in Odoo"""
        if not self.uid:
            if not self.authenticate():
                return None
        
        try:
            # Check if customer already exists
            existing = self.models.execute_kw(
                self.db, self.uid, self.password,
                "res.partner", "search",
                [[["name", "=", name]]]
            )
            
            if existing:
                print(f"Customer {name} already exists with ID: {existing[0]}")
                return existing[0]
            
            # Create new customer
            customer_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                "res.partner", "create",
                [{
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "customer_rank": 1,
                }]
            )
            print(f"Customer {name} created with ID: {customer_id}")
            return customer_id
        except Exception as e:
            print(f"Error creating customer: {e}")
            return None
    
    def get_customer(self, name: str) -> Optional[int]:
        """Get customer ID by name"""
        if not self.uid:
            if not self.authenticate():
                return None
        
        try:
            customers = self.models.execute_kw(
                self.db, self.uid, self.password,
                "res.partner", "search",
                [[["name", "=", name]]]
            )
            return customers[0] if customers else None
        except Exception as e:
            print(f"Error finding customer: {e}")
            return None
    
    def get_journal(self, journal_type: str = "sale") -> Optional[int]:
        """Get sales journal ID"""
        try:
            journals = self.models.execute_kw(
                self.db, self.uid, self.password,
                "account.journal", "search",
                [[["type", "=", journal_type]]]
            )
            return journals[0] if journals else None
        except Exception as e:
            print(f"Error finding journal: {e}")
            return None
    
    def create_invoice(self, customer_id: int, items: list, invoice_date: str = None) -> Optional[Dict[str, Any]]:
        """Create invoice in Odoo"""
        if not self.uid:
            if not self.authenticate():
                return None
        
        try:
            journal_id = self.get_journal("sale")
            if not journal_id:
                print("Sales journal not found!")
                return None
            
            # Calculate total
            total = sum(item.get("quantity", 1) * item.get("price_unit", 0) for item in items)
            
            # Create invoice
            invoice_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                "account.move", "create",
                [{
                    "move_type": "out_invoice",
                    "partner_id": customer_id,
                    "journal_id": journal_id,
                    "invoice_date": invoice_date,
                    "invoice_line_ids": [
                        (0, 0, {
                            "name": item.get("description", "Service"),
                            "quantity": item.get("quantity", 1),
                            "price_unit": item.get("price_unit", 0),
                        })
                        for item in items
                    ],
                }]
            )
            
            print(f"Invoice created with ID: {invoice_id}")
            
            # Get invoice number
            invoice = self.models.execute_kw(
                self.db, self.uid, self.password,
                "account.move", "read",
                [invoice_id, ["name", "amount_total", "state"]]
            )
            
            return {
                "id": invoice_id,
                "number": invoice[0].get("name", "N/A"),
                "total": invoice[0].get("amount_total", total),
                "state": invoice[0].get("state", "draft"),
            }
        except Exception as e:
            print(f"Error creating invoice: {e}")
            return None
    
    def post_invoice(self, invoice_id: int) -> bool:
        """Post/Confirm invoice"""
        try:
            self.models.execute_kw(
                self.db, self.uid, self.password,
                "account.move", "action_post",
                [[invoice_id]]
            )
            print(f"Invoice {invoice_id} posted successfully!")
            return True
        except Exception as e:
            print(f"Error posting invoice: {e}")
            return False


def create_invoice_from_draft(draft_data: dict) -> dict:
    """Create invoice from draft data"""
    client = OdooInvoiceClient()
    
    result = {
        "success": False,
        "customer_id": None,
        "invoice": None,
        "message": "",
    }
    
    # Authenticate
    if not client.authenticate():
        result["message"] = "Failed to authenticate with Odoo"
        return result
    
    # Get or create customer
    customer_name = draft_data.get("customer", "Unknown")
    customer_email = draft_data.get("customer_email", "")
    
    customer_id = client.get_customer(customer_name)
    if not customer_id:
        customer_id = client.create_customer(customer_name, customer_email)
    
    if not customer_id:
        result["message"] = f"Failed to create/find customer: {customer_name}"
        return result
    
    result["customer_id"] = customer_id
    
    # Create invoice
    items = draft_data.get("items", [])
    invoice_date = draft_data.get("created_at", "")[:10] if draft_data.get("created_at") else None
    
    invoice = client.create_invoice(customer_id, items, invoice_date)
    
    if not invoice:
        result["message"] = "Failed to create invoice"
        return result
    
    # Post invoice
    if client.post_invoice(invoice["id"]):
        invoice["state"] = "posted"
    
    result["invoice"] = invoice
    result["success"] = True
    result["message"] = f"Invoice {invoice[number]} created successfully!"
    
    return result


if __name__ == "__main__":
    # Test
    test_data = {
        "customer": "Test Customer",
        "customer_email": "test@example.com",
        "items": [
            {"description": "Test Service", "quantity": 1, "price_unit": 1000},
        ],
    }
    result = create_invoice_from_draft(test_data)
    print(f"Result: {result}")


# Dashboard API Integration
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import yaml
from pathlib import Path

invoice_router = APIRouter()

@invoice_router.post("/api/invoice/approve")
async def approve_invoice(req: dict) -> JSONResponse:
    """Approve invoice draft and create in Odoo"""
    filename = req.get("filename", "")
    vault_path = Path(req.get("vault_path", "./vault"))
    
    # Read invoice draft
    draft_file = vault_path / "Pending_Approval" / filename
    if not draft_file.exists():
        return JSONResponse(content={"success": False, "message": f"File not found: {filename}"})
    
    # Parse frontmatter
    content = draft_file.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return JSONResponse(content={"success": False, "message": "Invalid frontmatter format"})
    
    try:
        frontmatter = yaml.safe_load(parts[1])
    except Exception as e:
        return JSONResponse(content={"success": False, "message": f"Failed to parse frontmatter: {e}"})
    
    # Check if it is an invoice request
    if frontmatter.get("type") != "invoice_request":
        return JSONResponse(content={"success": False, "message": "Not an invoice request"})
    
    # Create invoice in Odoo
    result = create_invoice_from_draft(frontmatter)
    
    if result["success"]:
        # Move file to Done/
        done_dir = vault_path / "Done"
        done_dir.mkdir(parents=True, exist_ok=True)
        draft_file.rename(done_dir / filename)
        
        # Update frontmatter
        done_file = done_dir / filename
        done_content = done_file.read_text(encoding="utf-8")
        parts = done_content.split("---", 2)
        frontmatter["status"] = "approved"
        frontmatter["odoo_invoice"] = result["invoice"]["number"] if result["invoice"] else "N/A"
        new_content = f"---\n{yaml.dump(frontmatter)}---\n{parts[2]}"
        done_file.write_text(new_content, encoding="utf-8")
        
        return JSONResponse(content={
            "success": True,
            "message": result["message"],
            "invoice": result["invoice"],
            "customer_id": result["customer_id"],
        })
    else:
        return JSONResponse(content={
            "success": False,
            "message": result["message"],
        })
