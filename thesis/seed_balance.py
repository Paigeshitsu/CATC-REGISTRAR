import os
import django
import random
from decimal import Decimal

# 1. Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thesis.settings') 
django.setup()

from requests_app.models import StudentMasterList, StudentBalance

def seed_random_balances(n=50):
    print(f"Fetching students from Master List...")
    all_students = list(StudentMasterList.objects.all())

    if not all_students:
        print("Error: No students found in Master List. Run seed_students.py first!")
        return

    # If there are fewer than 50 students, just use all of them
    count_to_seed = min(n, len(all_students))
    
    # Pick n random unique students
    selected_students = random.sample(all_students, count_to_seed)

    print(f"Starting to seed balances for {count_to_seed} students...")

    created_count = 0
    updated_count = 0

    for student in selected_students:
        # Generate a random amount between 500.00 and 15,000.00
        random_amount = Decimal(random.randrange(500, 15000))
        
        # Use get_or_create to avoid duplicates if the script is run twice
        balance_record, created = StudentBalance.objects.get_or_create(
            student=student,
            defaults={'outstanding_amount': random_amount}
        )

        if not created:
            # If record already existed, update it with a new random amount
            balance_record.outstanding_amount = random_amount
            balance_record.save()
            updated_count += 1
        else:
            created_count += 1

    print(f"Success!")
    print(f"- New balance records created: {created_count}")
    print(f"- Existing records updated: {updated_count}")
    print(f"- Total students processed: {count_to_seed}")

if __name__ == "__main__":
    seed_random_balances(50)