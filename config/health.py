# config/health.py
from django.db import connection
from django.http import JsonResponse

def health(request):
    ok_db = True
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1;")
            c.fetchone()
    except Exception:
        ok_db = False
    return JsonResponse({"ok": ok_db})
