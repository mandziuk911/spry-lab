"""Local fixture: HTTPS JWKS plus an ephemeral, pre-authenticated browser session.

No sign-in endpoints. Only public keys are served; the session file is private.
The Spry image does not include or import this fixture.
"""

import json
import os
import ssl
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

issuer = os.environ["COGNITO_ISSUER"]
client_id = os.environ["COGNITO_CLIENT_ID"]
assert issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_SpryLab9MockOnly"
assert client_id == "SpryLab9LocalClient"
fixture = Path("/fixture")
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
kid = "spry-lab9-ephemeral"
jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
jwks = json.dumps({"keys": [{**jwk, "kid": kid, "alg": "RS256", "use": "sig"}]}).encode()
expires = int(time.time()) + 300
profile = {"sub": "spry-lab9-local", "email": "local-demo@example.invalid"}
access_token = jwt.encode(
    {**profile, "iss": issuer, "client_id": client_id, "token_use": "access", "exp": expires},
    key,
    algorithm="RS256",
    headers={"kid": kid},
)


class JWKSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/us-east-1_SpryLab9MockOnly/.well-known/jwks.json":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(jwks)))
        self.end_headers()
        self.wfile.write(jwks)


tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain(fixture / "tls.crt", fixture / "tls.key")
with HTTPServer(("0.0.0.0", 443), JWKSHandler) as server:
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    os.umask(0o077)
    temporary = fixture / "session.tmp"
    temporary.write_text(json.dumps({
        "access_token": access_token,
        "refresh_token": "fixture-not-refreshable",
        "token_type": "Bearer",
        "profile": profile,
        "expires_at": expires,
    }))
    temporary.rename(fixture / "session.json")
    server.serve_forever()
