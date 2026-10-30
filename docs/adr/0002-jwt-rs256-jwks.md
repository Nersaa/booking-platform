# 2. RS256 access tokens verified through JWKS

Status: accepted

## Context

Catalog authenticates users, but Booking must authorise requests too. Sharing an
HMAC secret would let any service mint tokens, and asking Catalog on every request
would couple Booking's availability to Catalog.

## Decision

- Catalog signs tokens with an RSA private key (RS256). Only Catalog holds it.
- Catalog publishes the public key at `/.well-known/jwks.json`. Every token carries
  a `kid` header equal to the RFC 7638 thumbprint of the key.
- Other services fetch the JWKS once, cache it and verify tokens locally
  (`iss`, `aud`, `exp`, signature).
- Access tokens live 15 minutes and carry `sub` and `roles`. Refresh tokens rotate
  on every use, and a reused refresh token is rejected (blacklist).
- The private key is generated inside the deployment (`generate_jwt_keys`) and is
  never part of the repository or the image.

## Consequences

- Booking verifies tokens without network calls; key rotation means publishing a new
  key next to the old one in JWKS.
- Roles inside an access token can be stale for up to its lifetime. Granting the
  host role returns a fresh token pair to avoid that for the common case.
