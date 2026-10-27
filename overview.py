"""Queue totals and conservative estimates from observed download timings."""
from pathlib import Path
import shutil
import statistics
import time


def queue_overview(state):
    now = time.time()
    jobs = state["jobs"]
    unfinished = [j for j in jobs if j["status"] in {"queued", "downloading", "converting", "retrying"}]
    running = [j for j in unfinished if j["status"] != "queued"]
    waiting = [j for j in unfinished if j["status"] == "queued"]
    speed = sum(max(0, j.get("speed_bps", 0)) for j in running if j["status"] == "downloading" and now - j.get("progress_at", 0) < 6)
    samples = [j for j in jobs if j["status"] == "done" and j.get("elapsed_seconds", 0) > 0][-20:]

    def typical(job):
        peers = [j for j in samples if j["mode"] == job["mode"]]
        ratios = [j["elapsed_seconds"] / j["duration"] for j in peers if j.get("duration", 0) and j["duration"] > 0]
        if ratios and job.get("duration", 0) and job["duration"] > 0:
            return max(1, statistics.median(ratios) * job["duration"])
        return statistics.median(j["elapsed_seconds"] for j in peers) if peers else None

    eta = 0 if not unfinished else None
    estimates = []
    for job in running:
        seconds = job.get("eta_seconds") if now - job.get("progress_at", 0) < 6 else None
        if seconds is None:
            estimate = typical(job)
            seconds = max(5, estimate * (1 - job.get("progress", 0) / 100)) if estimate else None
        estimates.append(seconds)
    queue_estimates = [typical(j) for j in waiting]
    if unfinished and not (state["paused"] and waiting) and all(n is not None for n in estimates + queue_estimates):
        capacity = state["settings"]["concurrent_downloads"]
        slots = sorted(estimates)[-capacity:]
        slots += [0] * max(0, capacity - len(slots))
        for estimate in queue_estimates:
            slot = slots.index(min(slots))
            slots[slot] += estimate
        eta = round(max(slots))
    completed = sum(j["status"] == "done" for j in jobs)
    skipped = sum(j["status"] == "skipped" for j in jobs)
    errors = sum(j["status"] in {"error", "interrupted"} for j in jobs)
    total = completed + skipped + errors + len(unfinished)
    progress = (completed + skipped + sum(j.get("progress", 0) / 100 for j in running)) / total * 100 if total else 0
    disks = []
    destinations = dict.fromkeys([state["settings"]["folder"]] + [j["folder"] for j in unfinished])
    for folder in destinations:
        try:
            path = Path(folder)
            while not path.exists() and path != path.parent:
                path = path.parent
            usage = shutil.disk_usage(path)
            disks.append({"folder":folder, "free":usage.free, "total":usage.total})
        except OSError:
            disks.append({"folder":folder, "free":None, "total":None})
    return {"speed_bps":speed, "eta_seconds":eta, "completed":completed, "skipped":skipped, "remaining":len(unfinished), "needs_attention":errors, "total":total, "progress":round(min(100, max(0, progress)), 1), "disks":disks}
