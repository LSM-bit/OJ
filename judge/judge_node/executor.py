"""nsjail 沙箱执行器：编译一次 + 逐测试点运行

固定运行在 Linux 容器内（nsjail 原生可用）。
工作区根目录由 JUDGE_WORKSPACE_ROOT / node.toml [paths].workspace 提供。
"""

import shlex
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

NSJAIL = "nsjail"
NSJAIL_CONFIG = "/etc/oj/nsjail.cfg"


@dataclass
class ResourceLimits:
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    output_limit_kb: int = 1024
    process_limit: int = 32
    cpu_cores: int = 1


@dataclass
class ExecutionResult:
    status: str                 # ok / runtime_error / time_limit_exceeded / memory_limit_exceeded / output_limit_exceeded
    stdout: bytes
    stderr: bytes
    time_used_ms: int
    memory_used_kb: int
    exit_code: int
    compile: bool = False       # 是否为编译阶段结果


@dataclass
class JudgeCase:
    language: str
    source: bytes
    stdin: bytes
    expected: bytes
    limits: ResourceLimits
    case_id: str = ""
    score: int = 0


def _same_output(expected: bytes, actual: bytes) -> bool:
    """忽略行尾空格与文件末尾换行"""
    def norm(b: bytes) -> list[str]:
        lines = b.decode("utf-8", errors="replace").splitlines()
        return [line.rstrip(" \t") for line in lines if line.strip("\r\n") or line.strip()]
    return norm(expected) == norm(actual)


class JudgeWorker:
    def __init__(self, workspace_root: str = "/workspace"):
        self.workspace_root = Path(workspace_root)

    # ---------- 对外接口 ----------

    def execute_cases(
        self, cases: list[JudgeCase],
        compile_limits: ResourceLimits | None = None,
        *, stop_on_failure: bool = False,
    ) -> list[ExecutionResult]:
        """编译一次后逐测试点运行。stop_on_failure：ACM 赛制短路。"""
        compile_limits = compile_limits or ResourceLimits(
            time_limit_ms=max(10_000, cases[0].limits.time_limit_ms * 10),
            memory_limit_mb=cases[0].limits.memory_limit_mb,
            output_limit_kb=cases[0].limits.output_limit_kb,
        )
        with tempfile.TemporaryDirectory(prefix="oj-judge-", dir=self._ensure_root()) as tmp:
            workdir = Path(tmp)
            source_name, run_cmd, compile_cmd = _commands(cases[0].language, str(workdir))
            source_path = workdir / source_name
            source_path.write_bytes(cases[0].source)

            results: list[ExecutionResult] = []
            compile_result = None
            if compile_cmd:
                compile_result = self._run(compile_cmd, cwd=workdir, stdin=b"",
                                           limits=compile_limits, compile=True)
                if compile_result.status != "ok":
                    # 全部测试点返回编译失败
                    return [ExecutionResult(
                        status="compile_error",
                        stdout=b"", stderr=compile_result.stderr,
                        time_used_ms=compile_result.time_used_ms,
                        memory_used_kb=compile_result.memory_used_kb,
                        exit_code=compile_result.exit_code, compile=True,
                    ) for _ in cases]

            for case in cases:
                res = self._run(run_cmd, cwd=workdir, stdin=case.stdin, limits=case.limits)
                if res.status == "ok":
                    res = ExecutionResult(
                        status="accepted" if _same_output(case.expected, res.stdout) else "wrong_answer",
                        stdout=res.stdout, stderr=res.stderr,
                        time_used_ms=res.time_used_ms, memory_used_kb=res.memory_used_kb,
                        exit_code=res.exit_code)
                results.append(res)
                if stop_on_failure and res.status != "accepted":
                    break
            return results

    def run_code(self, language: str, code: bytes, stdin: bytes,
                 limits: ResourceLimits) -> dict:
        """用户自测：单次运行，不比对"""
        with tempfile.TemporaryDirectory(prefix="oj-run-", dir=self._ensure_root()) as tmp:
            workdir = Path(tmp)
            source_name, run_cmd, compile_cmd = _commands(language, str(workdir))
            (workdir / source_name).write_bytes(code)
            if compile_cmd:
                cres = self._run(compile_cmd, cwd=workdir, stdin=b"", limits=limits)
                if cres.status != "ok":
                    return {"status": "compile_error", "output": b"",
                            "error_message": cres.stderr.decode("utf-8", errors="replace")[:4000]}
            res = self._run(run_cmd, cwd=workdir, stdin=stdin, limits=limits)
            status = {"ok": "finished"}.get(res.status, res.status)
            return {"status": status, "output": res.stdout,
                    "error_message": res.stderr.decode("utf-8", errors="replace")[:4000],
                    "time_used_ms": res.time_used_ms, "memory_used_kb": res.memory_used_kb}

    # ---------- 内部 ----------

    def _ensure_root(self) -> str:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return str(self.workspace_root)

    def _run(self, command: list[str], *, cwd: Path, stdin: bytes,
             limits: ResourceLimits, compile: bool = False) -> ExecutionResult:
        argv = [NSJAIL]
        if Path(NSJAIL_CONFIG).exists():
            argv += ["--config", NSJAIL_CONFIG]
        argv += [
            # /tmp 与作业目录可写（-B = bind rw）；根目录其余部分按 cfg 只读
            "--bindmount", "/tmp",
            "--bindmount", str(cwd),
            "--time_limit", str(max(1, (limits.time_limit_ms + 999) // 1000)),
            "--rlimit_as", str(limits.memory_limit_mb),
            "--rlimit_fsize", str(limits.output_limit_kb),
            "--rlimit_nproc", str(limits.process_limit),
            "--", "/bin/sh", "-c", shlex.join(command),
        ]
        env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
               "HOME": "/workspace", "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}
        # nsjail 日志重定向到文件，避免混入编译器/程序 stderr
        argv = argv[:1] + ["--log", "/tmp/nsjail.log"] + argv[1:]

        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        out_buf: list[bytes] = []
        err_buf: list[bytes] = []
        threads = [
            threading.Thread(target=lambda: out_buf.append(proc.stdout.read())),
            threading.Thread(target=lambda: err_buf.append(proc.stderr.read())),
        ]
        for t in threads:
            t.start()
        try:
            proc.stdin.write(stdin)
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=limits.time_limit_ms / 1000 + 10)  # 墙钟兜底
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            timed_out = True
        for t in threads:
            t.join()
        elapsed_ms = int((time.monotonic() - started) * 1000)

        stdout = out_buf[0] if out_buf else b""
        stderr = err_buf[0] if err_buf else b""
        if len(stdout) > limits.output_limit_kb * 1024:
            return ExecutionResult("output_limit_exceeded", stdout[:4096], stderr,
                                   elapsed_ms, 0, proc.returncode, compile)
        if timed_out:
            return ExecutionResult("time_limit_exceeded", stdout, stderr, elapsed_ms, 0, -9, compile)
        if proc.returncode == 0:
            status = "ok"
        elif compile:
            # g++/gcc/gcc 的编译错误退出码为 1；区分编译失败与沙箱内运行失败
            status = "compile_error"
        else:
            status = "runtime_error"
        # 内存计量：nsjail + rlimit_as 拦截超额分配，此处粗计 RSS
        return ExecutionResult(status, stdout, stderr, elapsed_ms, _peak_rss_kb(proc.pid),
                               proc.returncode, compile)


def _peak_rss_kb(root_pid: int) -> int:
    """扫描 /proc 下子进程 status 的 VmHWM 最大值（判题进程组）"""
    import glob
    peak = 0
    try:
        for status_file in glob.glob("/proc/[0-9]*/status"):
            try:
                with open(status_file) as f:
                    content = f.read()
                # 仅统计启动时间晚于判题开始的进程开销太大，一期用简单启发：
                if "VmHWM" in content:
                    for line in content.splitlines():
                        if line.startswith("VmHWM"):
                            peak = max(peak, int(line.split()[1]))
                            break
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass
    return peak


def _commands(language: str, workdir: str) -> tuple[str, list[str], list[str] | None]:
    """返回 (源文件名, 运行命令, 编译命令|None)。工具链用绝对路径保证 nsjail 下确定。"""
    if language == "python3.12":
        return "Main.py", ["/usr/bin/python3", f"{workdir}/Main.py"], None
    if language == "cpp17":
        return "Main.cpp", [f"{workdir}/Main"], [
            "/usr/bin/g++", "-std=c++17", "-O2", "-pipe", "-o", f"{workdir}/Main", f"{workdir}/Main.cpp"]
    if language == "c17":
        return "Main.c", [f"{workdir}/Main"], [
            "/usr/bin/gcc", "-std=c17", "-O2", "-pipe", "-o", f"{workdir}/Main", f"{workdir}/Main.c"]
    if language == "java21":
        return "Main.java", ["/usr/bin/java", "-Xss256m", "-cp", workdir, "Main"], [
            "/usr/bin/javac", "-encoding", "UTF-8", "-d", workdir, f"{workdir}/Main.java"]
    raise ValueError(f"不支持的语言: {language}")
