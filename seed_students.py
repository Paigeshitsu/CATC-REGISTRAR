import os
import django
import random

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thesis.settings') 
django.setup()

from requests_app.models import StudentMasterList

def generate_students(n=100):
    # Simplified list of courses
    courses = ['BSIT', 'BSCS', 'BSBA', 'BSCrim']

    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", 
                   "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
                   "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa"]
    
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", 
                  "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas"]

    print(f"Starting to seed {n} students...")

    count = 0
    start_id = 100001 

    while count < n:
        sid = f"S{start_id + count:06d}"
        
        if StudentMasterList.objects.filter(student_id=sid).exists():
            start_id += 1
            continue

        fname = random.choice(first_names)
        lname = random.choice(last_names)
        full_name = f"{fname} {lname}"
        
        email = f"{fname.lower()}.{lname.lower()}{random.randint(10,99)}@example.edu"
        phone = f"09{random.randint(100000000, 999999999)}"
        
        # --- LOGIC FOR COURSE AND MAJOR ---
        course_name = random.choice(courses)
        
        if course_name == 'BSBA':
            major_name = "Marketing"
        else:
            major_name = "" # No major for other courses
        # ----------------------------------

        try:
            StudentMasterList.objects.create(
                student_id=sid,
                full_name=full_name,
                course=course_name,
                major=major_name,
                email=email,
                phone_number=phone
            )
            count += 1
            if count % 10 == 0:
                print(f"Created {count} students...")
        except Exception as e:
            # Skip if email accidentally duplicates
            continue

    print(f"Success! {n} random students added to the Master List.")

if __name__ == "__main__":
    generate_students(100)