from django.db import migrations

def create_initial_master_data(apps, schema_editor):
    """Fungsi untuk memasukkan data kategori dan area."""
    SportCategory = apps.get_model('main', 'SportCategory')
    LocationArea = apps.get_model('main', 'LocationArea')
    
    # 1. DATA KATEGORI OLAHRAGA
    sport_categories = ['Futsal', 'Basket', 'Mini Soccer', 'Padel', 'Tenis']
    for name in sport_categories:
        SportCategory.objects.get_or_create(name=name)
        
    # 2. DATA AREA LOKASI
    location_areas = ['Jakarta', 'Tangerang', 'Bogor', 'Depok', 'Bekasi']
    for name in location_areas:
        LocationArea.objects.get_or_create(name=name)


def reverse_initial_master_data(apps, schema_editor):
    """Fungsi untuk menghapus data jika migrasi dibatalkan."""
    SportCategory = apps.get_model('main', 'SportCategory')
    LocationArea = apps.get_model('main', 'LocationArea')
    
    SportCategory.objects.filter(name__in=['Futsal', 'Basket', 'Mini Soccer', 'Padel', 'Tenis']).delete()
    LocationArea.objects.filter(name__in=['Jakarta', 'Tangerang', 'Bogor', 'Depok', 'Bekasi']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'), 
    ]

    operations = [
        migrations.RunPython(create_initial_master_data, reverse_initial_master_data),
    ]