from django.core.management.base import BaseCommand, CommandError
from GPIO.models import TemperatureValues as measurement
from django.utils import timezone
import random


class Command(BaseCommand):
    help = "Adds a temperature measurement to the database"

    def handle(self, *args, **options):
        simulated_measurement = round(random.uniform(18,26))
        temperature_unit = "Celsius"
        timestamp = timezone.now()
        try:
            new_measurement = measurement(measurement=simulated_measurement, unit=temperature_unit, timestamp=timestamp)
            new_measurement.save()
            print(f"{new_measurement.measurement} \t {timestamp}")
        except Exception as error:
            # Log errors 
            print(f"{error} \t {timestamp}")