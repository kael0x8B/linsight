"""Bounded algorithm diagnostics. Never publish exception text, locals or source code."""

import re
import traceback
from pathlib import Path, PurePosixPath
from uuid import uuid4

MESSAGES = {
    "IMPORT": "算法模块导入失败，请检查包内依赖和语法",
    "INITIALIZE": "算法初始化失败，请检查 Algorithm 构造函数",
    "PROCESS": "算法处理失败，请检查 process 方法",
    "SDK": "算法模型调用失败，请检查授权角色、输入区域及模型状态",
    "OUTPUT": "算法输出不符合标准对象契约，请检查 objects / observationValid",
    "PROTOCOL": "算法工作进程返回无效消息或已退出",
}


def exception_details(error: Exception, directory: Path, stage: str) -> dict:
    frames = []
    entries = [(f.filename, f.lineno, f.name) for f in traceback.extract_tb(error.__traceback__)]
    if isinstance(error, SyntaxError) and error.filename:
        entries.append((error.filename, error.lineno or 1, "<module>"))
    for filename, line, function in entries:
        try:
            relative = Path(filename).resolve().relative_to(directory.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        frames.append({"file": relative, "line": line, "function": function})
    return {"stage": stage, "exceptionType": type(error).__name__, "frames": frames[-6:]}


class AlgorithmExecutionError(ValueError):
    def __init__(self, manifest, digest, details, *, timestamp=None, timeout=False):
        stage = details.get("stage", "PROTOCOL")
        if not isinstance(stage, str) or stage not in MESSAGES:
            stage = "PROTOCOL"
        frames = []
        source_frames = details.get("frames", [])
        if not isinstance(source_frames, list):
            source_frames = []
        for frame in source_frames[-6:]:
            if not isinstance(frame, dict):
                continue
            filename = str(frame.get("file", ""))[:160]
            path = PurePosixPath(filename)
            line = frame.get("line")
            if (
                not filename
                or path.is_absolute()
                or ".." in path.parts
                or not re.fullmatch(r"[a-zA-Z0-9_./-]+\.py", filename)
                or not isinstance(line, int)
                or not 1 <= line <= 1_000_000
            ):
                continue
            function = str(frame.get("function", ""))[:80]
            frames.append(
                {
                    "file": filename,
                    "line": line,
                    "function": function if re.fullmatch(r"[\w<>]+", function) else "unknown",
                }
            )
        exception_type = str(details.get("exceptionType", "Exception"))[:80]
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", exception_type):
            exception_type = "Exception"
        message = "算法包处理超时" if timeout else MESSAGES[stage]
        self.diagnostic = {
            "schemaVersion": "1.0",
            "diagnosticId": str(uuid4()),
            "code": "ALGORITHM_TIMEOUT" if timeout else f"ALGORITHM_{stage}_FAILED",
            "stage": stage,
            "exceptionType": exception_type,
            "message": message,
            "packageCode": manifest["code"],
            "packageVersion": manifest["version"],
            "packageSha256": digest,
            "timestampMillis": timestamp,
            "frames": frames,
        }
        location = f" ({frames[-1]['file']}:{frames[-1]['line']})" if frames else ""
        super().__init__(f"{message}：{exception_type}{location}")
