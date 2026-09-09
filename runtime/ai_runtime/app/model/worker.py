"""Private local IPC worker, not a network service or executable model hook."""

import contextlib
import json
import os
import sys


def main() -> None:
    # Preserve a private protocol descriptor, then redirect native SDK printf as
    # well as Python prints. Native RKNN startup logs otherwise corrupt stdout.
    output = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with contextlib.redirect_stdout(sys.stderr):
        from PIL import Image

        from ai_runtime.app.model.contracts import (
            DeployModelRequest,
            ModelTestParameters,
            ModelTestRequest,
        )
        from ai_runtime.app.model.pool import _load_adapter, _sha256

        adapter = None
        model_version_id = None
        try:
            for line in sys.stdin.buffer:
                try:
                    message = json.loads(line)
                    if message.get('shutdown'):
                        break
                    if adapter is None:
                        request = DeployModelRequest.model_validate(message)
                        digest = _sha256(request.artifact_path)
                        if digest != request.sha256:
                            raise ValueError("model artifact SHA256 mismatch")
                        adapter, backend = _load_adapter(
                            request.artifact_path, request.artifact_format, request.device,
                            request.adapter, request.runtime_manifest, request.trusted_artifact,
                            digest,
                        )
                        model_version_id = request.model_version_id
                        result = {"backend": backend}
                    elif 'imageRgb' in message:
                        metadata = message['imageRgb']
                        width, height = metadata['width'], metadata['height']
                        count = metadata['bytes']
                        if (not isinstance(count, int) or not 0 < count <= 32 * 1024 * 1024
                                or count != width * height * 3):
                            raise ValueError('invalid RGB frame size')
                        data = sys.stdin.buffer.read(count)
                        if len(data) != count:
                            break  # EOF / failed parent; never infer a partial frame.
                        if message['modelVersionId'] != model_version_id:
                            raise ValueError('model binding differs from worker')
                        image = Image.frombytes('RGB', (width, height), data)
                        parameters = ModelTestParameters.model_validate(message['parameters'])
                        result = adapter.infer_image(image, parameters).model_dump(by_alias=True)
                    else:
                        request = ModelTestRequest.model_validate(message)
                        if request.model_version_id != model_version_id:
                            raise ValueError('model binding differs from worker')
                        prediction = adapter.infer(str(request.image_path), request.parameters)
                        result = prediction.model_dump(by_alias=True)
                    response = {"result": result}
                except Exception as error:
                    # Do not reflect arbitrary checkpoint/library exception text or paths.
                    if isinstance(error, ModuleNotFoundError):
                        message = "模型需要的模块不在受支持的依赖配置中，请检查模型格式与运行环境"
                    elif isinstance(error, MemoryError):
                        message = "节点内存不足，无法加载或执行模型"
                    else:
                        message = "模型格式、执行合约或输入不兼容，请检查模型版本和测试参数"
                    response = {"error": message}
                output.write(json.dumps(response) + "\n")
                output.flush()
        finally:
            if adapter is not None and callable(getattr(adapter, 'close', None)):
                adapter.close()
            output.close()


if __name__ == "__main__":
    main()
