from django.core.management.base import BaseCommand
from api.models import FaceVector, AnonymousFaceVector

class Command(BaseCommand):
    help = 'Delete face vectors based on criteria'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Delete all face vectors')
        parser.add_argument('--unknown', action='store_true', help='Delete only unknown faces')
        parser.add_argument('--user-id', type=str, help='Delete faces for specific user')
        parser.add_argument('--older-than', type=int, help='Delete faces older than X days')

    def handle(self, *args, **options):
        if options['all']:
            face_count = FaceVector.objects.count()
            anon_count = AnonymousFaceVector.objects.count()
            FaceVector.objects.all().delete()
            AnonymousFaceVector.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {face_count} face vectors and {anon_count} anonymous face vectors'))
            
        elif options['unknown']:
            anon_count = AnonymousFaceVector.objects.count()
            AnonymousFaceVector.objects.all().delete()
            no_user_count = FaceVector.objects.filter(user__isnull=True).count()
            FaceVector.objects.filter(user__isnull=True).delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {anon_count} anonymous face vectors and {no_user_count} unassigned face vectors'))
            
        elif options['user_id']:
            count = FaceVector.objects.filter(user_id=options['user_id']).count()
            FaceVector.objects.filter(user_id=options['user_id']).delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {count} face vectors for user {options["user_id"]}'))
            
        elif options['older_than']:
            import datetime
            from django.utils import timezone
            cutoff_date = timezone.now() - datetime.timedelta(days=options['older_than'])
            
            face_count = FaceVector.objects.filter(created_at__lt=cutoff_date).count()
            FaceVector.objects.filter(created_at__lt=cutoff_date).delete()
            
            anon_count = AnonymousFaceVector.objects.filter(created_at__lt=cutoff_date).count()
            AnonymousFaceVector.objects.filter(created_at__lt=cutoff_date).delete()
            
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {face_count} face vectors and {anon_count} anonymous face vectors older than {options["older_than"]} days'
            ))
        else:
            self.stdout.write(self.style.WARNING('No action specified. Use --all, --unknown, --user-id, or --older-than'))