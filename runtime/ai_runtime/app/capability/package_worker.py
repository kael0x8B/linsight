"""Small stdlib-only algorithm process. stdout is reserved for framed SDK messages."""

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

CHANNEL = sys.stdout
MAX_MESSAGE = 4 * 1024 * 1024


def send(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(data.encode()) > MAX_MESSAGE:
        raise ValueError("algorithm output exceeds limit")
    CHANNEL.write(data + "\n")
    CHANNEL.flush()


class Context:
    """SDK 1.0: access only bound model slots through the host's shared model pool."""

    def call(self, operation, **arguments):
        send({"call": operation, "arguments": arguments})
        response = json.loads(sys.stdin.readline(MAX_MESSAGE + 1))
        if not response.get("ok"):
            raise RuntimeError("Algorithm model operation failed")
        return response["data"]

    def infer(self, slot, region=None):
        return self.call("infer", slot=slot, region=region)

    def extract_embedding(self, slot, region=None):
        return self.call("embedding", slot=slot, region=region)

    def reference_embedding(self, resource, entry_id):
        return self.call("reference_embedding", resource=resource, entryId=entry_id)


def main():
    directory, entrypoint = Path(sys.argv[1]), sys.argv[2]
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location("algorithm_impl", directory / entrypoint)
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
        algorithm = module.Algorithm()
    send({"ready": True})
    for line in sys.stdin:
        try:
            if len(line.encode()) > MAX_MESSAGE:
                raise ValueError("input too large")
            payload = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                result = algorithm.process(payload, Context())
            send({"result": result})
        except Exception as error:
            send({"error": type(error).__name__})


if __name__ == "__main__":
    main()
