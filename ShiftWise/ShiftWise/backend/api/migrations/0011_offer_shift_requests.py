import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_schedule_publication'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shiftrequest',
            name='kind',
            field=models.CharField(choices=[('give', 'Give my shift away'), ('take', 'Take their shift'), ('swap', 'Swap shifts'), ('offer', 'Offer my shift to the whole department')], max_length=5),
        ),
        migrations.AlterField(
            model_name='shiftrequest',
            name='target',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='shift_requests_received', to='api.employeeprofile'),
        ),
    ]
