import datetime

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_and_publish_existing(apps, schema_editor):
    """Give every shift its week, and post every week that already has shifts so nothing disappears for employees."""
    Shift = apps.get_model('api', 'Shift')
    Publication = apps.get_model('api', 'SchedulePublication')
    seen = set()
    for shift in Shift.objects.all().only('id', 'department_id', 'shift_date'):
        monday = shift.shift_date - datetime.timedelta(days=shift.shift_date.weekday())
        Shift.objects.filter(pk=shift.pk).update(week_start=monday)
        seen.add((shift.department_id, monday))
    for department_id, monday in seen:
        Publication.objects.create(department_id=department_id, week_start=monday)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_general_manager_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='shift',
            name='week_start',
            field=models.DateField(db_index=True, editable=False, null=True),
        ),
        migrations.CreateModel(
            name='SchedulePublication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField()),
                ('published_at', models.DateTimeField(auto_now_add=True)),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='publications', to='api.department')),
                ('published_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-week_start', 'department_id'],
            },
        ),
        migrations.AddConstraint(
            model_name='schedulepublication',
            constraint=models.UniqueConstraint(fields=('department', 'week_start'), name='one_publication_per_week'),
        ),
        migrations.RunPython(backfill_and_publish_existing, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='shift',
            name='week_start',
            field=models.DateField(db_index=True, editable=False),
        ),
    ]
