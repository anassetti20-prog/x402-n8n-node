#!/usr/bin/env python3
import os, base64, sys
key_path = os.path.expanduser("/root/x402-api/.encryption_key.secure")
enc_path = os.path.expanduser("/root/x402-api/.env.enc")
with open(key_path, "rb") as f:
    key = f.read()
with open(enc_path, "rb") as f:
    enc = base64.b64decode(f.read())
decrypted = bytes([enc[i] ^ key[i % len(key)] for i in range(len(enc))])
print(decrypted.decode())
