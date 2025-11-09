from django.db import models

# Create your models here.

class Temperatures(models.Model):
   unit = models.CharField(max_length=50, db_column="unit")
   timestamp = models.DateTimeField(db_column="timestamp")
   measurement =  models.DecimalField(max_digits=5, decimal_places=2, db_column="measurement")

class Humidities(models.Model):
   unit = models.CharField(max_length=50, db_column="unit")
   timestamp = models.DateTimeField("timestamp", db_column="timestamp")
   measurement =  models.DecimalField(max_digits=5, decimal_places=2, db_column="measurement")