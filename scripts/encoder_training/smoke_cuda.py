"""The kernel-launch check, run before anything trusts this machine with a GPU.

**Why this is its own module and its own entry point.** ``torch.cuda.is_available()``
returning ``True`` proves that a driver and a runtime are present. It does not
prove that the installed wheel contains a kernel image for *this* architecture.
An RTX 5070 is compute capability ``sm_120`` and needs a wheel built against CUDA
12.8 or later; an older wheel installs cleanly, imports cleanly, reports
``True``, and then fails at the first kernel launch with "no kernel image is
available for execution on the device". The failure looks nothing like a wheel
problem, and it surfaces at whatever point a kernel first runs -- which, without
this check, is twenty minutes into a fine-tune.

So the check runs a **real matmul on the device** and prints
``torch.version.cuda`` beside ``torch.cuda.get_device_capability(0)``. If it
fails, the fix is a torch wheel built against CUDA 12.8+ (DD12), never a code
change.

    python -m scripts.encoder_training.smoke_cuda

That form needs no network and downloads nothing: it is torch and the GPU only,
which is what makes it the right first command on a new machine. The package's
``smoke`` subcommand does everything this does *and* loads 440MB of encoder
weights, so it also checks the network, the hub cache and the tokeniser -- run
this one first, because when it fails the encoder download is wasted.

Torch is imported inside the functions, as everywhere else in this package, so
the module stays importable in CI where no ML wheels exist.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

#: Deterministic cuBLAS reductions (DD11). Torch reads this when it initialises
#: CUDA, so it has to be in the environment *before* the first CUDA call --
#: setting it afterwards is a silent no-op that leaves the run non-reproducible
#: with nothing to say so.
CUBLAS_ENV_VAR = "CUBLAS_WORKSPACE_CONFIG"
CUBLAS_ENV_VALUE = ":4096:8"

#: The compute capability of the GPU this ticket was planned around (RTX 5070,
#: Blackwell, ``sm_120``). Recorded and compared rather than enforced: another
#: card is perfectly legitimate, and the matmul below is the check that matters.
#: The comparison exists so that "capability (12, 0)" appearing next to a CUDA
#: version below :data:`MIN_BLACKWELL_CUDA` is called out rather than left for a
#: reader to spot.
EXPECTED_CAPABILITY = (12, 0)

#: The oldest CUDA toolkit whose wheels carry ``sm_120`` kernels.
MIN_BLACKWELL_CUDA = (12, 8)


class CudaSmokeError(RuntimeError):
    """Raised when the device cannot do what the caller is about to ask of it."""


def ensure_deterministic_env() -> str:
    """Set ``CUBLAS_WORKSPACE_CONFIG`` before torch is imported (DD11).

    An existing value is respected rather than overwritten: a caller who set it
    deliberately knows something we do not.
    """
    os.environ.setdefault(CUBLAS_ENV_VAR, CUBLAS_ENV_VALUE)
    return os.environ[CUBLAS_ENV_VAR]


def resolve_device(requested: str = "auto") -> str:
    import torch

    if requested != "auto":
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def _version_tuple(version: str | None) -> tuple[int, ...] | None:
    """``"12.8"`` -> ``(12, 8)``. ``None`` for a CPU-only build."""
    if not version:
        return None
    parts: list[int] = []
    for chunk in version.split("."):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts) or None


def device_report(device: str) -> dict:
    """Prove the device can run a kernel, and record what it is.

    The matmul is the whole point. Everything above it is metadata that a broken
    installation reports just as happily as a working one, which is why the last
    field is the only one worth trusting on its own.

    Raises whatever torch raises on a failed launch, deliberately unwrapped: a
    kernel-launch failure is diagnosed from the stack and the CUDA error string,
    not from a summary sentence.
    """
    import torch

    cuda_version = torch.version.cuda
    report: dict = {
        "device": device,
        "torch_version": torch.__version__,
        "torch_cuda_version": cuda_version,
        "cuda_available": torch.cuda.is_available(),
        "deterministic_env": os.environ.get(CUBLAS_ENV_VAR),
    }
    if device.startswith("cuda"):
        index = torch.device(device).index or 0
        capability = tuple(torch.cuda.get_device_capability(index))
        built = _version_tuple(cuda_version)
        report["device_name"] = torch.cuda.get_device_name(index)
        report["compute_capability"] = list(capability)
        report["capability_matches_expected"] = capability == EXPECTED_CAPABILITY
        # A Blackwell card on a pre-12.8 wheel is the specific combination that
        # imports fine and dies at the first kernel. Named here so the printed
        # report says *why* the matmul below is about to fail.
        report["wheel_covers_blackwell"] = (
            None if built is None else built >= MIN_BLACKWELL_CUDA or capability < (12, 0)
        )

    left = torch.randn(64, 64, device=device, dtype=torch.float32)
    result = (left @ left.T).sum().item()
    report["kernel_launch_ok"] = bool(result == result)  # NaN would fail this
    return report


def require_cuda(report: Mapping[str, object]) -> None:
    """Refuse to continue on the CPU when the caller asked for a GPU run.

    Arm B on the CPU is not wrong, it is simply slow enough -- hours rather than
    the two minutes per fold the plan budgets -- that starting one by accident is
    a mistake worth catching in the first second.
    """
    device = str(report.get("device", ""))
    if not device.startswith("cuda"):
        raise CudaSmokeError(
            f"a CUDA device was required but the run resolved to {device!r}. "
            f"torch.cuda.is_available() is {report.get('cuda_available')!r} and this torch was "
            f"built against CUDA {report.get('torch_cuda_version')!r}. Install a wheel built "
            "against CUDA 12.8 or later (see requirements-ml.txt), or pass --device cpu "
            "deliberately"
        )


def format_report(report: Mapping[str, object]) -> list[str]:
    """The report as printable lines, plus whatever it is worth warning about.

    Split out from the printing so a caller can fold these lines into a larger
    log, and so the warning text is covered by a test that needs no GPU.
    """
    lines = [f"{key}: {value}" for key, value in report.items()]
    if report.get("wheel_covers_blackwell") is False:
        lines.append(
            "WARNING: this GPU is Blackwell (sm_120) but torch was built against CUDA "
            f"{report.get('torch_cuda_version')}, which carries no kernel image for it. The "
            "matmul above either failed or was not reached. Install a CUDA 12.8+ wheel; this is "
            "a wheel problem, not a code problem"
        )
    elif report.get("capability_matches_expected") is False:
        lines.append(
            f"note: compute capability is {report.get('compute_capability')}, not the "
            f"{list(EXPECTED_CAPABILITY)} this ticket was planned around. Not a fault -- the "
            "matmul is the check that matters -- but the timings in the plan assume a 5070"
        )
    return lines


def check_device(device: str = "auto", *, cuda_required: bool = False) -> dict:
    """Resolve a device, prove a kernel launches on it, and return the facts.

    Used by the CLI's training commands as their first action, and by
    :func:`main` on its own. The returned dict goes into the metadata sidecar
    verbatim, so a set of weights records the machine that produced it.
    """
    ensure_deterministic_env()
    resolved = resolve_device(device)
    report = device_report(resolved)
    if cuda_required:
        require_cuda(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.encoder_training.smoke_cuda",
        description=(
            "Run a real matmul on the training device and print what it actually is. "
            "Downloads nothing; run it before the encoder smoke test on a new machine."
        ),
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="exit non-zero if the run would fall back to the CPU",
    )
    args = parser.parse_args(argv)

    try:
        report = check_device(args.device, cuda_required=args.require_cuda)
    except CudaSmokeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ModuleNotFoundError as error:
        print(
            f"error: {error}. Install the offline training dependencies first: "
            "pip install -r requirements-ml.txt",
            file=sys.stderr,
        )
        return 2

    for line in format_report(report):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CUBLAS_ENV_VALUE",
    "CUBLAS_ENV_VAR",
    "EXPECTED_CAPABILITY",
    "MIN_BLACKWELL_CUDA",
    "CudaSmokeError",
    "check_device",
    "device_report",
    "ensure_deterministic_env",
    "format_report",
    "require_cuda",
    "resolve_device",
]
