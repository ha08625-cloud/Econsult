"""Frozen embeddings for Arm A, and the cache key that makes reuse safe (DD14).

Arm A holds the encoder still and fits a linear probe over its pooled output, so
every example's 768 floats can be computed once and reused across epochs, across
hyperparameters, and across reruns. That is what makes the arm cost seconds
instead of minutes, and it is also the arm's one genuinely dangerous failure
mode: **a stale cache produces numbers that look completely normal and mean
nothing at all.** Nothing crashes, nothing warns, and the report reads fine.

So the cache key is not a convenience. It encodes every input that changes what
an embedding *is*:

* the base model and the exact revision it was loaded at,
* the pooling mode -- mean and CLS are different vectors from the same weights,
* ``max_seq_len``, because truncation changes the pooled vector,
* the dataset's ``generator_version``, seed, signal, fold index and split,
* and a digest of the example ids and texts themselves.

The last one is belt and braces over the rest. Version and seed say which
generator run *should* have produced the file; the digest says which one
actually did. Regenerating a fold after editing a fragment library changes the
texts without necessarily changing either the version or the seed, and the
digest is the only field that notices.

**The key lives in the filename, not in a manifest.** A manifest can drift from
what it labels; a filename cannot. The payload repeats the key and the example
ids so that a file which somehow ends up under the wrong name is still caught on
load rather than trusted.

Torch is imported inside the functions that need it, exactly as
:mod:`.baselines` does with scikit-learn. Everything above the tensors --
the key derivation, the digest, the path convention -- is stdlib and is
therefore covered by CI's unit job, which installs no ML wheels. That matters
here more than anywhere else in the package: the cache key is the part whose
failure is silent.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .dataset import Example, Split

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import torch

    from .model import PooledEncoder

#: Bumped when the *layout* of a cache file changes, as opposed to its contents.
#: Part of the key, so an old file is ignored rather than misread.
CACHE_FORMAT_VERSION = 1

#: Pooling modes (DD3). Mean is the default; CLS exists so the two get compared
#: once rather than argued about, and whichever ran is recorded in the sidecar.
POOLING_MODES = ("mean", "cls")

#: Characters allowed in the model slug that goes into a filename.
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

#: How much of each hash is kept in the filename. Eight hex characters is 32
#: bits; the population being distinguished is a few dozen cache files in one
#: directory, so collision is not the risk being managed here -- readability is.
_HASH_CHARS = 8

#: Fields of a cache payload. Re-checked on load against the split being read.
PAYLOAD_KEYS = ("key", "example_ids", "embeddings")


class EmbedError(RuntimeError):
    """Raised when embeddings cannot be built, or a cache file cannot be trusted."""


@dataclass(frozen=True)
class EmbeddingSpec:
    """Everything about the encoder that changes the vectors it produces.

    ``revision`` is the resolved commit SHA, never the bare model name and never
    a branch. ``emilyalsentzer/Bio_ClinicalBERT`` at ``main`` is not a fixed
    object, and a cache keyed on the name would happily serve vectors from last
    month's weights against this month's report.
    """

    base_model: str
    revision: str
    pooling: str
    max_seq_len: int

    def __post_init__(self) -> None:
        if self.pooling not in POOLING_MODES:
            raise EmbedError(f"pooling must be one of {POOLING_MODES}: {self.pooling!r}")
        if self.max_seq_len < 1:
            raise EmbedError(f"max_seq_len must be positive: {self.max_seq_len}")
        if not self.revision:
            raise EmbedError(
                "an embedding cache cannot be keyed without a resolved model revision; pass "
                "--revision, or load the model from a source that reports its commit SHA"
            )

    @property
    def slug(self) -> str:
        """The model name, reduced to something a filename can hold."""
        return _SLUG_UNSAFE.sub("-", self.base_model).strip("-").lower()

    def to_dict(self) -> dict:
        return {
            "base_model": self.base_model,
            "revision": self.revision,
            "pooling": self.pooling,
            "max_seq_len": self.max_seq_len,
        }


def content_digest(examples: Sequence[Example]) -> str:
    """Digest of the example ids and texts, in order.

    The field that catches a regenerated dataset whose version and seed did not
    change -- an edited fragment library, say. Ids as well as texts, because two
    splits can legitimately contain the same sentence and must still key
    differently.
    """
    digest = hashlib.sha256()
    for example in examples:
        digest.update(example.example_id.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(example.text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def cache_key(
    spec: EmbeddingSpec,
    *,
    signal: str,
    fold_index: object,
    split: str,
    generator_version: object,
    dataset_seed: object,
    digest: str,
) -> str:
    """The full cache key, as the readable string that becomes a filename.

    Readable rather than one opaque hash so that a directory listing says what
    each file is, and so a mismatch is diagnosable without a script. The one
    hashed component is the content digest, which has no readable form.
    """
    return ".".join(
        (
            f"v{CACHE_FORMAT_VERSION}",
            spec.slug,
            f"rev-{spec.revision[:_HASH_CHARS]}",
            f"pool-{spec.pooling}",
            f"len{spec.max_seq_len}",
            f"{signal}",
            f"gen{generator_version}",
            f"seed{dataset_seed}",
            f"fold{fold_index}",
            split,
            f"d-{digest[:_HASH_CHARS]}",
        )
    )


def split_cache_key(spec: EmbeddingSpec, split: Split, *, signal: str) -> str:
    """The cache key for one loaded split, read from its own sidecar.

    The dataset seed comes from the sidecar rather than from a CLI flag on
    purpose: a flag records what the caller believes, and the sidecar records
    what the generator did.
    """
    if "seed" not in split.stats:
        raise EmbedError(
            f"{split.path} has no 'seed' in its sidecar, so an embedding cache keyed on it "
            "cannot be built. Regenerate the dataset rather than caching against an unknown seed"
        )
    return cache_key(
        spec,
        signal=signal,
        fold_index=split.fold_index,
        split=split.name,
        generator_version=split.generator_version,
        dataset_seed=split.stats["seed"],
        digest=content_digest(split.examples),
    )


def cache_path(directory: Path | str, key: str) -> Path:
    """Where the cache file for ``key`` lives."""
    return Path(directory) / f"{key}.pt"


def split_cache_path(
    directory: Path | str, spec: EmbeddingSpec, split: Split, *, signal: str
) -> Path:
    return cache_path(directory, split_cache_key(spec, split, signal=signal))


# ---------------------------------------------------------------------------
# Everything below needs torch
# ---------------------------------------------------------------------------


def _load_cached(path: Path, key: str, example_ids: Sequence[str]) -> torch.Tensor | None:
    """Read a cache file, or return ``None`` if there is nothing usable there.

    A file that exists but disagrees with the split is an error, not a miss.
    Rebuilding over it silently would hide whichever of the two is wrong, and
    the whole point of the key is that a disagreement gets noticed.
    """
    import torch

    if not path.is_file():
        return None

    payload = torch.load(path, map_location="cpu", weights_only=True)
    missing = [field for field in PAYLOAD_KEYS if field not in payload]
    if missing:
        raise EmbedError(f"{path} is not an embedding cache file: missing {', '.join(missing)}")
    if payload["key"] != key:
        raise EmbedError(
            f"{path} holds embeddings keyed {payload['key']!r} but is named for {key!r}. One of "
            "the two is a lie; delete the file rather than guessing which"
        )
    cached_ids = list(payload["example_ids"])
    if cached_ids != list(example_ids):
        raise EmbedError(
            f"{path} holds {len(cached_ids)} example ids that do not match the {len(example_ids)} "
            "in the split it is keyed to, in order. The cache and the dataset have diverged"
        )
    embeddings = payload["embeddings"]
    if embeddings.shape[0] != len(cached_ids):
        raise EmbedError(
            f"{path} holds {embeddings.shape[0]} vectors for {len(cached_ids)} examples"
        )
    return embeddings


def _write_cache(
    path: Path, key: str, example_ids: Sequence[str], embeddings: torch.Tensor
) -> None:
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    # Written to a sibling and moved, so an interrupted run leaves no file that
    # looks complete. A truncated cache is the one failure the key cannot catch.
    temporary = path.with_suffix(path.suffix + ".partial")
    torch.save(
        {"key": key, "example_ids": list(example_ids), "embeddings": embeddings.cpu()}, temporary
    )
    temporary.replace(path)


def embed_split(
    split: Split,
    encoder: PooledEncoder,
    *,
    batch_size: int = 64,
    progress: bool = False,
) -> torch.Tensor:
    """Pooled embeddings for every example in a split, in order.

    Order is the contract: the returned rows line up with ``split.examples``,
    and the cache re-checks it by id on every load.
    """
    texts = [example.text for example in split.examples]
    return encoder.embed(texts, batch_size=batch_size, progress=progress)


def load_or_build(
    split: Split,
    encoder: PooledEncoder,
    *,
    signal: str,
    directory: Path | str,
    batch_size: int = 64,
    progress: bool = False,
) -> tuple[torch.Tensor, Path, bool]:
    """Return this split's embeddings, from cache when the key matches.

    Returns the tensor, the path it is cached at, and whether it was a hit --
    the last so a caller can report cache hits rather than leaving a reader to
    wonder whether the encoder ran at all.
    """
    spec = encoder.spec
    key = split_cache_key(spec, split, signal=signal)
    path = cache_path(directory, key)

    example_ids = [example.example_id for example in split.examples]
    cached = _load_cached(path, key, example_ids)
    if cached is not None:
        return cached, path, True

    embeddings = embed_split(split, encoder, batch_size=batch_size, progress=progress)
    _write_cache(path, key, example_ids, embeddings)
    return embeddings, path, False


__all__ = [
    "CACHE_FORMAT_VERSION",
    "POOLING_MODES",
    "EmbedError",
    "EmbeddingSpec",
    "cache_key",
    "cache_path",
    "content_digest",
    "embed_split",
    "load_or_build",
    "split_cache_key",
    "split_cache_path",
]
