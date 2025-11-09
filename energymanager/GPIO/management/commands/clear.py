from django.core.management.base import BaseCommand, CommandError
from GPIO.models import Temperatures as measurement
from django.utils import timezone
import random

class Command(BaseCommand):
    help = "removes database entries"

    def handle(self, *args, **options):
        entries = measurement.objects.all() 
        for entry in entries:
         entry.delete()