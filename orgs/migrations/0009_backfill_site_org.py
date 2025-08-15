from django.db import migrations

def backfill_site_org(apps, schema_editor):
    Site = apps.get_model("orgs", "Site")
    Org = apps.get_model("orgs", "Org")

    # If any sites are missing org, attach them to the first org (temporary sensible default).
    # Prefer to fix these in admin BEFORE running this, if you can.
    first_org = Org.objects.order_by("id").first()
    if first_org:
        Site.objects.filter(org__isnull=True).update(org=first_org)

class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0008_alter_site_options_site_address_site_created_at_and_more"),
    ]
    operations = [
        migrations.RunPython(backfill_site_org, migrations.RunPython.noop),
    ]
