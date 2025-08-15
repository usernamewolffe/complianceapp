from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0009_backfill_site_org"),
    ]
    operations = [
        # Enforce NOT NULL on org
        migrations.AlterField(
            model_name="site",
            name="org",
            field=models.ForeignKey(
                to="orgs.org",
                on_delete=models.CASCADE,
                related_name="sites",
            ),
        ),
        # Switch created_at to auto_now_add=True (no manual default)
        migrations.AlterField(
            model_name="site",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, editable=False),
        ),
    ]
