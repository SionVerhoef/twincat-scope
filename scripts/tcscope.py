#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pyarrow", "matplotlib"]
# ///
"""Create TwinCAT 3 Scope configurations and triage the data they record.

A scope recording is far too large to read. Ten minutes of twenty channels at
1 kHz is twelve million samples; pasting any part of that into a conversation
burns the context window and still misses the three-millisecond transient that
caused the fault. So this tool never returns samples. It returns summaries,
events and pictures, and only hands back real rows once a time range is known.

Subcommands, acquisition side (no third-party imports needed):
  doctor      Check the environment and say how to fix what is missing
  newscope    Write a .tcscopex from a template, with fresh GUIDs
  checkscope  Validate a .tcscopex and warn about recording load

Subcommands, analysis side (needs numpy; run under `uv run`):
  ingest      Convert an export (.svdx / CSV) to Parquet, once
  manifest    Channels, units, sample rate, duration, gaps
  stats       Per-channel distribution and health numbers
  events      Steps, spikes, flatlines, clipping, threshold crossings
  plot        PNG using a min/max envelope, so transients survive
  window      Real rows, for a narrow time range only
  correlate   Cross-channel correlation and lag

Every subcommand prints JSON on stdout. Errors print JSON too, with a "fix"
field, and exit non-zero.

Status: the .tcscopex writer is modelled on real Beckhoff sample files but has
not been opened in TwinCAT. The CSV reader has not been run against genuine
TC3ScopeExportTool.exe output. Both say so rather than implying otherwise.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

BOM = b"\xef\xbb\xbf"
XML_DECL = '<?xml version="1.0" encoding="utf-8"?>'

# A .tcscopex sample time is expressed in 100 ns ticks.
TICKS_PER_MS = 10_000

# Above this, a recording starts to compete with the machine it is diagnosing.
# Directional, not a benchmark - see references/recording-load.md.
LOAD_WARN_SAMPLES_PER_S = 100_000


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------

def emit(obj):
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def fail(message, fix=None):
    out = {"ok": False, "error": message}
    if fix:
        out["fix"] = fix
    emit(out)
    raise SystemExit(1)


def need(module):
    """Import a heavy dependency, or explain how to get it.

    Imports stay inside the subcommands that need them so `doctor`, `newscope`
    and `checkscope` keep working under a bare interpreter, before uv exists.
    """
    try:
        return __import__(module)
    except ImportError:
        fail(
            f"{module} is not available",
            "Run this through uv, which installs dependencies automatically: "
            f"uv run {Path(__file__).name} ...",
        )


# --------------------------------------------------------------------------
# CSV sniffing
#
# TC3ScopeExportTool.exe writes a preamble of name/value pairs, then a header
# row, then data. On a Dutch or German Windows the delimiter is ';' and the
# decimal separator is ',' - a reader that assumes ',' and '.' turns a European
# export into one garbage column, or silently reads 1,5 as 15.
# --------------------------------------------------------------------------

def _looks_numeric(field, decimal):
    field = field.strip()
    if not field:
        return False
    if decimal == ",":
        field = field.replace(".", "").replace(",", ".")
    try:
        float(field)
        return True
    except ValueError:
        return False


def sniff_csv(path, sample_bytes=200_000):
    """Work out delimiter, decimal separator, header row and channel names."""
    with open(path, "rb") as fh:
        text = fh.read(sample_bytes).decode("utf-8-sig", errors="replace")
    # Indices below are into the raw line list, blanks included, because
    # load_csv slices the same raw list. Filtering here and slicing there is
    # how the header row ends up parsed as a row of NaN.
    lines = text.splitlines()
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    if not nonblank:
        fail(f"{path} is empty")

    best = None
    for delim in (";", ",", "\t"):
        counts = [lines[i].count(delim) for i in nonblank[-20:]]
        if not counts or max(counts) == 0:
            continue
        modal = max(set(counts), key=counts.count)
        if modal == 0:
            continue
        consistency = counts.count(modal) / len(counts)
        if best is None or consistency > best[1]:
            best = (delim, consistency, modal + 1)
    if best is None:
        fail(
            f"could not find a delimiter in {path}",
            "Inspect the file with: tcscope.py manifest <file> --dump-header",
        )
    delim, _, ncols = best

    # A ';' file almost always means the European decimal comma.
    decimal = "," if delim == ";" else "."

    data_start = None
    for i in nonblank:
        fields = lines[i].split(delim)
        if len(fields) != ncols:
            continue
        numeric = sum(_looks_numeric(f, decimal) for f in fields)
        if numeric >= max(1, len(fields) // 2):
            data_start = i
            break
    if data_start is None:
        fail(
            f"found no numeric rows in {path}",
            "Check this really is a Scope export: tcscope.py manifest <file> --dump-header",
        )

    header_idx, names = None, []
    for i in range(data_start - 1, -1, -1):
        if not lines[i].strip():
            continue
        fields = [f.strip().strip('"') for f in lines[i].split(delim)]
        if len(fields) == ncols and any(f and not _looks_numeric(f, decimal) for f in fields):
            header_idx, names = i, fields
            break
    if not names:
        names = [f"col{i}" for i in range(ncols)]

    return {
        "delimiter": delim,
        "decimal": decimal,
        "columns": ncols,
        "header_row": header_idx,
        "data_row": data_start,
        "names": names,
        "preamble": [lines[i] for i in range(header_idx)] if header_idx else [],
    }


def _parse_float(field, decimal):
    field = field.strip()
    if not field:
        return float("nan")
    if decimal == ",":
        field = field.replace(".", "").replace(",", ".")
    try:
        return float(field)
    except ValueError:
        return float("nan")


def load_csv(path):
    """Read a Scope CSV export into (names, 2-D float array)."""
    np = need("numpy")
    info = sniff_csv(path)
    delim, decimal = info["delimiter"], info["decimal"]

    rows = []
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig", errors="replace")
    for ln in text.splitlines()[info["data_row"]:]:
        if not ln.strip():
            continue
        fields = ln.split(delim)
        if len(fields) != info["columns"]:
            continue
        rows.append([_parse_float(f, decimal) for f in fields])
    if not rows:
        fail(f"no parsable data rows in {path}")
    return info["names"], np.asarray(rows, dtype=float), info


def load_parquet(path):
    need("pyarrow")
    np = need("numpy")
    from pyarrow import parquet as pq
    table = pq.read_table(path)
    names = list(table.column_names)
    data = np.column_stack([table.column(n).to_numpy(zero_copy_only=False) for n in names])
    return names, data.astype(float), {"source": "parquet"}


def load(path):
    path = Path(path)
    if not path.exists():
        fail(f"{path} does not exist")
    if path.suffix.lower() == ".parquet":
        return load_parquet(path)
    if path.suffix.lower() in (".csv", ".txt"):
        return load_csv(path)
    if path.suffix.lower() == ".svdx":
        fail(
            f"{path} is a raw Scope recording",
            "Convert it first: tcscope.py ingest <file.svdx> -o rec.parquet",
        )
    return load_csv(path)


def split_time(names, data):
    """Return (time, channel_names, channel_data). Column 0 is time by convention."""
    lowered = [n.lower() for n in names]
    idx = 0
    for i, n in enumerate(lowered):
        if "time" in n or n in ("t", "sample"):
            idx = i
            break
    t = data[:, idx]
    keep = [i for i in range(data.shape[1]) if i != idx]
    return t, [names[i] for i in keep], data[:, keep]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def config_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "tcscope"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tcscope"


EXPORT_TOOL_CANDIDATES = [
    r"C:\TwinCAT\Functions\TE1300-Scope-View",
    r"C:\TwinCAT\Functions\TF3300-Scope-Server",
    r"C:\Program Files (x86)\Beckhoff\TwinCAT\Functions",
    r"C:\Program Files\Beckhoff\TwinCAT\Functions",
]


def find_export_tool():
    """Locate TC3ScopeExportTool.exe. Discover, never hardcode."""
    env = os.environ.get("TCSCOPE_EXPORT_TOOL")
    if env and Path(env).exists():
        return env
    cached = config_dir() / "config.json"
    if cached.exists():
        try:
            got = json.loads(cached.read_text()).get("export_tool")
            if got and Path(got).exists():
                return got
        except (ValueError, OSError):
            pass
    on_path = shutil.which("TC3ScopeExportTool.exe")
    if on_path:
        return on_path
    for root in EXPORT_TOOL_CANDIDATES:
        base = Path(root)
        if not base.exists():
            continue
        for hit in base.rglob("TC3ScopeExportTool.exe"):
            return str(hit)
    return None


def cmd_doctor(args):
    checks = []

    def add(name, ok, detail, fix=None):
        row = {"check": name, "ok": bool(ok), "detail": detail}
        if fix and not ok:
            row["fix"] = fix
        checks.append(row)

    add("python", sys.version_info >= (3, 11),
        f"Python {sys.version.split()[0]}",
        "Install Python 3.11 or newer, or run through uv.")

    uv = shutil.which("uv")
    add("uv", uv is not None, uv or "not found",
        "winget install --id=astral-sh.uv -e   (no admin rights needed)")

    for mod in ("numpy", "pyarrow", "matplotlib"):
        try:
            __import__(mod)
            add(mod, True, "importable")
        except ImportError:
            add(mod, False, "not importable",
                f"uv run {Path(__file__).name} ... installs it automatically")

    tool = find_export_tool()
    add("TC3ScopeExportTool.exe", tool is not None, tool or "not found",
        "Set TCSCOPE_EXPORT_TOOL to its full path. It ships with TE130x Scope "
        "View and TF3300 Scope Server.")

    cfg = config_dir()
    try:
        cfg.mkdir(parents=True, exist_ok=True)
        probe = cfg / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
        add("cache directory", True, str(cfg))
    except OSError as exc:
        add("cache directory", False, f"{cfg}: {exc}", "Set XDG_CONFIG_HOME or LOCALAPPDATA.")

    if tool:
        try:
            cfg.mkdir(parents=True, exist_ok=True)
            (cfg / "config.json").write_text(json.dumps({"export_tool": tool}, indent=2))
        except OSError:
            pass

    ok = all(c["ok"] for c in checks if c["check"] not in ("TC3ScopeExportTool.exe",))
    emit({"ok": ok, "checks": checks,
          "note": "TC3ScopeExportTool.exe is only needed to read .svdx files. "
                  "CSV and Parquet analysis works without it."})
    return 0 if ok else 1


# --------------------------------------------------------------------------
# ingest / manifest
# --------------------------------------------------------------------------

def cmd_ingest(args):
    src = Path(args.input)
    if not src.exists():
        fail(f"{src} does not exist")

    if src.suffix.lower() == ".svdx":
        tool = find_export_tool()
        if not tool:
            fail("TC3ScopeExportTool.exe not found",
                 "Set TCSCOPE_EXPORT_TOOL, or run: tcscope.py doctor")
        csv_out = src.with_suffix(".csv")
        cmd = [tool, f"svd={src}", f"target={csv_out}", "silent"]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            fail(f"export tool failed: {exc}",
                 f"Try running it by hand: {' '.join(cmd)}")
        src = csv_out

    names, data, info = load_csv(src)
    out = Path(args.output)
    pa = need("pyarrow")
    from pyarrow import parquet as pq
    table = pa.table({n: data[:, i] for i, n in enumerate(names)})
    pq.write_table(table, out)
    emit({"ok": True, "input": str(args.input), "output": str(out),
          "rows": int(data.shape[0]), "columns": names,
          "delimiter": info.get("delimiter"), "decimal": info.get("decimal"),
          "note": "CSV layout was sniffed, not verified against a real export."})
    return 0


def cmd_manifest(args):
    if args.dump_header:
        with open(args.input, "rb") as fh:
            head = fh.read(4000).decode("utf-8-sig", errors="replace")
        emit({"ok": True, "raw_head": head.splitlines()[:40]})
        return 0

    names, data, info = load(args.input)
    np = need("numpy")
    t, chans, values = split_time(names, data)

    dt = np.diff(t)
    dt = dt[np.isfinite(dt)]
    median_dt = float(np.median(dt)) if dt.size else float("nan")
    gaps = int(np.sum(dt > 3 * median_dt)) if dt.size and median_dt > 0 else 0

    emit({
        "ok": True,
        "file": str(args.input),
        "rows": int(data.shape[0]),
        "duration": float(t[-1] - t[0]) if t.size > 1 else 0.0,
        "median_sample_interval": median_dt,
        "estimated_rate_hz": (1.0 / median_dt) if median_dt and median_dt > 0 else None,
        "gaps": gaps,
        "channels": [
            {"name": n,
             "nan_fraction": float(np.mean(~np.isfinite(values[:, i]))),
             "constant": bool(np.nanmax(values[:, i]) == np.nanmin(values[:, i]))}
            for i, n in enumerate(chans)
        ],
        "delimiter": info.get("delimiter"),
        "decimal": info.get("decimal"),
    })
    return 0


# --------------------------------------------------------------------------
# stats / events / correlate / window
# --------------------------------------------------------------------------

def select(chans, values, wanted):
    if not wanted:
        return chans, values
    want = [w.strip() for w in wanted.split(",")]
    idx = [i for i, n in enumerate(chans) if n in want]
    if not idx:
        fail(f"no channel matched {wanted}", f"Available: {', '.join(chans)}")
    return [chans[i] for i in idx], values[:, idx]


def cmd_stats(args):
    np = need("numpy")
    names, data, _ = load(args.input)
    _, chans, values = split_time(names, data)
    chans, values = select(chans, values, args.channels)

    out = []
    for i, name in enumerate(chans):
        col = values[:, i]
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            out.append({"name": name, "error": "all values are NaN"})
            continue
        lo, hi = float(np.min(finite)), float(np.max(finite))
        diffs = np.abs(np.diff(np.unique(finite)))
        out.append({
            "name": name,
            "min": lo, "max": hi,
            "mean": float(np.mean(finite)),
            "std": float(np.std(finite)),
            "rms": float(np.sqrt(np.mean(finite ** 2))),
            "p01": float(np.percentile(finite, 1)),
            "p50": float(np.percentile(finite, 50)),
            "p99": float(np.percentile(finite, 99)),
            "pct_at_max": float(np.mean(finite == hi) * 100),
            "pct_at_min": float(np.mean(finite == lo) * 100),
            "pct_flat": float(np.mean(np.abs(np.diff(finite)) == 0) * 100) if finite.size > 1 else 0.0,
            "quantisation_step": float(np.min(diffs)) if diffs.size else 0.0,
        })
    emit({"ok": True, "channels": out})
    return 0


def cmd_events(args):
    np = need("numpy")
    names, data, _ = load(args.input)
    t, chans, values = split_time(names, data)
    chans, values = select(chans, values, args.channels)

    found = []
    for i, name in enumerate(chans):
        col = values[:, i]
        ok = np.isfinite(col)
        if ok.sum() < 8:
            continue
        d = np.diff(col)
        d = np.where(np.isfinite(d), d, 0.0)
        mad = float(np.median(np.abs(d - np.median(d)))) or float(np.std(d)) or 0.0

        if mad > 0:
            # A step goes and stays; a spike comes back. The return edge can be
            # several samples away - a 3-sample spike puts it at j+3 - so look
            # ahead over a window rather than at d[j+1] alone, or every spike
            # gets reported twice as a pair of steps.
            big = np.flatnonzero(np.abs(d) > args.sigma * mad * 1.4826)
            reported = set()
            for j in big:
                if j in reported:
                    continue
                horizon = min(j + args.spike_width + 1, d.size)
                partner = None
                for k in range(j + 1, horizon):
                    if np.sign(d[k]) != np.sign(d[j]) and abs(d[k]) > 0.5 * abs(d[j]):
                        partner = k
                        break
                if partner is not None:
                    reported.update(range(j, partner + 1))
                found.append({
                    "channel": name,
                    "kind": "spike" if partner is not None else "step",
                    "time": float(t[min(j + 1, t.size - 1)]),
                    "index": int(j + 1),
                    "delta": float(d[j]),
                    **({"width_samples": int(partner - j)} if partner is not None else {}),
                })

        lo, hi = float(np.nanmin(col)), float(np.nanmax(col))
        for edge, value in (("max", hi), ("min", lo)):
            frac = float(np.mean(col[ok] == value))
            if frac > args.clip_fraction:
                found.append({"channel": name, "kind": "clipping",
                              "edge": edge, "value": value,
                              "fraction": frac})

        flat = np.abs(d) == 0
        run, start = 0, 0
        for k, is_flat in enumerate(flat):
            if is_flat:
                run = run + 1 if run else 1
                start = k - run + 1
            else:
                if run >= args.flat_samples:
                    found.append({"channel": name, "kind": "flatline",
                                  "time": float(t[start]),
                                  "samples": int(run)})
                run = 0
        if run >= args.flat_samples:
            found.append({"channel": name, "kind": "flatline",
                          "time": float(t[start]), "samples": int(run)})

        if args.threshold is not None:
            crossings = np.flatnonzero(np.diff((col > args.threshold).astype(int)) != 0)
            for j in crossings[:args.max_events]:
                found.append({"channel": name, "kind": "crossing",
                              "time": float(t[j + 1]), "threshold": args.threshold})

    found.sort(key=lambda e: e.get("time", 0.0))
    emit({"ok": True, "count": len(found), "events": found[:args.max_events],
          "truncated": len(found) > args.max_events})
    return 0


def cmd_correlate(args):
    np = need("numpy")
    names, data, _ = load(args.input)
    t, chans, values = split_time(names, data)
    chans, values = select(chans, values, args.channels)
    if len(chans) < 2:
        fail("correlate needs at least two channels")

    clean = np.where(np.isfinite(values), values, 0.0)
    corr = np.corrcoef(clean, rowvar=False)

    dt = float(np.median(np.diff(t))) if t.size > 1 else 1.0
    pairs = []
    for a in range(len(chans)):
        for b in range(a + 1, len(chans)):
            x = clean[:, a] - clean[:, a].mean()
            y = clean[:, b] - clean[:, b].mean()
            n = min(x.size, args.max_lag_samples)
            xc = np.correlate(x[:n], y[:n], mode="same")
            lag = int(np.argmax(xc) - n // 2)
            pairs.append({
                "a": chans[a], "b": chans[b],
                "correlation": float(corr[a, b]),
                "lag_samples": lag,
                "lag_seconds": lag * dt,
                "leads": chans[a] if lag < 0 else (chans[b] if lag > 0 else "simultaneous"),
            })
    pairs.sort(key=lambda p: -abs(p["correlation"]))
    emit({"ok": True, "pairs": pairs})
    return 0


def cmd_window(args):
    np = need("numpy")
    names, data, _ = load(args.input)
    t, chans, values = split_time(names, data)
    chans, values = select(chans, values, args.channels)

    mask = (t >= args.start) & (t <= args.end)
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        fail(f"no samples between {args.start} and {args.end}",
             f"The recording spans {float(t[0])} to {float(t[-1])}.")
    if idx.size > args.max_rows:
        fail(
            f"that window holds {idx.size} rows, over the {args.max_rows} cap",
            "Narrow the range, or raise --max-rows deliberately. This cap exists "
            "so a wide window cannot flood the context window.",
        )
    emit({
        "ok": True,
        "channels": chans,
        "rows": [
            {"time": float(t[i]), **{c: float(values[i, j]) for j, c in enumerate(chans)}}
            for i in idx
        ],
    })
    return 0


# --------------------------------------------------------------------------
# plot - min/max envelope, never decimation
# --------------------------------------------------------------------------

def cmd_plot(args):
    np = need("numpy")
    need("matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names, data, _ = load(args.input)
    t, chans, values = split_time(names, data)
    chans, values = select(chans, values, args.channels)

    buckets = max(64, args.width)
    fig, axes = plt.subplots(len(chans), 1, figsize=(args.width / 100, 2.2 * len(chans)),
                             sharex=True, squeeze=False)
    for i, name in enumerate(chans):
        col = values[:, i]
        ax = axes[i][0]
        if col.size <= buckets:
            ax.plot(t, col, linewidth=0.8)
        else:
            # One bucket per pixel column, drawn as its min-max band. Plain
            # decimation would drop a 3-sample spike between samples - which is
            # exactly the event the recording was taken to find.
            edges = np.linspace(0, col.size, buckets + 1).astype(int)
            lo = np.array([np.nanmin(col[a:b]) if b > a else np.nan
                           for a, b in zip(edges[:-1], edges[1:])])
            hi = np.array([np.nanmax(col[a:b]) if b > a else np.nan
                           for a, b in zip(edges[:-1], edges[1:])])
            mid = t[np.clip((edges[:-1] + edges[1:]) // 2, 0, t.size - 1)]
            ax.fill_between(mid, lo, hi, linewidth=0)
            ax.plot(mid, (lo + hi) / 2, linewidth=0.5)
        ax.set_ylabel(name, fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1][0].set_xlabel("time")
    fig.tight_layout()
    fig.savefig(args.output, dpi=100)
    plt.close(fig)

    emit({"ok": True, "output": str(args.output), "channels": chans,
          "samples": int(values.shape[0]), "buckets": buckets,
          "method": "min/max envelope per pixel bucket"})
    return 0


# --------------------------------------------------------------------------
# .tcscopex - acquisition side, stdlib only
# --------------------------------------------------------------------------

def read_tcscopex(path):
    raw = Path(path).read_bytes()
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    return ET.fromstring(raw.decode("utf-8"))


def write_tcscopex(root, path):
    """Write UTF-8 with BOM and CRLF, matching what TwinCAT itself produces."""
    body = ET.tostring(root, encoding="unicode")
    text = XML_DECL + "\r\n" + body.replace("\r\n", "\n").replace("\n", "\r\n")
    Path(path).write_bytes(BOM + text.encode("utf-8"))


NULL_GUID = "00000000-0000-0000-0000-000000000000"


def refresh_guids(root):
    """Mint new GUIDs, rewriting references so nothing is orphaned.

    A scope project is not a flat bag of GUIDs. Each display Channel points at
    its data source through <AcquisitionGUID>, and other nodes cross-reference
    by GUID too. Replacing every <Guid> and stopping there yields a file that
    opens cleanly and plots nothing - the charts still reference identifiers
    that no longer exist. So build the old-to-new mapping first, then rewrite
    every element whose text is one of the old values, whatever its tag.
    """
    mapping = {}
    for node in root.iter("Guid"):
        old = (node.text or "").strip()
        if old and old != NULL_GUID:
            mapping[old] = str(uuid.uuid4())

    rewritten = 0
    for node in root.iter():
        value = (node.text or "").strip()
        if value in mapping:
            node.text = mapping[value]
            rewritten += 1
    return {"minted": len(mapping), "references_rewritten": rewritten - len(mapping)}


def cmd_newscope(args):
    template = Path(args.template)
    if not template.exists():
        fail(f"template {template} not found",
             "Templates ship in templates/ next to this script.")
    root = read_tcscopex(template)

    acquisitions = root.findall(".//AdsAcquisition")
    if not acquisitions:
        fail(f"{template} contains no AdsAcquisition node - is it a scope project?")

    def parent_of(node):
        for candidate in root.iter():
            if node in list(candidate):
                return candidate
        return None

    def set_fields(node, pairs):
        for tag, value in pairs:
            el = node.find(tag)
            if el is not None:
                el.text = value

    channels = [c.strip() for c in args.channels.split(",")] if args.channels else []

    if not channels:
        for node in acquisitions:
            set_fields(node, (("AmsNetId", args.netid), ("TargetPort", str(args.port))))
    else:
        acq_parent = parent_of(acquisitions[0])
        if acq_parent is None:
            fail("could not locate the AdsAcquisition parent in the template")
        model_acq = acquisitions[0]
        model_guid = (model_acq.findtext("Guid") or "").strip()

        # The display Channel that reads this acquisition, so a cloned channel
        # keeps its link. Without this a new channel plots nothing.
        model_chan, chan_parent = None, None
        for chan in root.findall(".//Channel"):
            ref = chan.find(".//AcquisitionGUID")
            if ref is not None and (ref.text or "").strip() == model_guid:
                model_chan, chan_parent = chan, parent_of(chan)
                break

        for node in acquisitions:
            acq_parent.remove(node)
        if model_chan is not None and chan_parent is not None:
            for chan in list(chan_parent):
                if chan.tag == "Channel":
                    chan_parent.remove(chan)

        for symbol in channels:
            acq = copy.deepcopy(model_acq)
            # Every clone starts out carrying the template's nested GUIDs -
            # AcquisitionInterpreter, ChannelStyle and friends. Left alone, all
            # clones collide and the project is invalid. Re-GUID each subtree
            # first; the explicit Guid set below then survives as the anchor the
            # matching display channel points at.
            refresh_guids(acq)
            acq_guid = str(uuid.uuid4())
            set_fields(acq, (
                ("SymbolName", symbol),
                ("AmsNetId", args.netid),
                ("TargetPort", str(args.port)),
                ("Guid", acq_guid),
                ("Title", symbol),
            ))
            if args.sample_time_ms is not None:
                set_fields(acq, (
                    ("BaseSampleTime", str(int(args.sample_time_ms * TICKS_PER_MS))),
                    ("UseTaskSampleTime", "false"),
                ))
            acq_parent.append(acq)

            if model_chan is not None and chan_parent is not None:
                chan = copy.deepcopy(model_chan)
                refresh_guids(chan)
                set_fields(chan, (("Name", symbol.split(".")[-1]), ("Title", symbol)))
                ref = chan.find(".//AcquisitionGUID")
                if ref is not None:
                    ref.text = acq_guid
                chan_parent.append(chan)

    guids = refresh_guids(root)
    write_tcscopex(root, args.output)
    emit({
        "ok": True,
        "output": str(args.output),
        "channels": channels or "unchanged from template",
        "guids": guids,
        "ams_net_id": args.netid,
        "note": "Written from a schema derived from real Beckhoff sample files, "
                "but never opened in TwinCAT. Verify before relying on it.",
    })
    return 0


def cmd_checkscope(args):
    root = read_tcscopex(args.input)
    problems, warnings = [], []

    guids = [g.text for g in root.iter("Guid")]
    dupes = {g for g in guids if guids.count(g) > 1}
    if dupes:
        problems.append(f"duplicate GUIDs, which breaks the project: {sorted(dupes)}")

    acquisitions = root.findall(".//AdsAcquisition")
    if not acquisitions:
        problems.append("no AdsAcquisition nodes - nothing would be recorded")

    total_rate = 0.0
    channels = []
    acq_guids = set()
    for node in acquisitions:
        symbol = (node.findtext("SymbolName") or "").strip()
        netid = (node.findtext("AmsNetId") or "").strip()
        guid = (node.findtext("Guid") or "").strip()
        acq_guids.add(guid)
        ticks = node.findtext("BaseSampleTime")
        rate = None
        if ticks and ticks.isdigit() and int(ticks) > 0:
            rate = 1000.0 / (int(ticks) / TICKS_PER_MS)
            total_rate += rate
        if not symbol or symbol.upper().startswith("PLACEHOLDER"):
            problems.append(f"channel has an unfilled symbol name: {symbol or '(empty)'}")
        if netid in ("", "0.0.0.0.0.0"):
            warnings.append(f"{symbol}: AmsNetId is a placeholder")
        channels.append({"symbol": symbol, "ams_net_id": netid, "rate_hz": rate})

    # A display channel reaches its data through AcquisitionGUID. If that
    # reference dangles, the project opens perfectly and plots nothing - the
    # failure mode that looks like a working file until someone hits Record.
    plotted = 0
    for chan in root.findall(".//Channel"):
        ref = chan.find(".//AcquisitionGUID")
        name = (chan.findtext("Name") or "?").strip()
        if ref is None or not (ref.text or "").strip():
            problems.append(f"display channel '{name}' has no AcquisitionGUID")
            continue
        target = ref.text.strip()
        if target not in acq_guids:
            problems.append(
                f"display channel '{name}' references acquisition {target}, "
                "which does not exist - it would plot nothing"
            )
        else:
            plotted += 1
    if acquisitions and plotted == 0:
        warnings.append("no display channel is wired to any acquisition")

    if total_rate > LOAD_WARN_SAMPLES_PER_S:
        warnings.append(
            f"{len(channels)} channels totalling ~{total_rate:.0f} samples/s. "
            "A recording this dense competes for real-time bandwidth with the "
            "machine it is diagnosing. Narrow it, or accept the risk knowingly."
        )

    emit({"ok": not problems, "file": str(args.input),
          "channels": channels, "display_channels_wired": plotted,
          "total_samples_per_second": total_rate,
          "problems": problems, "warnings": warnings})
    return 0 if not problems else 1


# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="tcscope.py",
        description="Create TwinCAT 3 Scope configurations and triage recorded data.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the environment").set_defaults(func=cmd_doctor)

    q = sub.add_parser("ingest", help="convert .svdx/CSV to Parquet")
    q.add_argument("input")
    q.add_argument("-o", "--output", required=True)
    q.set_defaults(func=cmd_ingest)

    q = sub.add_parser("manifest", help="channels, rate, duration, gaps")
    q.add_argument("input")
    q.add_argument("--dump-header", action="store_true",
                   help="print the raw first lines, for when sniffing gets it wrong")
    q.set_defaults(func=cmd_manifest)

    q = sub.add_parser("stats", help="per-channel distribution and health")
    q.add_argument("input")
    q.add_argument("--channels")
    q.set_defaults(func=cmd_stats)

    q = sub.add_parser("events", help="steps, spikes, flatlines, clipping, crossings")
    q.add_argument("input")
    q.add_argument("--channels")
    q.add_argument("--sigma", type=float, default=6.0)
    q.add_argument("--spike-width", type=int, default=16,
                   help="how many samples a value may stay out before it counts "
                        "as a step rather than a spike")
    q.add_argument("--flat-samples", type=int, default=50)
    q.add_argument("--clip-fraction", type=float, default=0.01)
    q.add_argument("--threshold", type=float)
    q.add_argument("--max-events", type=int, default=100)
    q.set_defaults(func=cmd_events)

    q = sub.add_parser("plot", help="PNG with a min/max envelope")
    q.add_argument("input")
    q.add_argument("-o", "--output", required=True)
    q.add_argument("--channels")
    q.add_argument("--width", type=int, default=1200)
    q.set_defaults(func=cmd_plot)

    q = sub.add_parser("window", help="real rows for a narrow time range")
    q.add_argument("input")
    q.add_argument("--start", type=float, required=True)
    q.add_argument("--end", type=float, required=True)
    q.add_argument("--channels")
    q.add_argument("--max-rows", type=int, default=500)
    q.set_defaults(func=cmd_window)

    q = sub.add_parser("correlate", help="cross-channel correlation and lag")
    q.add_argument("input")
    q.add_argument("--channels")
    q.add_argument("--max-lag-samples", type=int, default=20000)
    q.set_defaults(func=cmd_correlate)

    q = sub.add_parser("newscope", help="write a .tcscopex from a template")
    q.add_argument("template")
    q.add_argument("-o", "--output", required=True)
    q.add_argument("--channels", help="comma-separated PLC symbol names")
    q.add_argument("--netid", default="0.0.0.0.0.0", help="target AmsNetId")
    q.add_argument("--port", type=int, default=851)
    q.add_argument("--sample-time-ms", type=float)
    q.set_defaults(func=cmd_newscope)

    q = sub.add_parser("checkscope", help="validate a .tcscopex")
    q.add_argument("input")
    q.set_defaults(func=cmd_checkscope)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
