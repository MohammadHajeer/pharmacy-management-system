"""Stable, fictional UI fixtures. Not clinical, legal, or pricing reference data.

Keep identities stable when changing display copy. There is deliberately no
random seed option: a different seed must not create another shared dataset.
No database writes or historical-import API live in this module.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5


NAMESPACE = UUID("a3183b65-537a-4db5-b1a2-7f3f672da5ab")
MARKER = "PHARMANEX-DEMO-V1"
CATEGORIES = (
    "Analgesics", "Antibiotics", "Antihistamines", "Gastrointestinal",
    "Cardiovascular", "Diabetes", "Respiratory", "Vitamins & Supplements",
    "Dermatology", "Ophthalmic", "Antifungal", "Antiseptic", "Cold & Flu",
    "Neurology", "Electrolytes", "Musculoskeletal", "Ear Care", "Miscellaneous",
)
MANUFACTURERS = (
    "Cedar Vale Pharma", "Northbridge Laboratories", "Olive Grove Therapeutics",
    "Silverleaf Healthcare", "Marina Life Sciences", "Bluehaven Pharma",
    "Summit Formulations", "Orchard Biologics", "Clearwater Laboratories",
    "Amberfield Pharma", "Oakwell Healthcare", "Meadowbrook Remedies",
    "Lighthouse Formulations", "Willowcrest Pharma", "Stonebridge Labs",
    "Pinehill Therapeutics", "Sunridge Healthcare", "Riverbend Pharma",
    "Westhaven Laboratories", "Aster Valley Pharma", "Juniper Life Sciences",
    "Harborstone Healthcare", "Linden Legacy Labs", "Brookfield Archive Pharma",
)
SUPPLIERS = (
    "Cedar Distribution", "Harbor Medical Supply", "Valley Wholesale",
    "Orchard Health Logistics", "Summit Pharmacy Supply", "Riverbend Distribution",
)

# Category index, generic label, two strengths, dosage form. Each concept has
# two fictional products. Prescription flags below are development metadata.
CONCEPTS = (
    (0, "Paracetamol", "500 mg", "650 mg", "Tablet"),
    (0, "Ibuprofen", "200 mg", "400 mg", "Tablet"),
    (0, "Aspirin", "75 mg", "100 mg", "Tablet"),
    (15, "Diclofenac", "25 mg", "50 mg", "Tablet"),
    (15, "Naproxen", "250 mg", "500 mg", "Tablet"),
    (1, "Amoxicillin", "250 mg", "500 mg", "Capsule"),
    (1, "Azithromycin", "250 mg", "500 mg", "Tablet"),
    (1, "Doxycycline", "50 mg", "100 mg", "Capsule"),
    (1, "Cefalexin", "250 mg", "500 mg", "Capsule"),
    (1, "Metronidazole", "250 mg", "500 mg", "Tablet"),
    (2, "Cetirizine", "5 mg", "10 mg", "Tablet"),
    (2, "Loratadine", "5 mg", "10 mg", "Tablet"),
    (2, "Fexofenadine", "120 mg", "180 mg", "Tablet"),
    (3, "Omeprazole", "10 mg", "20 mg", "Capsule"),
    (3, "Pantoprazole", "20 mg", "40 mg", "Tablet"),
    (3, "Famotidine", "20 mg", "40 mg", "Tablet"),
    (5, "Metformin", "500 mg", "850 mg", "Tablet"),
    (5, "Gliclazide", "30 mg", "60 mg", "Tablet"),
    (4, "Amlodipine", "5 mg", "10 mg", "Tablet"),
    (4, "Losartan", "25 mg", "50 mg", "Tablet"),
    (4, "Atorvastatin", "10 mg", "20 mg", "Tablet"),
    (4, "Bisoprolol", "2.5 mg", "5 mg", "Tablet"),
    (4, "Enalapril", "5 mg", "10 mg", "Tablet"),
    (7, "Vitamin C", "250 mg", "500 mg", "Tablet"),
    (7, "Vitamin D3", "400 IU", "1000 IU", "Capsule"),
    (7, "Zinc", "10 mg", "20 mg", "Tablet"),
    (13, "Gabapentin", "100 mg", "300 mg", "Capsule"),
    (13, "Levetiracetam", "250 mg", "500 mg", "Tablet"),
    (6, "Montelukast", "5 mg", "10 mg", "Tablet"),
    (12, "Guaifenesin", "200 mg", "400 mg", "Tablet"),
    (0, "Paracetamol", "120 mg/5 mL", "250 mg/5 mL", "Suspension"),
    (0, "Ibuprofen", "100 mg/5 mL", "200 mg/5 mL", "Suspension"),
    (1, "Amoxicillin", "125 mg/5 mL", "250 mg/5 mL", "Suspension"),
    (1, "Cefalexin", "125 mg/5 mL", "250 mg/5 mL", "Suspension"),
    (2, "Cetirizine", "1 mg/mL", "5 mg/5 mL", "Oral solution"),
    (3, "Lactulose", "3.335 g/5 mL", "10 g/15 mL", "Oral solution"),
    (12, "Guaifenesin", "100 mg/5 mL", "200 mg/5 mL", "Syrup"),
    (12, "Dextromethorphan", "10 mg/5 mL", "15 mg/5 mL", "Syrup"),
    (6, "Salbutamol", "100 mcg/dose", "200 mcg/dose", "Inhaler"),
    (6, "Budesonide", "100 mcg/dose", "200 mcg/dose", "Inhaler"),
    (8, "Hydrocortisone", "0.5%", "1%", "Cream"),
    (10, "Clotrimazole", "1%", "2%", "Cream"),
    (10, "Miconazole", "2% / 15 g", "2% / 30 g", "Cream"),
    (15, "Diclofenac", "1%", "2%", "Gel"),
    (8, "Dexpanthenol", "5% / 20 g", "5% / 50 g", "Ointment"),
    (11, "Povidone iodine", "5%", "10%", "Topical solution"),
    (11, "Chlorhexidine", "0.05%", "0.2%", "Topical solution"),
    (9, "Artificial tears", "0.2%", "0.3%", "Eye drops"),
    (9, "Sodium hyaluronate", "0.1%", "0.2%", "Eye drops"),
    (16, "Carbamide peroxide", "6.5% / 10 mL", "6.5% / 15 mL", "Ear drops"),
    (14, "Oral rehydration salts", "4.1 g", "20.5 g", "Powder"),
    (3, "Macrogol", "6.9 g", "13.8 g", "Powder"),
    (7, "Vitamin C", "500 mg", "1000 mg", "Powder"),
    (14, "Sodium chloride", "0.9% / 5 mL", "0.9% / 10 mL", "Injection"),
    (7, "Cyanocobalamin", "500 mcg/mL", "1000 mcg/mL", "Injection"),
    (1, "Ceftriaxone", "500 mg", "1 g", "Powder for injection"),
    (5, "Insulin demo blend", "100 units/mL / 3 mL", "100 units/mL / 10 mL", "Injection vial"),
    (8, "Zinc oxide", "10%", "20%", "Cream"),
    (17, "Barrier balm", "15 g", "30 g", "Ointment"),
    (17, "Saline rinse", "0.9% / 100 mL", "0.9% / 250 mL", "Topical solution"),
)
BASE_NAMES = {
    "Suspension": "Bottle", "Oral solution": "Bottle", "Syrup": "Bottle",
    "Inhaler": "Inhaler", "Cream": "Tube", "Gel": "Tube", "Ointment": "Tube",
    "Topical solution": "Bottle", "Eye drops": "Bottle", "Ear drops": "Bottle",
    "Powder": "Sachet", "Injection": "Ampoule", "Powder for injection": "Vial",
    "Injection vial": "Vial",
}


def identity(kind, key):
    return uuid5(NAMESPACE, f"{kind}:{key}")


def unit_specs(index):
    form = CONCEPTS[index // 2][4]
    base = BASE_NAMES.get(form, form)
    result = [(base, Decimal("1.000000"))]
    if index % 5:
        if form in ("Tablet", "Capsule"):
            result.append(("Strip of 10", Decimal("10.000000")))
        else:
            result.append((f"Pack of 6 {base.lower()}s", Decimal("6.000000")))
    if index % 5 == 4 and form in ("Tablet", "Capsule"):
        result.append(("Box of 20", Decimal("20.000000")))
    return result


def barcode_value(index, slot):
    # Synthetic 13-digit strings with a check digit, never commercial IDs.
    body = f"299{index:07d}{slot:02d}"
    checksum = sum(int(digit) * (1 if n % 2 == 0 else 3) for n, digit in enumerate(body))
    return body + str((-checksum) % 10)


def has_barcode(index, slot):
    return slot == 0 or (slot == 1 and index % 3 != 0)


def stock_rank(index):
    # Permute to spread scenarios across dosage forms and active/inactive rows.
    return (index * 37) % 120


def threshold(index):
    values = (20, 50, 100) if index < 60 else (10, 20, 50)
    return Decimal(values[index % 3]).quantize(Decimal("0.001"))


@dataclass(frozen=True)
class Receipt:
    medicine_index: int
    slot: int
    quantity_base: Decimal
    expiry_days: int
    lot_slot: int

    @property
    def key(self):
        return f"{self.medicine_index}:{self.slot}"


def receipt_specs():
    receipts = []
    for index in range(120):
        rank = stock_rank(index)
        limit = threshold(index)
        rows = []
        if rank < 70:
            early = 120 + (rank * 7) % 240
            later = 780 + rank if rank % 5 == 0 else 365 + rank * 4
            # Two acquisition-cost layers of the exact same lot/expiry.
            rows = [(limit * 3, early, 0), (limit * 4, early if rank == 0 else later, 0 if rank == 0 else 1)]
            if rank < 10:
                rows.append((limit, -(1 + rank * 43) if rank < 4 else 700 + rank, 2))
        elif rank < 91:
            rows = [(limit if rank % 3 == 0 else limit / 2, 180 + rank, 0)]
        elif rank < 102:
            pass  # Catalog-only: no fabricated zero-quantity receipts.
        elif rank < 116:
            rows = [(limit, (rank - 102) * 2, 0), (limit * 3, 31 + (rank - 102) * 4, 1)]
        else:
            rows = [(limit / 2, -(30 + (rank - 116) * 50), 0)]
        receipts.extend(
            Receipt(index, slot, quantity.quantize(Decimal("0.001")), days, lot)
            for slot, (quantity, days, lot) in enumerate(rows)
        )
    return receipts


def invoice_groups():
    # 23 deliveries, six suppliers, 5–9 lines each; related catalog entries
    # stay together rather than making a single enormous opening invoice.
    receipts = receipt_specs()
    return [receipts[start:start + 9] for start in range(0, len(receipts), 9)]
