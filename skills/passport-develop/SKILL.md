---
name: passport-develop
description: Implement or extend a FoloToy AI Passport application from a user requirement, coordinating implementation, validation, and device-test handoff. Not for advice-only questions, log-only diagnosis, or publishing.
---

<p align="right"><a href="SKILL.zh_CN.md">简体中文</a> · <strong>English</strong></p>

# Develop an AI Passport Application

Resolve the target checkout with `git rev-parse --show-toplevel`; all paths below
are relative to that checkout, not the installed skill folder. Start with
`git status --short --branch`. Read `AGENTS.md` and `docs/development/ai-guide.md`,
follow the required-skill availability policy, and load other documents by task.

## Turn the request into a working increment

1. Define behavior and acceptance checks for the relevant screens, buttons, data,
   services, and failure states. Clarify material uncertainties; state reasonable
   defaults. Do not invent hardware facts or add unrequested networking, cloud
   services, wiring, or paid dependencies.
2. Continue the intended application and branch, preserving existing changes.
   For a new application, use the agreed baseline and applicable branch convention.
   Resolve conflicting edits or an ambiguous target with the user.
3. Consult relevant demo branches and `docs/reference/README.md` for reusable
   patterns. Derivative applications must implement their own UI under the AI
   guide's mandatory redesign rule; reuse BSP APIs and isolated logic.
4. Implement the smallest complete behavior and host tests for pure logic,
   following the AI guide's application/BSP boundary and runtime invariants.
5. Run focused checks while editing and the complete `./tools/validate.sh` gate
   before delivery. Fix failures introduced by the change; report unrelated or
   environmental blockers with evidence and the remaining actionable step.

## Route specialist work only when needed

| Situation | Skill |
| --- | --- |
| Missing or broken toolchain | `passport-setup` |
| Validate and package firmware | `passport-build` |
| User accepts on-device testing | `passport-device-test` |
| Runtime failure or crash | `passport-debug` |

## Handoff and continuation

Report implemented behavior, next steps, and `Build`, `Host tests`, `Device tests`,
and `Unverified` separately. For derivative-application UI work, describe the
pages and controls and verify startup/navigation use the application's own UI.
For work spanning sessions, update existing project notes only as needed.

After each completed firmware implementation, proactively offer device testing
under the AI guide's on-device handoff. Flashing requires explicit approval;
a build or USB connection is not consent. Do not commit, push, or publish
without authorization.
