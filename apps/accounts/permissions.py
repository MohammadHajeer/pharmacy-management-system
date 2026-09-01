"""Approved PHARMANEX capabilities exposed by the role-permission workspace."""

from collections import OrderedDict


OWNER_ROLE = "Owner / Admin"
OPERATIONAL_ROLES = ("Pharmacist", "Inventory Manager", "Accountant")
BUSINESS_ROLES = (OWNER_ROLE, *OPERATIONAL_ROLES)


PERMISSION_GROUPS = OrderedDict(
    (
        (
            "Catalog",
            (
                ("catalog.view_medicine", "View medicines", "Search and inspect medicine records."),
                ("catalog.add_medicine", "Add medicines", "Create medicine definitions and their base units."),
                ("catalog.change_medicine", "Change medicines", "Edit medicine selling and clinical configuration."),
                ("catalog.view_category", "View categories", "Inspect medicine categories."),
                ("catalog.add_category", "Add categories", "Create medicine categories."),
                ("catalog.change_category", "Change categories", "Edit or deactivate medicine categories."),
                ("catalog.view_manufacturer", "View manufacturers", "Inspect manufacturer records."),
                ("catalog.add_manufacturer", "Add manufacturers", "Create manufacturer records."),
                ("catalog.change_manufacturer", "Change manufacturers", "Edit or deactivate manufacturers."),
                ("catalog.add_medicineunit", "Add medicine units", "Configure purchasing and selling units."),
                ("catalog.change_medicineunit", "Change medicine units", "Edit or deactivate medicine units."),
                ("catalog.add_medicinebarcode", "Add barcodes", "Register medicine unit barcodes."),
                ("catalog.change_medicinebarcode", "Change barcodes", "Edit or deactivate registered barcodes."),
            ),
        ),
        (
            "Inventory",
            (
                ("inventory.view_medicinebatch", "View medicine batches", "Inspect available batch stock and expiry dates."),
                ("inventory.view_stockmovement", "View stock movements", "Inspect the immutable stock movement history."),
            ),
        ),
        (
            "Suppliers",
            (
                ("parties.view_supplier", "View suppliers", "Search and inspect supplier records."),
                ("parties.add_supplier", "Add suppliers", "Create supplier records."),
                ("parties.change_supplier", "Change suppliers", "Edit or deactivate suppliers."),
            ),
        ),
        (
            "Customers",
            (
                ("parties.view_customer", "View customers", "Search and inspect customer records."),
                ("parties.add_customer", "Add customers", "Create customer records for sales and balances."),
                ("parties.change_customer", "Change customers", "Edit or deactivate customers."),
            ),
        ),
        (
            "Prescriptions",
            (
                ("prescriptions.view_prescription", "View prescriptions", "Inspect stored prescription records."),
                ("prescriptions.add_prescription", "Add prescriptions", "Create prescription records."),
                ("prescriptions.change_prescription", "Change prescriptions", "Edit prescription records."),
                ("prescriptions.view_prescriptionitem", "View prescription items", "Inspect prescribed medicine lines."),
                ("prescriptions.add_prescriptionitem", "Add prescription items", "Add medicine lines to prescriptions."),
                ("prescriptions.change_prescriptionitem", "Change prescription items", "Edit prescribed medicine lines."),
            ),
        ),
        (
            "Purchasing",
            (
                ("purchasing.view_purchaseinvoice", "View purchases", "Search and inspect purchase invoices."),
                ("purchasing.add_purchaseinvoice", "Create purchases", "Create draft purchase invoices."),
                ("purchasing.change_purchaseinvoice", "Change purchases", "Edit draft purchase invoices."),
                ("purchasing.view_purchaseinvoiceline", "View purchase lines", "Inspect purchase invoice lines."),
                ("purchasing.add_purchaseinvoiceline", "Add purchase lines", "Add medicines to draft purchases."),
                ("purchasing.change_purchaseinvoiceline", "Change purchase lines", "Edit draft purchase lines."),
                ("purchasing.post_purchaseinvoice", "Post purchase", "Receive a purchase invoice and increase inventory."),
            ),
        ),
        (
            "Sales",
            (
                ("sales.view_salesinvoice", "View sales", "Search and inspect sales invoices."),
                ("sales.add_salesinvoice", "Create sales", "Open draft point-of-sale transactions."),
                ("sales.change_salesinvoice", "Change sales", "Edit draft point-of-sale transactions."),
                ("sales.view_salesinvoiceline", "View sale lines", "Inspect medicines recorded on sales."),
                ("sales.add_salesinvoiceline", "Add sale lines", "Add medicines to draft sales."),
                ("sales.change_salesinvoiceline", "Change sale lines", "Edit medicines on draft sales."),
                ("sales.complete_sale", "Complete sale", "Finalize a sale and allocate FEFO stock."),
                ("sales.view_salebatchallocation", "View sale allocations", "Inspect the batches allocated to completed sales."),
            ),
        ),
        (
            "Payments / Finance",
            (
                ("finance.view_customerpayment", "View customer payments", "Inspect customer payment records."),
                ("finance.post_customerpayment", "Post customer payment", "Record or reverse payments against customer invoices."),
                ("finance.view_supplierpayment", "View supplier payments", "Inspect supplier payment records."),
                ("finance.post_supplierpayment", "Post supplier payment", "Record or reverse payments against purchase invoices."),
                ("finance.view_financial_reports", "View financial reports", "Access protected financial reporting."),
            ),
        ),
        (
            "Returns & Refunds",
            (
                ("returns.view_customerreturn", "View customer returns", "Inspect customer return records."),
                ("returns.add_customerreturn", "Create customer returns", "Create customer return records."),
                ("returns.change_customerreturn", "Change customer returns", "Edit draft customer returns."),
                ("returns.post_customerreturn", "Post customer return", "Finalize a customer return and approved restocking."),
                ("returns.process_refund", "Process refund", "Post a refund linked to a customer return."),
                ("returns.view_supplierreturn", "View supplier returns", "Inspect supplier return records."),
                ("returns.add_supplierreturn", "Create supplier returns", "Create supplier return records."),
                ("returns.change_supplierreturn", "Change supplier returns", "Edit draft supplier returns."),
                ("returns.post_supplierreturn", "Post supplier return", "Finalize a supplier return and reduce exact batch stock."),
            ),
        ),
        (
            "Settings",
            (
                ("core.change_pharmacysettings", "Change pharmacy settings", "Manage pharmacy identity and default configuration."),
                ("core.add_taxrate", "Add tax rates", "Create tax configurations."),
                ("core.change_taxrate", "Change tax rates", "Edit or deactivate tax configurations."),
                ("core.add_paymentmethod", "Add payment methods", "Create accepted payment methods."),
                ("core.change_paymentmethod", "Change payment methods", "Edit or deactivate payment methods."),
            ),
        ),
        (
            "Staff Administration",
            (
                ("auth.view_user", "View staff accounts", "Inspect staff identity, role, status, and activity."),
                ("auth.add_user", "Add staff accounts", "Create PHARMANEX staff accounts."),
                ("auth.change_user", "Change staff accounts", "Edit access, status, and passwords for staff."),
                ("auth.view_group", "View roles and permissions", "Inspect PHARMANEX business role capabilities."),
                ("auth.change_group", "Change role permissions", "Update approved capabilities for operational roles."),
            ),
        ),
    )
)


APPROVED_PERMISSION_NAMES = frozenset(
    permission
    for capabilities in PERMISSION_GROUPS.values()
    for permission, _label, _description in capabilities
)
OPERATIONAL_PERMISSION_NAMES = frozenset(
    name for name in APPROVED_PERMISSION_NAMES if not name.startswith("auth.")
)


ROLE_SLUGS = {
    "owner": OWNER_ROLE,
    "pharmacist": "Pharmacist",
    "inventory-manager": "Inventory Manager",
    "accountant": "Accountant",
}
ROLE_TO_SLUG = {name: slug for slug, name in ROLE_SLUGS.items()}
