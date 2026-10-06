"""Build throwaway vaults in a temp dir, so tests control every byte (BOM, CRLF)."""
import os
import shutil
import tempfile


class TempVault:
    def __init__(self, files):
        """files: {"rel/path.md": str | bytes}"""
        self.root = tempfile.mkdtemp(prefix="vault-doctor-")
        for rel, content in files.items():
            full = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            data = content if isinstance(content, bytes) else content.encode("utf-8")
            with open(full, "wb") as f:
                f.write(data)

    def __enter__(self):
        return self.root

    def __exit__(self, *exc):
        shutil.rmtree(self.root, ignore_errors=True)
