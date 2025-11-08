from django.db import models

# Create your models here.

class TemperatureValues(models.Model):
   unit = models.CharField(max_length=50)
   date = models.DateTimeField("timestamp")
   measurement =  models.DecimalField(max_digits=5, decimal_places=2)

class RadarSensoreValues(models.Model):
   unit = models.CharField(max_length=50)
   date = models.DateTimeField("timestamp")
   measurement =  models.DecimalField(max_digits=5, decimal_places=2)