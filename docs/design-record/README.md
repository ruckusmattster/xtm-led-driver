# Design record

The two design documents as they were written during the project. They're addressed to me: I
wrote a brief, Claude reviewed it (Phase 1), I answered its questions, and Claude produced the
detailed design (Phase 2). They're kept as the record of *why* the design is what it is.

| Document | What's in it |
| --- | --- |
| [Phase 1: design review](phase1-review.md) | The critique of my original brief (PWM, the buck, the headroom loop), the error and leakage budgets, power and thermal budgets, the picks for the open decisions, and my answers |
| [Phase 2: detailed design](phase2-detailed-design.md) | Every value on both boards with its reasoning, the crossover analysis, schematics, layout rules, parts and ordering, both firmwares, bring-up, calibration, flicker verification, the pre-order checklist and every assumption |

Where these differ from each other, Phase 2 wins; where either differs from the files in the
repository, the files win. For a shorter, current overview, start with the
[design process](../DESIGN_PROCESS.md), the [hardware reference](../HARDWARE.md) and the
[firmware reference](../FIRMWARE.md).
