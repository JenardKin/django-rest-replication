"""
Root conftest.py — ensures both src/ and the repo root are on sys.path
so that `import django_rest_replication` and `import tests.testapp` both resolve
in CI without needing an editable install.
"""
