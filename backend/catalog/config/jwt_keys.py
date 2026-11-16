from pathlib import Path

from cryptography.hazmat.primitives import serialization


def load_rsa_keypair(private_key_file: str) -> tuple[str, str]:
    """Return (private_pem, public_pem); empty strings when the key file is absent."""
    path = Path(private_key_file) if private_key_file else None
    if path is None or not path.is_file():
        return "", ""

    private_pem = path.read_bytes()
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem.decode(), public_pem.decode()
