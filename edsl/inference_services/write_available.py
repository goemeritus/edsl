from edsl.inference_services.registry import default

d = {}
for service in default.services:
    d[service._inference_service_] = service.available()

with open('models_available_cache.py', 'w') as f:
    f.write(f"models_available = {d}")
