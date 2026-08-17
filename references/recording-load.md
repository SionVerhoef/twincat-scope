# Recording load — rule 4, and how to size a scope

A scope reads. Reading feels free. It is not.

## Why this is a hard rule

Every enabled channel is sampled by the TwinCAT real-time system and pushed to the Scope
Server. That costs cycle-time budget on the target and bandwidth on the ADS route. Ask for
enough of it and one of three things happens:

- The recording develops gaps, and the gaps land where the machine was busiest — which is
  exactly the moment you were trying to capture.
- The real-time task starts overrunning its cycle, which *changes the machine's behaviour*.
  You are no longer measuring the fault; you are measuring the fault plus your measurement.
- On a loaded controller, the task overrun trips a watchdog and stops the machine.

The middle case is the dangerous one, because it looks like data. A recording that perturbed
its own subject is worse than no recording — it produces a confident, wrong, well-evidenced
diagnosis.

**Therefore: propose the configuration, let a human start it on a production machine.** This
is not ceremony. The person at the machine knows what else that controller is doing and
whether now is a safe moment; an agent reading a file does not.

## Sizing

The number that matters is **total samples per second** — sample rate × enabled channels, not
either alone. Twenty channels at 1 kHz and two channels at 10 kHz load the system very
differently from what their headline rates suggest.

`checkscope` sums this across all acquisitions and reports which band it lands in. The bands
are **empirical, not certified** — a prompt to think, not a limit. The real limit depends on
the controller, the core assignment, what else runs on it, and the task cycle time.

| Band | samples/s | Meaning |
|---|---|---|
| `typical` | ≤ 6,000 | The middle of observed practice |
| `moderate` | ≤ 10,000 | Busier than most; no note |
| `high` | ≤ 20,000 | Denser than five of the seven measured projects — worth re-checking before adding channels |
| warn | > 20,000 | Denser than anything measured in practice; justify it |

The numbers come from seven real Beckhoff-authored projects on one production machine, which
measured **417, 2,750, 4,000, 5,750, 7,750, 11,667 and 16,250** samples/s. That distribution
is the whole reason for bands: an earlier single threshold sat at 100,000, then 20,000, above
every project anyone had actually built, so it never once fired and graded nothing. A check
that always passes is indistinguishable from no check.

Treat a warning as "justify this", not "this will fail".

Practical shape of a well-sized recording:

| Question | Rate | Channels |
|---|---|---|
| Why did this axis fault? | task rate (1–2 ms) | 4–6 on that axis |
| Is the machine drifting over a shift? | 100 ms or slower | many, cheaply |
| What does this 5 ms transient look like? | oversampled, ≥10 kHz | 1–2, briefly |

### Rules that keep you out of trouble

- **Sampling faster than the task that updates the variable buys nothing.** A value written
  once per 1 ms task does not become higher-resolution at 10 kHz — you get ten copies of each
  value, ten times the load, and a signal that looks smoother than the machine really is.
  `UseTaskSampleTime` exists for this; prefer it unless you have a reason.
- **Know which task feeds the variable, and treat its cycle as the floor.** Axis data off the
  NC interface (`NcToPlc.ActPos`, `ActVelo`, `ActTorque`) updates once per **NC SAF cycle** —
  typically 2 ms, 1 ms on a tuned system — not once per PLC cycle and not on demand. So a
  request for 50 µs on axis channels is asking for 20–40 identical samples per real update. It
  is a staircase, not resolution, and it costs 20–40× the bandwidth to record. When someone
  asks for microseconds on NC data, the useful reply is which task writes it, not a faster
  sample time.
- **Genuine sub-cycle resolution needs different hardware, not a faster scope.** For an analog
  signal that is EL3xxx/EL7xxx oversampling terminals. For something internal to a drive —
  current-loop or torque behaviour shorter than one fieldbus cycle — the scope on the target
  cannot see it at all, because the value only reaches the controller once per EtherCAT cycle.
  An AX8000 samples its own current loop internally at roughly 62.5 µs and Drive Manager can
  upload that trace; that is the instrument for the question, and it is a different
  conversation from this one.
- **Record the shortest window that contains the event.** A trigger and thirty seconds beats
  ten minutes of hoping.
- **Add channels for a reason.** "Everything on the axis" is how a recording becomes both
  expensive and unreadable. Each channel should be one you would name in the report.
- **Start narrow and widen.** A second recording is cheap. A machine stopped by the first one
  is not.

## What this skill will and will not do

Will: build the `.tcscopex`, validate it, warn on the load, explain what to expect.

Will not: start a recording, activate a configuration, or write to the target. Rule 2.
