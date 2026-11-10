from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_offer_shift_requests'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='extra_departments',
            field=models.ManyToManyField(blank=True, related_name='extra_members', to='api.department'),
        ),
    ]
