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

Times: a Scope export states time in milliseconds. This tool converts on read
and reports seconds everywhere - `manifest` says so via "time_unit": "ms" and
"times_reported_in": "s".

Status: the CSV reader was measured against 19 genuine TC3ScopeExportTool.exe
exports from a Beckhoff CX/AX8000 machine (TwinCAT 3.1, Dutch Windows) covering
both the TAB and ',' dialects, and is tested against structural copies of all
five layouts those files use. The .tcscopex writer is still modelled on real
Beckhoff sample files but has never been opened in TwinCAT. Both say so rather
than implying otherwise.
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
# Directional, not a benchmark - see references/recording-load.md. Set from
# practice rather than theory: the densest of seven real Beckhoff-authored
# projects measured 16 250 samples/s, so 100 000 never once fired and warned
# about nothing. This line means "denser than anything anyone here has shipped".
LOAD_WARN_SAMPLES_PER_S = 20_000


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
# A Scope CSV is not `time,ch1,ch2,...`. TC3ScopeExportTool.exe writes a
# horizontal concatenation of independent acquisition groups - typically one ADS
# port and one sample rate each - and every group carries its own time column:
#
#     <t0> <a0> <a1> | <t1> <b0> <b1> <b2> | <t2> <c0>
#     ^ group 0      ^ group 1             ^ group 2
#
# So a physical row is not one instant in time. Treating it as one puts every
# channel on group 0's clock, which on these files is wrong by one PLC cycle at
# best and by half the recording at worst.
#
# Two dialects: TAB with European decimal commas and 17 metadata rows, and ','
# with '.' decimals and a Name row only. ';' appeared in none of the 19 real
# files but the synthetic EU fixture uses it, so it stays supported.
# --------------------------------------------------------------------------

# A metadata row repeats its key at every group start, so these double as the
# group-boundary markers. Taken from the TAB dialect, which writes all 17.
METADATA_KEYS = frozenset({
    "Name", "SymbolName", "SymbolComment", "NetId", "Port", "IndexGroup",
    "IndexOffset", "Data-Type", "SampleTime[ms]", "SymbolBased", "VariableSize",
    "Offset", "ScaleFactor", "BitMask", "Unit", "StartTime", "EndTime",
})

# Preference order: the qualified path identifies a signal, the short name does
# not. The ',' dialect only ever has Name.
GROUP_KEYS = ("SymbolName", "Name")

# Scope exports milliseconds. Everything this tool reports is seconds.
MS_PER_S = 1000.0

# Beyond this multiple of the fastest sample time, groups are not skewed, the
# export is broken: the slow groups were never repeat-padded and run off their
# own wall clock. Cross-group timing on such a file means nothing.
BROKEN_SKEW_MULTIPLE = 10


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


def _probe_delimiter(lines, nonblank):
    """Elect the delimiter, trying ';' then TAB then ',' and keeping the first
    on a tie.

    The order is the fix, not an accident. On a European TAB export every row
    holds exactly as many ',' as it holds TABs - the decimal comma is precisely
    as consistent as the real delimiter - so a vote decided on consistency alone
    elects ',' for a TAB file, ncols collapses from 120 to 26, no row ever
    matches it and the file reports no numeric rows at all. Both re-orderings of
    this tuple were tried against the real corpus and each broke a dialect.
    """
    best = None
    for delim in (";", "\t", ","):
        counts = [lines[i].count(delim) for i in nonblank[-20:]]
        if not counts or max(counts) == 0:
            continue
        modal = max(set(counts), key=counts.count)
        if modal == 0:
            continue
        consistency = counts.count(modal) / len(counts)
        if best is None or consistency > best[1]:
            best = (delim, consistency, modal + 1)
    return best


def _probe_decimal(candidate_rows, delim):
    """Score both separators over candidate data rows.

    Inferring the decimal from the delimiter is what produced silently wrong
    numbers: the TAB dialect is a European export with decimal commas, and
    nothing about a TAB says so.
    """
    if delim == ",":
        return "."  # a comma cannot be the delimiter and the decimal at once
    scores = {}
    for candidate in (".", ","):
        total = ok = 0
        for fields in candidate_rows:
            for field in fields:
                if field.strip():
                    total += 1
                    ok += _looks_numeric(field, candidate)
        scores[candidate] = ok / total if total else 0.0
    return "," if scores[","] > scores["."] else "."


def _find_data_row(lines, nonblank, delim, decimal, ncols):
    """The first row that is entirely data.

    Every non-empty field must be numeric. A metadata row is key/value pairs
    (Offset<D>0<D>Offset<D>0...) and so is exactly 50% numeric, which the older
    'at least half' rule accepted as data - the run appeared to start 14 rows
    early and the time axis began with NaN. The old rule survives as a fallback
    for files that match nothing.
    """
    fallback = None
    for i in nonblank:
        fields = lines[i].split(delim)
        if len(fields) != ncols:
            continue
        filled = [f for f in fields if f.strip()]
        if not filled:
            continue
        numeric = sum(_looks_numeric(f, decimal) for f in filled)
        if numeric == len(filled):
            return i
        if fallback is None and numeric >= max(1, len(fields) // 2):
            fallback = i
    return fallback


def _metadata_rows(lines, nonblank, delim, ncols, data_row):
    """Key -> fields, for rows that are ncols wide and start with a known key.

    Found by field count and key token, never by line number: a SymbolComment
    holding a multi-line Structured Text comment breaks one logical row across
    seventeen physical lines, none of them ncols wide.
    """
    found = {}
    for i in nonblank:
        if i >= data_row:
            break
        fields = [f.strip().strip('"') for f in lines[i].split(delim)]
        if len(fields) == ncols and fields[0] in METADATA_KEYS and fields[0] not in found:
            found[fields[0]] = fields
    return found


def _parse_groups(meta, ncols, decimal):
    """Split the columns into acquisition groups, or None if this is not a
    grouped export.

    Every column holding the key token starts a group; the columns up to the
    next one are that group's channels. A group's first column is its time
    column, not a channel - reporting it as data is how a 0-to-20280 time ramp
    ends up in a correlation matrix, correlated with everything that trends.
    """
    key = next((k for k in GROUP_KEYS if k in meta), None)
    if key is None:
        return None
    fields = meta[key]
    starts = [i for i, f in enumerate(fields) if f == key]
    if not starts or starts[0] != 0:
        return None

    names, symbols = meta.get("Name"), meta.get("SymbolName")

    def cell(row_key, col):
        row = meta.get(row_key)
        return (row[col].strip() if row else "") or None

    groups = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else ncols
        channels = []
        for col in range(start + 1, end):
            short = (names[col].strip() if names else fields[col].strip())
            qualified = (symbols[col].strip() if symbols else "")
            if not short:
                short = qualified or f"col{col}"
            declared = cell("SampleTime[ms]", col)
            port = cell("Port", col)
            channels.append({
                "name": short,
                "symbol_name": qualified or short,
                "column": col,
                "group": index,
                "unit": cell("Unit", col),
                "data_type": cell("Data-Type", col),
                "port": int(port) if port and port.isdigit() else None,
                "sample_time_ms": _parse_float(declared, decimal) if declared else None,
            })
        groups.append({"id": index, "time_column": start, "channels": channels})
    return groups


def _flat_group(lines, data_row, delim, decimal, ncols):
    """Fallback for an export with no group metadata: column 0 is time.

    Names come from the nearest non-numeric row above the data, but never from a
    metadata row - in the TAB dialect the nearest such row is
    `Unit<D>Offset<D>0<D>...`, which is how every channel ended up named '0'.
    """
    names = []
    for i in range(data_row - 1, -1, -1):
        if not lines[i].strip():
            continue
        fields = [f.strip().strip('"') for f in lines[i].split(delim)]
        if len(fields) != ncols or fields[0] in METADATA_KEYS:
            continue
        if any(f and not _looks_numeric(f, decimal) for f in fields):
            names = fields
            break
    if not names:
        names = [f"col{i}" for i in range(ncols)]
    channels = [{"name": names[col] or f"col{col}", "symbol_name": names[col] or f"col{col}",
                 "column": col, "group": 0, "unit": None, "data_type": None,
                 "port": None, "sample_time_ms": None}
                for col in range(1, ncols)]
    return [{"id": 0, "time_column": 0, "channels": channels}]


def sniff_csv(path, sample_bytes=200_000):
    """Work out delimiter, decimal separator, data start and group layout."""
    with open(path, "rb") as fh:
        text = fh.read(sample_bytes).decode("utf-8-sig", errors="replace")
    # Indices below are into the raw line list, blanks included, because
    # load_csv slices the same raw list. Filtering here and slicing there is
    # how the header row ends up parsed as a row of NaN.
    lines = text.splitlines()
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    if not nonblank:
        fail(f"{path} is empty")

    best = _probe_delimiter(lines, nonblank)
    if best is None:
        fail(
            f"could not find a delimiter in {path}",
            "Inspect the file with: tcscope.py manifest <file> --dump-header",
        )
    delim, _, ncols = best

    tail = [lines[i].split(delim) for i in nonblank[-20:]]
    decimal = _probe_decimal([f for f in tail if len(f) == ncols], delim)

    data_start = _find_data_row(lines, nonblank, delim, decimal, ncols)
    if data_start is None:
        fail(
            f"found no numeric rows in {path}",
            "Check this really is a Scope export: tcscope.py manifest <file> --dump-header",
        )

    meta = _metadata_rows(lines, nonblank, delim, ncols, data_start)
    groups = _parse_groups(meta, ncols, decimal)
    if groups is None:
        groups = _flat_group(lines, data_start, delim, decimal, ncols)

    return {
        "delimiter": delim,
        "decimal": decimal,
        "columns": ncols,
        "data_row": data_start,
        "metadata_keys": sorted(meta),
        "groups": groups,
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


class Recording:
    """A Scope export: acquisition groups, each on its own time axis.

    There is deliberately no single `time` vector. Handing one out is what let
    every verb apply group 0's clock to every channel.
    """

    def __init__(self, groups, info):
        self.groups = groups
        self.info = info

    @property
    def channels(self):
        return [ch for group in self.groups for ch in group["channels"]]

    def time_of(self, channel):
        return self.groups[channel["group"]]["time"]

    def samples(self, channel):
        """(t, v) for one channel, one point per distinct time instant.

        Repeat-padding prints a slow group's sample again on the next row, so
        the raw column has runs of identical values whose diffs are zero. Left
        in, they read as flatlines and they halve every measured rate.
        """
        group = self.groups[channel["group"]]
        keep = group["instants"]
        return group["time"][keep], channel["values"][keep]

    def max_skew_ms(self):
        """Largest row-wise disagreement between any two group time columns."""
        np = need("numpy")
        if len(self.groups) < 2:
            return 0.0
        stack = np.column_stack([g["raw_ms"] for g in self.groups])
        usable = np.all(np.isfinite(stack), axis=1)
        if not usable.any():
            return float("nan")
        spans = stack[usable].max(axis=1) - stack[usable].min(axis=1)
        return float(spans.max())

    def fastest_sample_time_ms(self):
        rates = [g["sample_time_ms_measured"] for g in self.groups
                 if g["sample_time_ms_measured"] and g["sample_time_ms_measured"] > 0]
        return min(rates) if rates else None

    def timing(self):
        """How far the file can be trusted across groups."""
        skew = self.max_skew_ms()
        fastest = self.fastest_sample_time_ms()
        limit = (fastest or 0) * BROKEN_SKEW_MULTIPLE
        broken = bool(fastest and skew == skew and skew > limit)
        out = {
            "row_is_one_instant": bool(skew == 0.0),
            "max_skew_ms": skew,
            "fastest_sample_time_ms": fastest,
            "cross_group_timing_valid": not broken,
        }
        if broken:
            out["note"] = (
                f"This export is broken, not merely skewed: the groups disagree by "
                f"{skew:.0f} ms against a {fastest:.0f} ms fastest sample time. The "
                "slow groups were never repeat-padded, so they run off their own wall "
                "clock and are stretched over a different span. Any conclusion about "
                "the relative timing of channels in different groups is invalid. "
                "Re-export with all groups on one sample rate."
            )
        elif skew > 0:
            out["note"] = (
                f"Groups are repeat-padded and disagree by up to {skew:.0f} ms. Each "
                "channel is timestamped from its own group, so single-channel results "
                "are exact; cross-group ordering is only meaningful beyond that skew."
            )
        return out


def _finalise_group(np, group, raw):
    """Attach the timing numbers one group needs, from its time column in ms."""
    finite = np.isfinite(raw)
    group["raw_ms"] = raw
    group["time"] = raw / MS_PER_S
    group["time_nan_count"] = int((~finite).sum())

    # First row of each distinct timestamp, non-finite times dropped: a blank
    # cell in a time column otherwise poisons every median taken over np.diff.
    changed = np.ones(raw.size, dtype=bool)
    changed[1:] = raw[1:] != raw[:-1]
    group["instants"] = np.flatnonzero(finite & changed)

    stamps = raw[group["instants"]]
    steps = np.diff(stamps)
    steps = steps[steps > 0]
    measured = float(np.median(steps)) if steps.size else float("nan")
    group["sample_time_ms_measured"] = measured
    group["n_samples"] = int(stamps.size)
    group["t_first"] = float(stamps[0] / MS_PER_S) if stamps.size else float("nan")
    group["t_last"] = float(stamps[-1] / MS_PER_S) if stamps.size else float("nan")
    group["gaps"] = int(np.sum(steps > 3 * measured)) if steps.size and measured > 0 else 0

    rows_seen = int(finite.sum())
    group["repeat_factor"] = max(1, round(rows_seen / stamps.size)) if stamps.size else 1

    declared = [ch["sample_time_ms"] for ch in group["channels"] if ch["sample_time_ms"]]
    group["sample_time_ms_declared"] = declared[0] if declared else None
    return group


def load_csv(path):
    """Read a Scope CSV export into a Recording."""
    np = need("numpy")
    info = sniff_csv(path)
    delim, decimal, ncols = info["delimiter"], info["decimal"], info["columns"]

    rows = []
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig", errors="replace")
    for ln in text.splitlines()[info["data_row"]:]:
        if not ln.strip():
            continue
        fields = ln.split(delim)
        if len(fields) != ncols:
            continue
        rows.append([_parse_float(f, decimal) for f in fields])
    if not rows:
        fail(f"no parsable data rows in {path}")

    data = np.asarray(rows, dtype=float)
    groups = []
    for group in info["groups"]:
        for channel in group["channels"]:
            channel["values"] = data[:, channel["column"]]
        groups.append(_finalise_group(np, group, data[:, group["time_column"]]))
    info["rows"] = int(data.shape[0])
    return Recording(groups, info)


PARQUET_META_KEY = b"tcscope"


def _unique(name, used):
    """Parquet column names must be unique; channel names are not.

    Keying a table off channel names silently dropped a column whenever two
    channels shared one - which the ',' dialect makes routine, and which
    reporting short names as the selector makes routine everywhere.
    """
    if name not in used:
        used[name] = 1
        return name
    used[name] += 1
    return f"{name}#{used[name]}"


def parquet_payload(rec):
    """(columns, layout) for writing a Recording losslessly to Parquet."""
    columns, used = {}, {}
    layout = {"time_unit": "s", "groups": []}
    for group in rec.groups:
        time_col = _unique(f"g{group['id']}.time", used)
        columns[time_col] = group["time"]
        entry = {"id": group["id"], "time_column": time_col,
                 "sample_time_ms_declared": group["sample_time_ms_declared"],
                 "channels": []}
        for channel in group["channels"]:
            name = _unique(f"g{group['id']}.{channel['name']}", used)
            columns[name] = channel["values"]
            entry["channels"].append({
                "column": name, "name": channel["name"],
                "symbol_name": channel["symbol_name"], "unit": channel["unit"],
                "data_type": channel["data_type"], "port": channel["port"],
                "sample_time_ms": channel["sample_time_ms"],
            })
        layout["groups"].append(entry)
    return columns, layout


def load_parquet(path):
    """Read back a recording ingested earlier, group model included.

    The layout travels in the schema metadata because it cannot be recovered
    from column names: without it every group's time axis collapses back into
    one, which is exactly the defect ingest used to reintroduce silently.
    """
    need("pyarrow")
    np = need("numpy")
    from pyarrow import parquet as pq
    table = pq.read_table(path)
    blob = (table.schema.metadata or {}).get(PARQUET_META_KEY)
    if not blob:
        fail(
            f"{path} carries no group layout - it was written by an older ingest",
            "Re-run: tcscope.py ingest <original.csv> -o " + str(path),
        )
    layout = json.loads(blob.decode())

    def column(name):
        return table.column(name).to_numpy(zero_copy_only=False).astype(float)

    groups = []
    for entry in layout["groups"]:
        seconds = column(entry["time_column"])
        group = {"id": entry["id"], "time_column": entry["time_column"],
                 "sample_time_ms_declared": entry.get("sample_time_ms_declared"),
                 "channels": []}
        for spec in entry["channels"]:
            group["channels"].append({
                "name": spec["name"], "symbol_name": spec["symbol_name"],
                "column": spec["column"], "group": entry["id"],
                "unit": spec.get("unit"), "data_type": spec.get("data_type"),
                "port": spec.get("port"), "sample_time_ms": spec.get("sample_time_ms"),
                "values": column(spec["column"]),
            })
        groups.append(_finalise_group(np, group, seconds * MS_PER_S))

    rows = int(groups[0]["time"].size) if groups else 0
    return Recording(groups, {"source": "parquet", "rows": rows,
                              "columns": len(table.column_names)})


def load(path):
    path = Path(path)
    if not path.exists():
        fail(f"{path} does not exist")
    if path.suffix.lower() == ".parquet":
        return load_parquet(path)
    if path.suffix.lower() == ".svdx":
        fail(
            f"{path} is a raw Scope recording",
            "Convert it first: tcscope.py ingest <file.svdx> -o rec.parquet",
        )
    return load_csv(path)


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

    rec = load_csv(src)
    out = Path(args.output)
    pa = need("pyarrow")
    from pyarrow import parquet as pq
    columns, layout = parquet_payload(rec)
    table = pa.table(columns).replace_schema_metadata(
        {PARQUET_META_KEY: json.dumps(layout).encode()})
    pq.write_table(table, out)
    emit({"ok": True, "input": str(args.input), "output": str(out),
          "rows": rec.info.get("rows"), "groups": len(rec.groups),
          "channels": len(rec.channels), "columns": list(columns),
          "delimiter": rec.info.get("delimiter"), "decimal": rec.info.get("decimal"),
          "note": "Group layout is stored in the Parquet schema metadata, so the "
                  "per-group time axes survive the round trip."})
    return 0


def cmd_manifest(args):
    if args.dump_header:
        with open(args.input, "rb") as fh:
            head = fh.read(4000).decode("utf-8-sig", errors="replace")
        emit({"ok": True, "raw_head": head.splitlines()[:40]})
        return 0

    np = need("numpy")
    rec = load(args.input)
    timing = rec.timing()
    total = len(rec.groups)

    groups = []
    for group in rec.groups:
        measured = group["sample_time_ms_measured"]
        groups.append({
            "group": group["id"],
            "channels": len(group["channels"]),
            "sample_time_ms_declared": group["sample_time_ms_declared"],
            "sample_time_ms_measured": measured,
            "repeat_factor": group["repeat_factor"],
            "estimated_rate_hz": (MS_PER_S / measured) if measured and measured > 0 else None,
            "n_samples": group["n_samples"],
            "t_first": group["t_first"],
            "t_last": group["t_last"],
            "duration": group["t_last"] - group["t_first"],
            "time_nan_count": group["time_nan_count"],
            "gaps": group["gaps"],
            "port": next((ch["port"] for ch in group["channels"] if ch["port"]), None),
        })

    # The fastest group stands for the file in the flat fields below, which
    # exist so a single-group export reads the way it always did.
    lead = min(groups, key=lambda g: g["sample_time_ms_measured"]
               if g["sample_time_ms_measured"] == g["sample_time_ms_measured"] else 1e18)

    emit({
        "ok": True,
        "file": str(args.input),
        "rows": rec.info.get("rows"),
        "ncols": rec.info.get("columns"),
        "time_unit": "ms",
        "times_reported_in": "s",
        "duration": lead["duration"],
        "median_sample_interval": (lead["sample_time_ms_measured"] or 0) / MS_PER_S,
        "estimated_rate_hz": lead["estimated_rate_hz"],
        "gaps": sum(g["gaps"] for g in groups),
        "timing": timing,
        "groups": groups,
        "channels": [
            dict(channel_label(ch, total),
                 unit=ch["unit"], data_type=ch["data_type"],
                 nan_fraction=float(np.mean(~np.isfinite(ch["values"]))),
                 constant=bool(np.nanmax(ch["values"]) == np.nanmin(ch["values"])))
            for ch in rec.channels
        ],
        "delimiter": rec.info.get("delimiter"),
        "decimal": rec.info.get("decimal"),
    })
    return 0


# --------------------------------------------------------------------------
# stats / events / correlate / window
# --------------------------------------------------------------------------

def select(rec, wanted):
    """Channels matching a comma-separated selector, by short or qualified name.

    Both forms match because short names are not unique - two groups routinely
    carry the same ActTorque - and the qualified path is the only way to say
    which one you meant.
    """
    channels = rec.channels
    if not wanted:
        return channels
    want = {w.strip() for w in wanted.split(",")}
    hits = [ch for ch in channels if ch["name"] in want or ch["symbol_name"] in want]
    if not hits:
        available = ", ".join(sorted({ch["name"] for ch in channels})[:40])
        fail(f"no channel matched {wanted}", f"Available: {available}")
    return hits


def channel_label(channel, groups_total):
    """How a channel is named back to the caller."""
    out = {"name": channel["name"], "symbol_name": channel["symbol_name"]}
    if groups_total > 1:
        out["group"] = channel["group"]
    return out


def cmd_stats(args):
    np = need("numpy")
    rec = load(args.input)
    total = len(rec.groups)

    out = []
    for channel in select(rec, args.channels):
        label = channel_label(channel, total)
        # One point per distinct instant: a repeat-padded group otherwise reads
        # as half real samples and half frozen ones.
        _, col = rec.samples(channel)
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            out.append(dict(label, error="all values are NaN"))
            continue
        lo, hi = float(np.min(finite)), float(np.max(finite))
        diffs = np.abs(np.diff(np.unique(finite)))
        out.append(dict(
            label,
            **{
            # Distinct instants, not file rows: a repeat-padded group holds half
            # as many samples as the file has rows, and without this number
            # there is no way to tell from the output which one a std was
            # computed over.
            "n_samples": int(finite.size),
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
            }))
    emit({"ok": True, "channels": out})
    return 0


def _runs(np, flags):
    """(starts, ends) of every run of True in `flags`, as half-open pairs."""
    edges = np.flatnonzero(np.diff(np.concatenate(
        ([False], flags, [False])).astype(np.int8)))
    return edges[0::2], edges[1::2]


def _excursions(np, col, d, thresh, gap):
    """Half-open (start, end) index pairs, one per sustained change in `col`.

    Consecutive over-threshold differences are obviously one excursion. The
    reason for the gap tolerance is less obvious: a ramp whose per-sample change
    lands near the threshold flickers over and under it, so one commanded move
    arrives as dozens of one-sample fragments - which is how a velocity channel
    still reported 50 "steps" for a single move after the threshold was floored.

    Same-direction excursions within `gap` samples are therefore joined. Opposite
    directions never are: the return edge of a spike is exactly that, and merging
    it would erase the out-and-back shape the spike test looks for.
    """
    starts, ends = _runs(np, np.abs(d) > thresh)
    merged = []
    for s, e in zip(starts.tolist(), ends.tolist()):
        if merged:
            ps, pe = merged[-1]
            if s - pe <= gap and (col[e] - col[s]) * (col[pe] - col[ps]) > 0:
                merged[-1] = (ps, e)
                continue
        merged.append((s, e))
    return merged


def _detection_threshold(np, d, finite_d, span, args):
    """Smallest first-difference that counts as a real change on this channel.

    MAD alone is what made this verb unusable on real machine data. An axis is
    at rest for most of a recording, so over half its first differences are the
    encoder's quantisation floor and MAD collapses to ~1e-9 - non-zero, so it
    passed the old `if not mad` guard, and 6*MAD*1.4826 then became a threshold
    that every genuine acceleration sample cleared. One 5000-row export fired
    1199 "steps" on a position channel that simply moved once.

    So the noise-relative threshold is floored against the channel's own travel:
    a change worth reporting is exceptional against the quiet stretches *and* a
    real fraction of the distance this signal covers. The span is measured
    p0.5-p99.5 so a single outlier cannot set the scale.
    """
    mad = (float(np.median(np.abs(finite_d - np.median(finite_d))))
           if finite_d.size else 0.0)
    scale = mad * 1.4826
    if not scale:
        scale = float(np.std(finite_d)) if finite_d.size else 0.0
    return max(args.sigma * scale, args.min_step * span)


def cmd_events(args):
    np = need("numpy")
    rec = load(args.input)
    total = len(rec.groups)

    found = []
    for channel in select(rec, args.channels):
        name = channel["name"]

        def event(kind, severity, **rest):
            row = {"channel": name, "symbol_name": channel["symbol_name"], "kind": kind}
            if total > 1:
                row["group"] = channel["group"]
            row["severity"] = round(float(severity), 3)
            row.update(rest)
            return row

        # Each channel is timestamped from its own group's clock. Using group
        # 0's was wrong by one PLC cycle on a padded export and by half the
        # recording on an unpadded one.
        t, col = rec.samples(channel)
        ok = np.isfinite(col)
        if ok.sum() < 8:
            continue
        finite = col[ok]
        lo, hi = float(np.min(finite)), float(np.max(finite))
        # Two distinct values means a digital signal. Its "steps" are toggles and
        # its rails are just its two states, so the analogue detectors describe
        # it wrongly in both directions - 100% of a BOOL sits at a rail.
        digital = bool(np.all((finite == lo) | (finite == hi)))
        p_lo, p_hi = np.percentile(finite, [0.5, 99.5])
        span = float(p_hi - p_lo) or (hi - lo)

        # NaN diffs stay NaN. Substituting 0.0 turned a blank cell into a real
        # reading of zero - a fake step on a torque channel - and turned a run
        # of blanks into a flatline, reporting missing data as a frozen signal.
        d = np.diff(col)
        finite_d = d[np.isfinite(d)]
        thresh = _detection_threshold(np, d, finite_d, span, args)

        if thresh > 0:
            # A sustained change is ONE event. Reporting each over-threshold
            # sample separately turned a single 2.4 s move into 1199 "steps" and
            # buried every real fault under them. NaN compares False, so a gap
            # in the data ends an excursion rather than bridging it.
            for s, e in _excursions(np, col, d, thresh, args.spike_width):
                # d[s] and d[e-1] are finite by construction, so both endpoints
                # of the excursion are real readings.
                base, net = float(col[s]), float(col[e] - col[s])
                # A spike comes back; a step goes and stays. Test the level the
                # signal returns to, not the sign of the next difference - the
                # return edge of a 3-sample spike is its own excursion, several
                # samples away.
                horizon = min(e + args.spike_width + 1, col.size)
                back = np.flatnonzero(np.abs(col[e:horizon] - base) <= 0.5 * abs(net))
                width = e - s
                if back.size:
                    kind, width = "spike", int(width + back[0])
                elif digital:
                    kind = "transition"
                elif width > args.ramp_samples:
                    # It went, but it took its time getting there. Calling a
                    # commanded move a "step" would bury the discontinuities
                    # that are actually worth looking at.
                    kind = "ramp"
                else:
                    kind = "step"
                found.append(event(
                    kind,
                    1.0 if kind in ("ramp", "transition") else abs(net) / thresh,
                    time=float(t[min(s + 1, t.size - 1)]),
                    index=int(s + 1),
                    delta=net,
                    width_samples=int(width),
                ))

        # A BOOL sits at both its rails 100% of the time and holds each state for
        # as long as the machine needs it. Clipping and flatline describe neither
        # - `transition` already reports every change a digital channel makes.
        if not digital:
            for edge, value in (("max", hi), ("min", lo)):
                frac = float(np.mean(col[ok] == value))
                if frac > args.clip_fraction:
                    found.append(event("clipping", frac / args.clip_fraction,
                                       edge=edge, value=value, fraction=frac))

            # NaN == 0 is False, so a gap in the data breaks a flat run instead
            # of extending it.
            flat_starts, flat_ends = _runs(np, np.abs(d) == 0)
            for s, e in zip(flat_starts.tolist(), flat_ends.tolist()):
                run = e - s
                if run >= args.flat_samples:
                    found.append(event("flatline", run / args.flat_samples,
                                       time=float(t[s]), samples=run))

        if args.threshold is not None:
            crossings = np.flatnonzero(np.diff((col > args.threshold).astype(int)) != 0)
            for j in crossings[:args.max_events]:
                found.append(event("crossing", 1.0, time=float(t[j + 1]),
                                   threshold=args.threshold))

    t0, t1 = _recording_span(rec)
    emit({"ok": True, "count": len(found),
          "summary": _event_summary(found, t0, t1, args.max_events),
          "events": sorted(_rank(found, t0, t1, args.max_events),
                           key=lambda e: e.get("time", 0.0)),
          "truncated": len(found) > args.max_events,
          "severity": "multiple of each detector's own threshold; ramp, "
                      "transition and crossing are descriptive, always 1.0",
          "ranking": "worst first within each tenth of the recording, so a "
                     "truncated answer still spans the whole of it"})
    return 0


BINS = 10


def _recording_span(rec):
    spans = [(g["t_first"], g["t_last"]) for g in rec.groups
             if g["t_first"] == g["t_first"]]
    if not spans:
        return 0.0, 0.0
    return min(s for s, _ in spans), max(e for _, e in spans)


def _bin_of(event, t0, t1):
    """Which tenth of the recording an event falls in.

    `clipping` describes a whole channel rather than an instant, so it has no
    time and lands in a pool of its own - counting it as "at t=0" would both
    skew the histogram and let it crowd out real events from the first tenth.
    """
    if "time" not in event:
        return BINS
    if t1 <= t0:
        return 0
    return min(BINS - 1, int((event["time"] - t0) / (t1 - t0) * BINS))


def _rank(found, t0, t1, cap):
    """The worst events, spread across the recording.

    Chronological truncation was the real defect: the default 100 came back
    from the first 10 ms of a 10.8 s export and said `truncated`, while the
    fault sat at 9 s. Pure severity ranking has the same failure in a different
    costume - it answers about the loudest second and says nothing about the
    rest.

    So: one pass per round, taking the worst remaining event from each tenth of
    the recording, and visiting the tenths worst-first. Round one therefore
    always contains the single worst event in the file, and a cap smaller than
    the number of tenths still spends itself on the worst of them rather than
    the earliest.
    """
    if len(found) <= cap:
        return list(found)
    bins = [[] for _ in range(BINS + 1)]
    for event in found:
        bins[_bin_of(event, t0, t1)].append(event)
    for b in bins:
        b.sort(key=lambda e: -e["severity"])

    kept, round_ = [], 0
    while len(kept) < cap:
        ready = [b for b in bins if round_ < len(b)]
        if not ready:
            break
        ready.sort(key=lambda b: -b[round_]["severity"])
        for b in ready:
            kept.append(b[round_])
            if len(kept) == cap:
                break
        round_ += 1
    return kept


def _event_summary(found, t0, t1, cap):
    """Per-kind, per-channel and per-decile totals over ALL events.

    Always present, truncated or not. Without it the only way to learn that the
    returned events cover 0.1% of the recording was to re-run with a cap no
    caller would think to guess.
    """
    by_kind, by_channel = {}, {}
    bins, timed = [0] * BINS, 0
    for e in found:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        by_channel[e["channel"]] = by_channel.get(e["channel"], 0) + 1
        if "time" in e:
            bins[_bin_of(e, t0, t1)] += 1
            timed += 1
    return {
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
        "by_channel": dict(sorted(by_channel.items(), key=lambda kv: -kv[1])),
        "per_channel_max": max(by_channel.values()) if by_channel else 0,
        # `timed` is below `count` by however many clipping events there are:
        # clipping describes a channel, not an instant, so it has no bin.
        "time_histogram": {"t_first": t0, "t_last": t1, "bins": bins, "timed": timed},
        "returned": min(len(found), cap),
    }


def _unit_vector(np, values):
    """Mean-centred and scaled to unit norm, so cross-correlation is bounded.

    Without this the raw correlation is dominated by amplitude: a torque channel
    swinging hundreds of Nm outranks the position signal that actually caused
    it, whatever the shapes look like.
    """
    centred = values - values.mean()
    norm = float(np.linalg.norm(centred))
    return centred / norm if norm else centred


def _lag_of(np, x, y, max_lag):
    """(lag_samples, correlation_at_that_lag) for two aligned unit vectors.

    Sign convention: a NEGATIVE lag means `a` leads `b` - a's features appear
    earlier in time. `np.correlate(x, y, "full")[k]` sums x[n+k]·y[n], so if
    y is x delayed by D samples the peak sits at k = -D.
    """
    full = np.correlate(x, y, mode="full")
    zero = x.size - 1
    lo, hi = max(0, zero - max_lag), min(full.size, zero + max_lag + 1)
    window = full[lo:hi]
    peak = int(np.argmax(np.abs(window))) + lo
    return peak - zero, float(full[peak])


def cmd_correlate(args):
    np = need("numpy")
    rec = load(args.input)
    total = len(rec.groups)
    chosen = select(rec, args.channels)
    if len(chosen) < 2:
        fail("correlate needs at least two channels")

    timing = rec.timing()
    if not timing["cross_group_timing_valid"] and total > 1:
        fail(
            "this export cannot support any cross-channel timing claim",
            timing.get("note", "Re-export with all groups on one sample rate."),
        )

    pairs, refused = [], []
    for i in range(len(chosen)):
        for j in range(i + 1, len(chosen)):
            ca, cb = chosen[i], chosen[j]
            same_group = ca["group"] == cb["group"]
            if not same_group and not args.allow_cross_group:
                refused.append({
                    "a": ca["name"], "b": cb["name"],
                    "groups": [ca["group"], cb["group"]],
                    "reason": "channels are in different acquisition groups, so "
                              "they are not sampled on the same clock",
                })
                continue

            ta, xa = rec.samples(ca)
            tb, xb = rec.samples(cb)
            resampled = False
            if same_group:
                keep = np.isfinite(xa) & np.isfinite(xb)
                x, y, axis = xa[keep], xb[keep], ta[keep]
            else:
                # Put b on a's axis. Honest only because the caller asked for it
                # and the file's skew is inside one sample of the fast group.
                good_a, good_b = np.isfinite(xa), np.isfinite(xb)
                axis = ta[good_a]
                x = xa[good_a]
                y = np.interp(axis, tb[good_b], xb[good_b])
                resampled = True
            if x.size < 2:
                continue

            dt = float(np.median(np.diff(axis))) if axis.size > 1 else 1.0
            xn, yn = _unit_vector(np, x), _unit_vector(np, y)
            lag, peak = _lag_of(np, xn, yn, max(1, args.max_lag_samples))
            row = {
                "a": ca["name"], "b": cb["name"],
                "a_symbol": ca["symbol_name"], "b_symbol": cb["symbol_name"],
                "correlation": float(np.dot(xn, yn)),
                "correlation_at_lag": peak,
                "lag_samples": lag,
                "lag_seconds": lag * dt,
                "leads": ca["name"] if lag < 0 else (cb["name"] if lag > 0 else "simultaneous"),
            }
            if total > 1:
                row["groups"] = [ca["group"], cb["group"]]
            if resampled:
                row["resampled"] = (
                    f"b was linearly resampled from its own {cb['group']} axis onto "
                    f"a's, because the two groups do not share a clock")
            pairs.append(row)

    pairs.sort(key=lambda p: -abs(p["correlation"]))
    out = {"ok": True, "pairs": pairs,
           "lag_sign": "negative lag_seconds means 'a' leads 'b'",
           "timing": timing}
    if refused:
        out["refused_pairs"] = refused
        out["fix"] = "Pass --allow-cross-group to compare across groups anyway."
    emit(out)
    return 0


def cmd_window(args):
    """Real rows, grouped by acquisition group.

    Rows are never merged across groups. A physical row of a Scope export holds
    one sample from each group, taken at times that differ by up to a full slow
    cycle, so presenting them under one timestamp would be a quiet lie.
    """
    np = need("numpy")
    rec = load(args.input)
    chosen = select(rec, args.channels)

    wanted = {}
    for channel in chosen:
        wanted.setdefault(channel["group"], []).append(channel)

    blocks, total_rows = [], 0
    for gid in sorted(wanted):
        group = rec.groups[gid]
        # One row per distinct instant, like every other verb. Indexing the raw
        # rows printed each sample of a repeat-padded group twice under the same
        # timestamp - so a table this tool had just described as 4 ms-sampled
        # came back with duplicate times, and the row cap bit at half the real
        # width because it was counting padding.
        keep = group["instants"]
        t = group["time"][keep]
        idx = keep[np.flatnonzero((t >= args.start) & (t <= args.end))]
        total_rows += idx.size
        blocks.append((gid, group, wanted[gid], idx))

    if total_rows == 0:
        spans = "; ".join(f"group {g['id']}: {g['t_first']} to {g['t_last']}"
                          for g in rec.groups)
        fail(f"no samples between {args.start} and {args.end}",
             f"The recording spans {spans}.")
    if total_rows > args.max_rows:
        fail(
            f"that window holds {total_rows} rows, over the {args.max_rows} cap",
            "Narrow the range, or raise --max-rows deliberately. This cap exists "
            "so a wide window cannot flood the context window.",
        )

    groups = []
    for gid, group, channels, idx in blocks:
        groups.append({
            "group": gid,
            "sample_time_ms": group["sample_time_ms_measured"],
            "channels": [ch["name"] for ch in channels],
            "rows": [
                {"time": float(group["time"][i]),
                 **{ch["name"]: float(ch["values"][i]) for ch in channels}}
                for i in idx
            ],
        })

    out = {"ok": True, "time_unit": "s", "groups": groups}
    if len(groups) == 1:
        # One group means one clock, so a flat row list is unambiguous.
        out["channels"] = groups[0]["channels"]
        out["rows"] = groups[0]["rows"]
    emit(out)
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

    rec = load(args.input)
    chosen = select(rec, args.channels)
    total = len(rec.groups)

    buckets = max(64, args.width)
    # Groups with different clocks do not share an x-axis; forcing one would
    # draw a 4 ms trace against a 2 ms ruler.
    shared = len({rec.groups[ch["group"]]["sample_time_ms_measured"] for ch in chosen}) == 1
    fig, axes = plt.subplots(len(chosen), 1, figsize=(args.width / 100, 2.2 * len(chosen)),
                             sharex=shared, squeeze=False)
    for i, channel in enumerate(chosen):
        t, col = rec.samples(channel)
        name = channel["name"]
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
        # The short name on the axis, the qualified path in the corner: full
        # symbol paths as y-labels overlap into an unreadable stack by about six
        # channels, and the path is what identifies the signal.
        ax.set_ylabel(name, fontsize=9)
        if channel["symbol_name"] != name or total > 1:
            caption = channel["symbol_name"]
            if total > 1:
                caption += f"   [group {channel['group']}]"
            ax.set_title(caption, fontsize=7, loc="left", pad=2)
        if not shared:
            ax.set_xlabel("time [s]", fontsize=8)
        ax.grid(alpha=0.3)
    if shared:
        axes[-1][0].set_xlabel("time [s]")
    fig.tight_layout()
    fig.savefig(args.output, dpi=100)
    plt.close(fig)

    emit({"ok": True, "output": str(args.output),
          "channels": [ch["name"] for ch in chosen],
          "samples": int(rec.samples(chosen[0])[1].size) if chosen else 0,
          "buckets": buckets, "shared_x_axis": shared,
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

    # The null GUID is a legitimate "unset" marker and refresh_guids leaves it
    # alone, so several may appear. Counting it as a duplicate condemns a file
    # that is perfectly valid.
    guids = [(g.text or "").strip() for g in root.iter("Guid")]
    real = [g for g in guids if g and g != NULL_GUID]
    dupes = {g for g in real if real.count(g) > 1}
    if dupes:
        problems.append(f"duplicate GUIDs, which breaks the project: {sorted(dupes)}")

    acquisitions = root.findall(".//AdsAcquisition")
    if not acquisitions:
        problems.append("no AdsAcquisition nodes - nothing would be recorded")

    total_rate = 0.0
    channels = []
    acq_guids = set()
    unrated = 0
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
        else:
            # An acquisition on the task's own sample time declares no
            # BaseSampleTime, so it contributes nothing to the total below. Say
            # so, or the load figure reads as complete when it is not.
            unrated += 1
        if not symbol or symbol.upper().startswith("PLACEHOLDER"):
            problems.append(f"channel has an unfilled symbol name: {symbol or '(empty)'}")
        if netid in ("", "0.0.0.0.0.0"):
            warnings.append(f"{symbol}: AmsNetId is a placeholder")
        channels.append({"symbol": symbol, "ams_net_id": netid, "rate_hz": rate})

    # A display channel reaches its data through AcquisitionGUID. If that
    # reference dangles, the project opens perfectly and plots nothing - the
    # failure mode that looks like a working file until someone hits Record.
    plotted = 0
    wired_to = {}
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
            wired_to.setdefault(target, []).append(name)
    if acquisitions and plotted == 0:
        warnings.append("no display channel is wired to any acquisition")

    # An acquisition with no display channel still costs target bandwidth and
    # still lands in the export; it just never appears on a chart. One real
    # project recorded sixteen and plotted six.
    unwired = len(acq_guids) - len(wired_to)
    if unwired > 0:
        warnings.append(
            f"{unwired} of {len(acq_guids)} acquisitions are not wired to any "
            "display channel. They consume target bandwidth and are recorded, "
            "but nothing plots them."
        )

    # Two display channels may legitimately share one acquisition, which is why
    # 'wired' can exceed the acquisition count. Report it rather than let the
    # number read as more sources than exist.
    shared = {guid: names for guid, names in wired_to.items() if len(names) > 1}
    if shared:
        warnings.append(
            f"{len(shared)} acquisition(s) feed more than one display channel, so "
            f"{plotted} wired channels come from {len(wired_to)} sources."
        )

    if unrated:
        warnings.append(
            f"{unrated} of {len(acquisitions)} acquisitions declare no "
            "BaseSampleTime - they run at the task rate, so the load figure "
            "below counts only the rest."
        )

    if total_rate > LOAD_WARN_SAMPLES_PER_S:
        warnings.append(
            f"{len(channels)} channels totalling ~{total_rate:.0f} samples/s. "
            "A recording this dense competes for real-time bandwidth with the "
            "machine it is diagnosing. Narrow it, or accept the risk knowingly."
        )

    # Wiring is only half of whether a scope catches anything. A fixed window
    # that starts when someone presses Record is fine for a fault you can
    # reproduce on demand and a lottery for one you cannot - and "intermittent"
    # is the usual reason for reaching for a scope at all. This cannot know
    # which case it is looking at, so it states the window and the arithmetic
    # and leaves the judgement where it belongs.
    trigger_node = root.find(".//TriggerModule")
    trigger_sub = trigger_node.find("SubMember") if trigger_node is not None else None
    has_trigger = trigger_sub is not None and len(trigger_sub) > 0

    record_ticks = (root.findtext(".//RecordTime") or "").strip()
    record_seconds = None
    if record_ticks.isdigit() and int(record_ticks) > 0:
        record_seconds = int(record_ticks) / TICKS_PER_MS / 1000.0

    auto_restart = (root.findtext(".//AutoRestartRecord") or "").strip().lower() == "true"

    if record_seconds and not has_trigger and not auto_restart:
        warnings.append(
            f"records a fixed {record_seconds:g} s window with no trigger configured. "
            "For a fault you can reproduce on demand that is fine. For an intermittent "
            "one the chance of catching it is roughly the window divided by the mean "
            "time between occurrences - a 60 s window on an hourly fault is under 2%. "
            "A trigger with a pre-trigger keeps the seconds before the event instead."
        )

    emit({"ok": not problems, "file": str(args.input),
          "channels": channels, "display_channels_wired": plotted,
          "acquisitions": len(acq_guids), "acquisitions_plotted": len(wired_to),
          "acquisitions_without_display_channel": max(0, unwired),
          "acquisitions_without_declared_rate": unrated,
          "total_samples_per_second": total_rate,
          "load_warn_samples_per_second": LOAD_WARN_SAMPLES_PER_S,
          "record_seconds": record_seconds,
          "trigger_configured": has_trigger,
          "auto_restart_record": auto_restart,
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

    q = sub.add_parser("events", help="steps, ramps, spikes, flatlines, clipping")
    q.add_argument("input")
    q.add_argument("--channels")
    q.add_argument("--sigma", type=float, default=6.0)
    q.add_argument("--min-step", type=float, default=0.01,
                   help="floor under --sigma, as a fraction of the channel's own "
                        "travel. Without it, a signal that rests has a noise "
                        "estimate of ~0 and every sample of a move is an event.")
    q.add_argument("--ramp-samples", type=int, default=3,
                   help="an excursion wider than this many samples is a ramp - a "
                        "commanded move - rather than a step discontinuity")
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
    q.add_argument("--max-lag-samples", type=int, default=20000,
                   help="widest lag searched, in samples. It bounds the search, "
                        "not the data: every sample is still correlated.")
    q.add_argument("--allow-cross-group", action="store_true",
                   help="compare channels from different acquisition groups by "
                        "resampling onto a common axis. They do not share a clock.")
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
