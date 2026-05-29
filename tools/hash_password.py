"""Genera un hash PBKDF2 para ADMIN_PASSWORD_HASH.
Uso: python tools/hash_password.py "tu_password_seguro"
"""
import hashlib
import os
import sys

if len(sys.argv) < 2:
    raise SystemExit('Uso: python tools/hash_password.py "tu_password_seguro"')

password = sys.argv[1]
salt = os.urandom(16)
iterations = 260_000
digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
print(f"pbkdf2_sha256${iterations}${salt.hex()}${digest}")
