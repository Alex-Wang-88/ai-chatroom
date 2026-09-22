# Architecture Notes

The backend owns provider credentials, transcript history, routing, round state and cancellation. The browser only sends commands and renders normalized events.

Topic mode creates an immutable context snapshot and starts one independent provider task per eligible agent. Free mode creates a new snapshot before every speaker, keeps the discussion anchored to the user's trigger, and runs a bounded two-cycle scheduler: each currently eligible agent can be selected at most once per cycle, with the normal talkativeness/recency weighting used for the order. It stops earlier on the configured message cap, user cancellation, no eligible speaker, or the error threshold. `display_sequence` is assigned under a per-round lock on the first non-empty delta and never changes.
