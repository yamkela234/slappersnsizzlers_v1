from .models import TruckLocation


def truck(request):
    return {"truck": TruckLocation.current()}
