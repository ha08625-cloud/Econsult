# Overnight GPU job queue

Local development only. Never deployed, never used in CI.

Runs one job at a time, unattended, in filename order. It exists because the GPU
is idle most of the week and the runs are hours long: the point is to queue an
evening's worth of work and read the logs in the morning.

## Use

Write a job — any shell script, one per run:

```
cat > gpu_queue/jobs/01-noise-transfer.sh <<'END'
python -m scripts.encoder_training finetune ...
END
```

Start the runner:

```
./gpu_queue/run.sh            # drains the queue, then exits
./gpu_queue/run.sh --watch    # stays up; add jobs any time from another terminal
```

Leave it running overnight with `nohup` if you are closing the terminal:

```
nohup ./gpu_queue/run.sh --watch > gpu_queue/runner.log 2>&1 &
```

In the morning:

```
ls gpu_queue/done gpu_queue/failed      # what succeeded, what did not
tail -40 gpu_queue/logs/*.log           # why
```

## What it does and does not do

**Jobs run in filename order**, so number them: `01-`, `02-`. A job is picked up
by re-scanning the directory each time, so a job added at midnight runs after
the one already going.

**A failing job does not stop the queue.** The runs are independent tickets and
losing a night's work to the first one's typo is the failure this exists to
prevent. Failed jobs land in `failed/` with their log; successful ones in
`done/`. A job interrupted mid-run stays in `running/`, which is how you tell
"killed" from "failed".

**Every log records its own provenance** — git SHA, whether the tree was dirty,
free disk, GPU, and the torch and transformers versions. That last one is not
decoration: the 2026-08-31 noise sweep's comparability rests on all its cells
having run on transformers 5.14.1, and nothing in the run artefacts records it.
A queue that spans a `pip install` will otherwise mix stacks silently.

**It refuses to start a job under 20GB free** (`MIN_FREE_GB` to change). Arm B
weights are ~440MB per fold; a queue of runs writing weights will fill a disk at
3am and fail everything after it. Pass `--no-weights` on any run whose encoders
you do not need to keep.

**It is not a scheduler.** No priorities, no parallelism, no resume. One GPU, one
job at a time, which is the whole requirement. If you outgrow it, `task-spooler`
(`apt install task-spooler`) is the standard tool for this and does the same
thing with more features.

## Writing a job well

* **Pin what matters at the top of the job**, not in your shell. A job that
  depends on the ambient environment is a job you cannot re-read in the morning.
* **Redirect nothing** — the runner captures stdout and stderr already.
* **Make it idempotent where you can.** A job that refuses to overwrite is better
  than one that half-overwrites; the training CLI already refuses a non-empty
  output directory without `--force`.
* **Put the dataset generation in the same job as the run that needs it**, so a
  missing tree fails that job rather than the next three.
