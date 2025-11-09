from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse, JsonResponse, Http404
from .models import Temperatures

def index(request):
   template = loader.get_template("GPIO/dashboard.html")
   return HttpResponse(template.render({}, request))

def fetch_temperatures(request):
   data = list(Temperatures.objects.values("measurement", "date"))
   return JsonResponse(data, safe=False)

def fetch_humidities(request):
   data = ["humidities", "placeholder", "value"]
   return JsonResponse(data, safe=False)

def fetch_vcos(request):
   data = ["vco", "placeholder", "values"]
   return JsonResponse(data, safe=False)