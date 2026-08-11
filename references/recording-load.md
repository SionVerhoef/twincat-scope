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

`checkscope` sums this across all acquisitions and warns above 100,000 samples/s. That
threshold is **directional, not measured** — it is a prompt to think, not a certified limit.
The real limit depends on the controller, the core assignment, what else runs on it, and the
task cycle time. Treat a warning as "justify this", not "this will fail".

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
- **Genuine sub-cycle resolution needs oversampling terminals**, not a faster scope. If the
  question is about something shorter than one PLC cycle, the answer is EL3xxx/EL7xxx
  oversampling hardware, and that is a different conversation.
- **Record the shortest window that contains the event.** A trigger and thirty seconds beats
  ten minutes of hoping.
- **Add channels for a reason.** "Everything on the axis" is how a recording becomes both
  expensive and unreadable. Each channel should be one you would name in the report.
- **Start narrow and widen.** A second recording is cheap. A machine stopped by the first one
  is not.

## What this skill will and will not do

Will: build the `.tcscopex`, validate it, warn on the load, explain what to expect.

Will not: start a recording, activate a configuration, or write to the target. Rule 2.
