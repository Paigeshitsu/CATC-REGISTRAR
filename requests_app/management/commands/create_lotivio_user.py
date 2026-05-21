from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Creates the Lotivio staff user for TOR page counting'

    def handle(self, *args, **options):
        username = 'Lotivio01'
        password = 'yoshimitsu69'
        
        # Create TOR Desk group if it doesn't exist
        tor_group, created = Group.objects.get_or_create(name='TOR Desk')
        if created:
            self.stdout.write(self.style.SUCCESS('Created TOR Desk group'))
        
        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
            user.set_password(password)
            user.is_staff = True
            user.save()
            user.groups.add(tor_group)
            self.stdout.write(self.style.SUCCESS(f'Updated user: {username}'))
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                is_staff=True,
                first_name='Mr.',
                last_name='Lotivio'
            )
            user.groups.add(tor_group)
            self.stdout.write(self.style.SUCCESS(f'Created new staff user: {username}'))
        
        self.stdout.write(self.style.SUCCESS(f''))
        self.stdout.write(self.style.SUCCESS(f'=== LOGIN CREDENTIALS ==='))
        self.stdout.write(self.style.SUCCESS(f'Username: {username}'))
        self.stdout.write(self.style.SUCCESS(f'Password: {password}'))
        self.stdout.write(self.style.SUCCESS(f''))
        self.stdout.write(self.style.SUCCESS(f'Go to: /staff/login/'))
