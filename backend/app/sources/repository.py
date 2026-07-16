import hashlib


def make_block_id(document_sha256: str, locator: str, parser_version: str) -> str:
    raw = "\0".join((document_sha256, locator, parser_version)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
