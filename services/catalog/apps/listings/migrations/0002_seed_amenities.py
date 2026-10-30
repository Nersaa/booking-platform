from django.db import migrations

AMENITIES = {
    "wifi": "Wi-Fi",
    "kitchen": "Kitchen",
    "parking": "Free parking",
    "washer": "Washer",
    "air_conditioning": "Air conditioning",
    "heating": "Heating",
    "tv": "TV",
    "workspace": "Dedicated workspace",
    "pool": "Pool",
    "pets_allowed": "Pets allowed",
}


def seed(apps, schema_editor):
    Amenity = apps.get_model("listings", "Amenity")
    for code, name in AMENITIES.items():
        Amenity.objects.update_or_create(code=code, defaults={"name": name})


def unseed(apps, schema_editor):
    apps.get_model("listings", "Amenity").objects.filter(code__in=AMENITIES).delete()


class Migration(migrations.Migration):
    dependencies = [("listings", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
