import hashlib
from pathlib import Path

import httpx


async def download_file(url: str, target: Path, max_bytes: int, sha256: str | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        async with httpx.AsyncClient(
            timeout=120.0, trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with temporary.open("wb") as stream:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("download exceeds configured size limit")
                        digest.update(chunk)
                        stream.write(chunk)
        if sha256 is not None and digest.hexdigest() != sha256:
            raise ValueError("downloaded artifact SHA256 mismatch")
        temporary.replace(target)
        return target
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
