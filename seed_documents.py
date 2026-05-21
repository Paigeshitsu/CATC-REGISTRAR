import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thesis.settings')
django.setup()

from requests_app.models import DocumentType

def seed():
    docs = [
        # --- SCHOLASTIC RECORDS (Base Documents) ---
        ("Diploma", 150.00),
        ("Transcript of Records", 100.00),
        ("Honorable Dismissal", 80.00),
        ("Certification of Grades", 80.00),
        ("Certification of Good Moral", 80.00),
        ("Certification of Units Earned", 80.00),
        ("Certification of General Weighted Average (GWA)", 80.00),
        ("Certificate of Enrollment (Junior/Senior HS)", 80.00),
        ("Certificate of Enrollment (College Dept)", 80.00),
        ("Form 137/138", 150.00),
        ("Clearance (High School & College Dept)", 100.00),
        
        # --- AUTHENTICATIONS (Paired specifically to the names above) ---
        # Note: Names are standardized as "Authentication - [Base Name]" 
        # so the Dropdown logic in views.py finds them easily.
        ("Authentication - Diploma", 40.00),
        ("Authentication - Transcript of Records", 40.00),
        ("Authentication - Honorable Dismissal", 40.00),
        ("Authentication - Certification of Grades", 40.00),
        ("Authentication - Certification of Good Moral", 40.00),
        ("Authentication - Certification of Units Earned", 40.00),
        ("Authentication - Certification of General Weighted Average (GWA)", 40.00),
        ("Authentication - Certificate of Enrollment (Junior/Senior HS)", 40.00),
        ("Authentication - Certificate of Enrollment (College Dept)", 40.00),
        ("Authentication - Form 137/138", 40.00),
        ("Authentication - Clearance (High School & College Dept)", 40.00),

        # --- SPECIAL CATEGORIES / MISC ---
        ("Authentication - True Copy of Special Order", 40.00),
        ("Authentication - School ID", 40.00),
        ("Authentication - White Form", 40.00),
        ("Authentication - Printing of Grades (College Dept)", 20.00),
        ("Authentication - for BU Application Form (PIS)", 40.00),
        ("Authentication - for CHED/TES documents", 50.00),
    ]

    print("Clearing old document types to prevent duplicates...")
    DocumentType.objects.all().delete()

    for name, price in docs:
        DocumentType.objects.create(name=name, price=price)
        
    print(f"Successfully seeded {len(docs)} document types!")
    print("Base documents and Authentication pairs are now standardized.")

if __name__ == "__main__":
    seed()