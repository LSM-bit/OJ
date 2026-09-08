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
            # 编译器（尤其 javac/JVM）需要预留大块虚拟地址空间，放宽到 4GB
            memory_limit_mb=max(4096, cases[0].limits.memory_limit_mb),
            output_limit_kb=cases[0].limits.output_limit_kb,
            # javac 多线程编译需要更多进程/线程配额
            process_limit=max(512, cases[0].limits.process_limit),
        )
        with tempfile.TemporaryDirectory(prefix="oj-judge-", dir=self._ensure_root()) as tmp:
            workdir = Path(tmp)
            # nsjail 内以 nobody(65534) 运行，需要让工作目录可写可进入
            workdir.chmod(0o777)
            source_name, run_cmd, compile_cmd = _commands(cases[0].language, str(workdir))
            source_path = workdir / source_name
            source_path.write_bytes(cases[0].source)
            source_path.chmod(0o644)

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
                limits = case.limits
                if cases[0].language == "java21":
                    # JVM 预留虚拟地址空间 >> 实际内存，运行阶段 rlimit_as 同样需放宽；
                    # 真实内存占用靠 -Xmx 与 VmHWM 计量约束
                    limits = ResourceLimits(
                        time_limit_ms=limits.time_limit_ms,
                        memory_limit_mb=max(4096, limits.memory_limit_mb),
                        output_limit_kb=limits.output_limit_kb,
                        process_limit=max(256, limits.process_limit),
                    )
                res = self._run(run_cmd, cwd=workdir, stdin=case.stdin, limits=limits)
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
            workdir.chmod(0o777)
            source_name, run_cmd, compile_cmd = _commands(language, str(workdir))
            source_path = workdir / source_name
            source_path.write_bytes(code)
            source_path.chmod(0o644)
            if compile_cmd:
                # 与 execute_cases 一致：编译阶段放宽限制（javac/JVM 需要大地址空间与进程配额）
                compile_limits = ResourceLimits(
                    time_limit_ms=max(10_000, limits.time_limit_ms * 10),
                    memory_limit_mb=max(4096, limits.memory_limit_mb),
                    output_limit_kb=limits.output_limit_kb,
                    process_limit=max(512, limits.process_limit),
                )
                cres = self._run(compile_cmd, cwd=workdir, stdin=b"",
                                 limits=compile_limits, compile=True)
                if cres.status != "ok":
                    return {"status": "compile_error", "output": b"",
                            "error_message": cres.stderr.decode("utf-8", errors="replace")[:4000]}
            if language == "java21":
                # 与 execute_cases 一致：JVM 预留虚拟地址空间 >> 实际内存，rlimit_as 需放宽
                limits = ResourceLimits(
                    time_limit_ms=limits.time_limit_ms,
                    memory_limit_mb=max(4096, limits.memory_limit_mb),
                    output_limit_kb=limits.output_limit_kb,
                    process_limit=max(256, limits.process_limit),
                )
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
            # 传递环境变量到沙箱内
            "--env", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "--env", "HOME=/workspace",
            "--env", "TMPDIR=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
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
        # 内存计量：程序运行期间周期采样进程树 VmHWM。
        # 程序退出后 /proc 条目即消失，事后扫树只会得到 0，必须边跑边读。
        peak_rss = _RssSampler(proc.pid)
        try:
            proc.wait(timeout=limits.time_limit_ms / 1000 + 10)  # 墙钟兜底
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            timed_out = True
        peak_rss.stop()
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
        elif proc.returncode in (137, 143, -9, -15):
            # nsjail 自己按 --time_limit SIGKILL 子进程后以 137 退出（SIGTERM 143），
            # 外层墙钟兜底（+10s）来不及触发 timed_out，需按信号码识别为超时
            return ExecutionResult("time_limit_exceeded", stdout, stderr, elapsed_ms, 0,
                                   proc.returncode, compile)
        elif proc.returncode in (134, -6):
            # SIGABRT（exit 134）：两种来源——
            #   1. C++ 未捕获异常 → terminate called after throwing ...（含 what() 输出）→ RE
            #   2. 内存分配失败 std::bad_alloc（stderr 含 bad_alloc）→ MLE
            if b"bad_alloc" in stderr or b"MemoryError" in stderr:
                status = "memory_limit_exceeded"
            else:
                status = "runtime_error"
        elif b"MemoryError" in stderr or b"std::bad_alloc" in stderr \
                or b"Cannot allocate memory" in stderr:
            # Python 的 MemoryError 以 exit 1 + traceback 出现（rlimit_as 拦截超额分配），
            # 凭 stderr 关键词与普通运行错误区分
            status = "memory_limit_exceeded"
        elif b"SyntaxError" in stderr or b"IndentationError" in stderr:
            # Python 无编译步骤，语法错在运行期才出现；按编译错误归类（与 C++ CE 一致的语义）
            status = "compile_error"
        else:
            status = "runtime_error"
        # 内存计量：nsjail + rlimit_as 拦截超额分配；峰值由运行期采样器收集
        return ExecutionResult(status, stdout, stderr, elapsed_ms, peak_rss.peak_kb,
                               proc.returncode, compile)


class _RssSampler:
    """后台线程周期采样 nsjail 进程树的 VmHWM，取最大值。

    程序退出后 /proc 条目立即消失，不能等 wait() 返回后再扫——
    那正是之前 A+B 这类秒退程序内存恒为 0 的原因。
    进程树用 /proc/<pid>/task/<pid>/children 内核接口逐层收集
    （全量扫 /proc 匹配 ppid 太慢，会错过短命进程的存活窗口）。
    root（nsjail 主进程自身 ~8.5MB）不计入用户内存。
    """

    def __init__(self, root_pid: int, interval_ms: int = 2):
        self.root_pid = root_pid
        self.interval_ms = interval_ms
        self.peak_kb = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _loop(self) -> None:
        while True:
            try:
                peak = _tree_peak_rss(self.root_pid)
                if peak > self.peak_kb:
                    self.peak_kb = peak
            except Exception:  # noqa: BLE001 单次采样失败不影响判题
                pass
            if self._stop.wait(self.interval_ms / 1000):
                break


def _tree_peak_rss(root_pid: int) -> int:
    """单次采样 root_pid 进程树（不含 root 自身）的 VmHWM 最大值（kB）"""
    def children(pid: int) -> list[int]:
        try:
            with open(f"/proc/{pid}/task/{pid}/children") as f:
                return [int(x) for x in f.read().split()]
        except OSError:
            return []

    # children 接口逐层下钻；总进程数很小，深度 10 兜底防异常环
    tree = [root_pid]
    i = 0
    while i < len(tree) and i < 10_000:
        tree.extend(children(tree[i]))
        i += 1

    peak = 0
    for pid in tree[1:]:  # 跳过 root：nsjail 自身开销不算用户内存
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmHWM"):
                        peak = max(peak, int(line.split()[1]))
                        break
        except OSError:
            continue
    return peak


def _commands(language: str, workdir: str) -> tuple[str, list[str], list[str] | None]:
    """返回 (源文件名, 运行命令, 编译命令|None)。工具链用绝对路径保证 nsjail 下确定。"""
    # 编译/运行命令都通过 sh -c 包装，确保 PATH 可用
    if language == "python3.12":
        return "Main.py", ["/usr/bin/python3", f"{workdir}/Main.py"], None
    if language == "cpp17":
        return "Main.cpp", [f"{workdir}/Main"], [
            "/bin/sh", "-c",
            f"PATH=/usr/bin:/bin /usr/bin/g++ -std=c++17 -O2 -pipe -o {workdir}/Main {workdir}/Main.cpp"]
    if language == "c17":
        return "Main.c", [f"{workdir}/Main"], [
            "/bin/sh", "-c",
            f"PATH=/usr/bin:/bin /usr/bin/gcc -std=c17 -O2 -pipe -o {workdir}/Main {workdir}/Main.c"]
    if language == "java21":
        # JVM 需要预留大块虚拟地址空间（code cache + class space + 堆），
        # rlimit_as 必须放宽到 ~4GB 才能启动；实际物理内存占用由 -Xmx 控制。
        # 注意：Java 的内存限制无法靠 rlimit_as 精确执行，判题内存指标以 VmHWM 计量兜底
        return "Main.java", [
            "/usr/bin/java", "-Xss8m", "-Xmx256m",
            "-XX:ReservedCodeCacheSize=64m", "-XX:CompressedClassSpaceSize=128m",
            "-Xshare:off", "-cp", workdir, "Main"], [
            "/bin/sh", "-c",
            # javac 也是 JVM：默认堆按物理内存 1/4 预留，会占满低 4GB rlimit_as 导致 native 堆 OOM，
            # 显式限制堆并用 SerialGC 减少线程/地址空间压力
            f"PATH=/usr/bin:/bin /usr/bin/javac -encoding UTF-8 -J-Xmx256m -J-Xms64m "
            f"-J-XX:+UseSerialGC -d {workdir} {workdir}/Main.java"]
    raise ValueError(f"不支持的语言: {language}")
