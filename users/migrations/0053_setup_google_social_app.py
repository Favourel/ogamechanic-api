from django.conf import settings
from django.db import migrations


def create_google_social_app(apps, schema_editor):
    """
    Ensures a SocialApp record for Google exists in the database
    and is linked to the primary Site.
    """
    try:
        SocialApp = apps.get_model("socialaccount", "SocialApp")
        Site = apps.get_model("sites", "Site")
    except LookupError:
        return

    client_id = getattr(
        settings,
        "GOOGLE_CLIENT_ID",
        "113954419006-ngbls808fq260861rc0inh74hu9v8g0l.apps.googleusercontent.com",
    )
    secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "") or ""

    app, created = SocialApp.objects.get_or_create(
        provider="google",
        defaults={
            "name": "Google",
            "client_id": client_id,
            "secret": secret,
        },
    )
    if not created and app.client_id != client_id:
        app.client_id = client_id
        app.secret = secret
        app.save()

    # Link to existing site
    site = Site.objects.first()
    if site and not app.sites.filter(id=site.id).exists():
        app.sites.add(site)


def remove_google_social_app(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0052_driverprofile_nin_is_verified_and_more"),
        ("socialaccount", "0001_initial"),
        ("sites", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_google_social_app, remove_google_social_app),
    ]
