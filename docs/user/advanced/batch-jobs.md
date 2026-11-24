# Batch Jobs and Non-Interactive Execution

Submit long-running jobs and check results later - HPC-style workflows.

> **Note:** In examples below, replace `<project-name>` with your actual project name. The `$(id -u)` part auto-substitutes your user ID.

---

## Overview

**Batch job pattern:**
1. Submit job to container
2. Job runs in background
3. Results written to workspace
4. Check logs/results later

**No babysitting needed.**

---

## Basic Pattern

```bash
# Create container
container-create training --gpu=2

# Submit job (non-interactive)
docker exec -d training._.$(id -u) \
  nohup python /workspace/train.py > /workspace/training.log 2>&1

# Job runs for hours/days
# You can disconnect, container keeps running

# Check progress later
tail -f ~/workspace/training.log

# Or check GPU usage
nvidia-smi
```

---

## With nohup

**Standard approach:**

```bash
docker exec -d <project-name>._.$(id -u) \
  nohup python /workspace/train.py \
  > /workspace/output.log 2>&1 &
```

**Components:**
- `docker exec -d` - Detached mode (background)
- `nohup` - Ignore hangup signals (survives disconnects)
- `> /workspace/output.log` - Redirect stdout
- `2>&1` - Redirect stderr to stdout
- `&` - Run in background

---

## Parameter Sweep Example

**Run multiple experiments:**

```bash
#!/bin/bash
# sweep.sh

for lr in 0.001 0.01 0.1; do
  for batch_size in 16 32 64; do
    NAME="exp-lr${lr}-bs${batch_size}"

    # Create container
    container-create $NAME --gpu=1 --background

    # Submit job
    docker exec -d $NAME._.$(id -u) \
      nohup python /workspace/train.py \
      --lr=$lr \
      --batch-size=$batch_size \
      > /workspace/logs/${NAME}.log 2>&1

    echo "Submitted: $NAME"
  done
done

echo "All jobs submitted. Monitor with:"
echo "tail -f ~/workspace/logs/*.log"
```

---

## Monitoring Jobs

**Check running processes:**

```bash
# All your containers
docker ps --filter label=DS01_USER=$(id -u)

# Processes in specific container
docker exec <project-name>._.$(id -u) ps aux | grep python

# GPU usage
nvidia-smi

# Live monitoring
watch -n 1 nvidia-smi
```

**Check logs:**

```bash
# Follow log
tail -f ~/workspace/training.log

# Last 100 lines
tail -100 ~/workspace/training.log

# Search logs
grep "epoch" ~/workspace/training.log

# Multiple logs
tail -f ~/workspace/logs/*.log
```

---

## Job Completion Detection

**Wait for job to finish:**

```bash
#!/bin/bash

PROJECT=my-training

# Submit job
docker exec -d $PROJECT._.$(id -u) \
  nohup python /workspace/train.py > /workspace/output.log 2>&1

# Wait for completion
while docker exec $PROJECT._.$(id -u) pgrep -f train.py > /dev/null; do
  echo "Job still running..."
  sleep 60
done

echo "Job completed!"

# Collect results
cat ~/workspace/output.log
```

---

## Error Handling

**Check exit codes:**

```bash
# Run job
docker exec <project-name>._.$(id -u) \
  python /workspace/train.py
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "Success!"
else
  echo "Failed with code $EXIT_CODE"
  docker logs <project-name>._.$(id -u)
fi
```

---

## Checkpointing

**Save progress regularly:**

```python
# In train.py
for epoch in range(num_epochs):
    train_one_epoch()

    # Save checkpoint
    if epoch % 5 == 0:
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
        }, f'/workspace/checkpoints/epoch_{epoch}.pt')
```

**Resume if interrupted:**

```python
# Load checkpoint if exists
checkpoint_path = '/workspace/checkpoints/latest.pt'
if os.path.exists(checkpoint_path):
    checkpoint = torch.load(checkpoint_path)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    start_epoch = checkpoint['epoch'] + 1
else:
    start_epoch = 0
```

---

## Notifications

**DS01 can't send email.** There's no mail server on the host or in containers, and Hertie's mail system doesn't accept mail sent from scripts. Installing `mail` or `sendmail` won't help.

Use a push notification instead. [ntfy](https://ntfy.sh) needs no account, and it only needs `curl`, which every DS01 image includes.

**1. Pick a topic and subscribe to it.** A topic is just a name. Generate one that's hard to guess:

```bash
echo ds01-$(openssl rand -hex 6)    # e.g. ds01-a812c99de5ce
```

Subscribe to it in the ntfy app (iOS / Android) or at `https://ntfy.sh/<your-topic>` in a browser.

> **Topics are public.** Anyone who knows the name can read the messages. Keep the name unguessable, and don't put anything sensitive in a message.

**2. Send a message when the job finishes or fails.** Set `NTFY_TOPIC` in the shell that starts the job, then use one of these:

```bash
# Bash: one message either way
export NTFY_TOPIC=ds01-a812c99de5ce
python train.py \
  && curl -sS -o /dev/null -d "run finished" ntfy.sh/$NTFY_TOPIC \
  || curl -sS -o /dev/null -d "run failed" ntfy.sh/$NTFY_TOPIC
```

```python
# Python: standard library only
import os
import urllib.request

def notify(msg: str) -> None:
    url = f"https://ntfy.sh/{os.environ['NTFY_TOPIC']}"
    urllib.request.urlopen(url, data=msg.encode(), timeout=15)

try:
    main()
    notify("run finished")
except Exception as e:
    notify(f"run failed: {e}")
    raise
```

```r
# R: no packages needed
notify <- function(msg, topic = Sys.getenv("NTFY_TOPIC")) {
  system2("curl", c("-sS", "-m", "15", "-o", "/dev/null", "-d", shQuote(msg),
                    paste0("https://ntfy.sh/", topic)))
}

tryCatch({
  main()
  notify("run finished")
}, error = function(e) {
  notify(paste("run failed:", conditionMessage(e)))
  stop(e)
})
```

The Python and R versions re-raise the error, so the job still exits with a failure and your log shows the traceback.

None of these fire if the container itself is stopped (for example during [monthly maintenance](../core-guides/long-running-jobs.md#monthly-maintenance)), because the script is killed with it. For long runs, have the script also send a message every few hours: if the messages stop, the job has stopped.

---

## Best Practices

1. **Always write to `/workspace`:** Anything written elsewhere in the container (like `/tmp` or `/root`) vanishes when the container is removed. Your training ran for 12 hours, saved the model to `/home/model.pt`, you retired the container - model gone. Always use `/workspace/` which is mounted from the host and persists.

2. **Use clear log names:** When you're running a parameter sweep with 50 experiments, `output.log` tells you nothing. Use `exp-lr0.001-bs32-seed42.log` - you can grep for specific hyperparameters, sort by parameter values, and immediately know which experiment produced which results without opening each file.

3. **Save checkpoints frequently:** GPU jobs get interrupted - idle timeouts, server maintenance, OOM errors. If you only save at the end, 23 hours of training is lost. Save every N epochs to `/workspace/checkpoints/`. When restarting, load the latest checkpoint and continue from where you left off instead of starting over.

4. **Log hyperparameters:** At the start of your training script, write all hyperparameters to the log file: learning rate, batch size, model architecture, random seed. Three months later when you're writing your thesis, you'll need to know exactly what settings produced your best model. The log file is your lab notebook.

5. **Clean up finished jobs:** Each running container holds a GPU allocation. If you submit 10 experiments and forget to clean up, you're blocking 10 GPUs even though the jobs finished hours ago. Add cleanup to your scripts, or periodically run `container-list` and retire finished experiments.

---

## Example: Full Pipeline

```bash
#!/bin/bash
# pipeline.sh

set -e

PROJECT="my-training"
LOG_DIR=~/workspace/logs
CHECKPOINT_DIR=~/workspace/checkpoints

mkdir -p $LOG_DIR $CHECKPOINT_DIR

# Create container
container-create $PROJECT --gpu=2 || exit 1

# Submit job
docker exec -d $PROJECT._.$(id -u) bash -c "
  cd /workspace
  python train.py \
    --epochs=100 \
    --lr=0.001 \
    --batch-size=32 \
    --checkpoint-dir=/workspace/checkpoints \
    > /workspace/logs/training.log 2>&1
"

echo "Job submitted. Monitor with:"
echo "  tail -f $LOG_DIR/training.log"
echo ""
echo "Check GPU usage:"
echo "  nvidia-smi"
echo ""
echo "When complete, collect results from:"
echo "  $CHECKPOINT_DIR/"
```

---

## See Also

- → [Terminal Workflows](terminal-workflows.md) - CLI development patterns

- → [Docker Direct](docker-direct.md) - Docker commands

- → [Scripting](../intermediate/scripting-bash.md) - Automation patterns
