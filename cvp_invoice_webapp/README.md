# CVP Project Billing & Invoice Management

A Streamlit web application based on the handwritten workflow and tax-invoice sample supplied by the user.

## Main modules
1. Company / Admin setup
2. Client & Project registration
3. P.O. / Work Order details
4. Configurable project milestones with service details, milestone name, due date, taxable value, tax invoice number, and payment status
5. Proforma Invoice / Tax Invoice
6. Self-generated invoice number
7. GST calculation (IGST or CGST + SGST)
8. PDF invoice/report in the structure of the supplied sample
9. Invoice register
10. Local SQLite database

## Run in VS Code / PowerShell
```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The database file `cvp_invoice.db` is created automatically on the first run.
