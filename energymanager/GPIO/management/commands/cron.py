from django.core.management.base import BaseCommand, CommandError
from GPIO.models import TemperatureValues as measurement
from django.utils import timezone
import random


class Command(BaseCommand):
    help = "Adds a measurement to the database"

    def handle(self, *args, **options):
        simulated_measurement = round(random.uniform(18,26))
        temperature_unit = "Celsius"
        timestamp = timezone.now()
        # print("Blub")
        # random_measurement = random.randint(18, 29)

        new_measurement = measurement(measurement=simulated_measurement, unit=temperature_unit, date=timestamp)
        print(new_measurement.measurement)
        new_measurement.save()
        pass