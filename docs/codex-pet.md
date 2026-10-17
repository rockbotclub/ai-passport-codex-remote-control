<p align="right"><a href="codex-pet.zh_CN.md">简体中文</a> · <strong>English</strong></p>

# Codex Pet on AI Passport

This application replaces the baseline test menu with a dedicated companion
screen using the original blue Codex pet. Normal operation is wireless: the
computer and AI Passport join the same 2.4 GHz Wi-Fi network, and the device runs
from its battery. USB is needed for initial flashing or optional wired status.

## Chinese messages

All application-owned device labels, button hints, empty/error states, Wi-Fi
setup pages and responses, bridge diagnostics, and command-line help use
Simplified Chinese. Protocol keys, reason codes, commands, external chat/project
names, and upstream ESP-IDF diagnostics retain their original identifiers.
The native helper still recognizes the desktop application's English and
Chinese accessibility labels.

Fixed device labels use bundled Passport Sans subsets at 12/14/20 pixels;
see the [font assets](../assets/README.md#fonts). Startup verifies every required
glyph against each actual LVGL font descriptor, including a missing-glyph
negative check. Dynamic desktop text continues to use locally rasterized
bitmaps. A custom desktop font must cover the fixed Chinese message inventory;
unsupported dynamic content directs the user to review it on the computer.
Run `python3 tests/test_codex_pet_chinese.py` in the bridge environment to check
message coverage, native reason translations, argument errors, font cmaps, and
device-footer widths.

On 2026-10-17, the user authorized flashing this version. The installed table
has a 3 MiB factory application at `0x10000`, with the same NVS/PHY offsets as
the template. The 2,754,928-byte application fits that existing partition.
Only the application was written; the installed bootloader, partition table,
NVS, PHY and resource partitions were retained. Flash hash verification passed.
The flashed bundle is
`build/firmware/ef5d82bb3aedbd5c33c0cc65f91463c8ae274df3fefb7a479aaab9e14fe8bb8a/`;
application SHA-256 is
`7d7aa14d650610d8107be9abf3e436352139c9776560a01c0a8e6d18535b86ef`,
and matching ELF SHA-256 is
`166e46b3b9a72e625219941d0f8c234a6c7576770ac0ba8ea1b83e078557d5c0`.

A bounded 35-second startup capture matched ELF prefix `166e46b3b`, contained
one application start with no font errors, crash markers or error-level logs,
and confirmed Wi-Fi reconnection and a received task overview. Free heap / largest
block were 77,900 / 69,632 bytes after initialization and 75,928 / 65,536 bytes
with the overview active. The monitor was closed. The user confirmed normal
Chinese status text, button hints and the chat list without boxes or clipping.
Build: PASS. Host tests: PASS. Device tests: PASS for flashing, startup and the
observed Chinese display. Unverified: uncommon error/setup states, extended
runtime and minimum heap under all interactions.

## Native new chat from Projects (2026-10-17)

Holding Up on the selected saved project now opens Codex's native new-chat
composer through `codex://new?mode=codex&projectId=...`. The bridge uses the
project ID and Codex's own project selection and creation flow. It does not
start a CLI turn or send an initial prompt.

The card shows a temporary new-chat entry. Hold Confirm to use the configured
PC dictation backend, release to finish inserting, then short-press Confirm to
press native Send. The first message remains in the desktop composer. After
sending, the card waits for the saved chat to appear before enabling further
input. The temporary entry is kept across a device reconnect, but is not written
to selection memory or retained after a bridge restart.

Native draft controls require a unique project name and a matching project
selector in the application shell. The native home heading picker is identified
by its exact project name and renderer classes. It provides positive home-view
evidence even if the sidebar retains saved-chat current markers. The labeled
picker remains supported when there is no saved-chat current marker. Missing,
renamed, duplicate, conflicting or changed targets fail closed. The current selector binding
uses the installed desktop's English and Simplified Chinese accessible labels. Projectless groups
cannot create a project chat. Repeated or stale button commands cannot open or
submit twice; uncertain submission is not retried.

Physical acceptance remains pending: project selection, native draft discovery,
hold/release insertion, separate first-message submission, and saved-chat
selection. This computer-side change reuses the existing firmware protocol;
no firmware flash is required.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (static gate, native control simulations and focused bridge checks).
Device tests: NOT RUN for this change. Unverified: the physical acceptance above,
including the card's Chinese prompts and native draft discovery.
Validation-only archive: `build/firmware/1816ae1dfd1d0afb8789be893f6a0659662a578f115895ed2ab858e6514927a9/`.
Matching ELF SHA-256: `6ae359b5a14e01f2e7ff9be1c8c235b1aaf8d942339d8350f32dcc997af41f45`.
The updated bridge was restarted after the active dictation ended, preserving
the Doubao backend. The card reconnected with authenticated encrypted control
and at least five successful synchronizations. No new-chat gesture or first
message has been physically accepted yet; connection recovery alone is not
feature acceptance. No firmware was flashed.

The user confirmed native new-chat navigation but reported that holding Confirm
returned `chat-not-found` before Doubao started. Logs showed no editor scan or
button press. The previous detector required the labeled picker and rejected
current sidebar markers, so it did not cover the installed native home heading
picker. Host regressions now cover that picker with retained sidebar markers,
wrong names, conflicting selectors, duplicate pickers, dialogs, embedded
browsers and saved-chat routes. Doubao startup failures and normal completion
forward only fixed numeric discovery schemas; names and input contents are
never logged. Physical first-message acceptance remains pending for this fix.

## Doubao PC dictation trial (2026-10-17)

An opt-in bridge backend uses Doubao Input Method for PC microphone recognition
while retaining Codex's native Send/Queue/Steer button. The installed Doubao
1.0.2 settings show hold-to-talk with release-to-finish and real-time text.
The user configured the hold shortcut to **Left Control**; Fn is unavailable on
their keyboard. Keep Doubao selected as the current input method and keep Codex
in front. The bridge does not change microphone selection or input-method settings.

```bash
python3 tools/codex_pet/bridge.py run --interactive --dictation-backend doubao
```

Hold Confirm to open the selected chat, uniquely identify and focus its message
composer, then hold Left Control. Wait for the PC voice panel before speaking.
Release Confirm to release Left Control and insert text. Short Confirm still
presses Codex's native submit button. No Codex native Dictate button is pressed
in this mode, and the bridge does not receive audio or transcript contents.
The default backend remains `codex`.

The helper rejects an existing unknown Doubao panel, held keyboard modifiers,
ambiguous composers and an unverified focus. A bounded helper owns the key hold,
checks the foreground app, editor, input source and selected chat, and releases on
stop, EOF, signal or watchdog expiry. Normal release briefly waits for the voice
panel to close before restoring Send; this is a UI observation, not proof of
transcription accuracy or message delivery. Cancellation may leave partial text
in the PC input and never sends it. Keep the target chat/input unchanged while
speaking. Existing PC-dictation firmware is reused; this trial needs no flash.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (126 full-dependency bridge tests without skips, native focus
and left-Control/panel simulations, and the complete static gate).
Device tests: PASS for the observed physical control path: authentication, at
least 30 encrypted synchronizations, three accepted hold/release cycles returning
from mode 10 to mode 1, and one native submit press without a reported helper error.
The last two PC start calls took 549/539 ms; stop calls took 556/568/571 ms and
native submission took 573 ms. These are bridge-side control timings, not audio
recognition or message-delivery measurements.
The user subsequently confirmed successful PC-microphone voice entry, release
inserting text without submitting, and a separate short Confirm submitting via
the native Codex button. The test message arrived in this chat and the user
reported no issues. The basic end-to-end flow passes physical acceptance;
recognition latency is qualitatively accepted, with no instrumented ASR timing.
Unverified: extended use, broader recognition accuracy, focus/chat changes,
disconnection, watchdog expiry and interruption during transcription.
Validation-only archive:
`build/firmware/d2c6626899db6900e2c35c559b54a9c85d811ab17d67be296b6c8768bc748fb6/`.
No firmware was flashed.

## Empty-input confirmation (2026-10-17)

The user reported another unavailable-submit result after the native submission
label update. The log again shows one writable editor, zero scoped candidates,
and no press. The earlier Queue/Steer compatibility change did not establish or
resolve the cause of this repeated failure.

The helper now reports fixed numeric counts of submit, dictation, stop, resume
and voice controls. These distinguish an absent submit control from a submit
control outside the accepted editor group. No labels, input text or chat
identities are logged. Automatic retries remain disabled.
The user subsequently confirmed that the input was empty and the PC displayed
Voice or Resume. Short Confirm now recognizes either control in the same
single-editor group when there is no submit control. It reports that there is
no message to send and asks the user to return, type on the PC or hold Confirm
to dictate. It does not press Voice/Resume or borrow another input's Send.

An empty main composer also remains the target for long-Confirm dictation when
a separate question input has its own Send/Dictate controls. Multiple matching
empty composers remain ambiguous; changed chats are rejected. The helper still
does not read input contents. Disabled submit controls remain a distinct state
because they can reflect validation or attachments rather than empty input.
Actual card rendering and empty-to-dictation-to-send acceptance remain unverified.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (117 full-dependency bridge cases and native simulations of
empty input, nested controls, separate question inputs, ambiguity and chat changes).
Device tests: NOT RUN for this fix; the final bridge restart restored authenticated
encrypted synchronization. Unverified: physical notice rendering and dictation/send.
No firmware write is needed for this computer-side change.

Validation archive: `build/firmware/9aad91b93f198735e659a2c7b37186c070d62e1fc9f827b528e5b06aa382b61a/`.
Matching ELF SHA-256: `12a265cbefad6e83287ab05522b6b83c0271e9c052aec17bd12423a471dc0cfd`.

## Native submission during an active chat (2026-10-17)

A reported short-Confirm failure found the selected chat and one writable input,
but no matching submit button; the native helper did not press anything. The
installed desktop uses Send when idle and Queue or Steer during an active run.
The bridge previously accepted only Send. Short Confirm now accepts these three
native submission labels and preserves the submission mode selected in Codex.
Stop, Resume and Transcribe and send remain excluded. A disabled submit control
is reported as disabled without pressing it.

Failures before a press now show their specific cause; the uncertain-send warning
is reserved for an unacknowledged press, timeout or unknown helper failure. Each
confirmation still consumes its token before dispatch and never retries an
uncertain send. Applying this computer-side fix requires restarting the bridge;
it requires no firmware write. Actual active-run submission remains a physical
acceptance check.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (complete host gate, native helper simulation, and 117
full-dependency bridge regressions without skips).
Device tests: NOT RUN for physical submission; the restarted bridge compiled
the updated helper and resumed authenticated encrypted card synchronization.
Unverified: actual idle/active-chat submission and the original reported symptom.

Validation archive: `build/firmware/72a4b8e427a436c58974bf7c4e77980c70eb5162b5e2fadffafa5d3dc4dcb86b/`.
Matching ELF SHA-256: `83046de7db3f465adfec2c6b858919d51cd70c68e71a184ba8b5a3a7efbcfa1a`.
This validation did not flash the device.

## Task identities and title synchronization (2026-10-17)

The task overview uses the same user-chat directory as the card's chat selector.
Source metadata excludes internal agents even when their `agent_path` is empty.
Independent user chats remain separate; parent/child relationships do not merge
their counts. An unrecognized lifecycle identity triggers a bounded background
catalog refresh and a global syncing/unknown indication, never an extra task row.
The footer can show synchronization while confirmed tasks remain visible.

Title refresh failures retain the last successful catalog. A missing active
identity requests an early background refresh, limited to one attempt per second
and one worker at a time. Confirmed chats without cached titles remain actionable
and show a Chinese unnamed-chat label. Fonts lacking the fixed Chinese glyphs
are rejected before rendering.
Successful catalog refreshes remove archived/deleted entries. A desktop-observed
task is removed when owner discovery explicitly confirms it has unloaded, including
tasks first seen through hooks. Read failures and newer hook events cannot clear
those tasks; hook-only CLI sessions retain their existing lifecycle behavior.
The overview protocol and firmware are unchanged; applying this fix requires a
computer bridge restart.

Build: PASS (shared ESP-IDF 5.5.3 firmware gate and independent archive verification;
this change requires no firmware write).
Host tests: PASS (115 full-dependency bridge regressions without skips, including
20 status-sync and 17 overview checks; the complete static gate also passed).
Device tests: PASS for authenticated reconnect, at least 30 encrypted syncs,
and user-confirmed absence of the placeholder task with chat names/counts matching
Codex. The observed overview contained three running chats and no waiting chats.
Unverified: physical approval handling during metadata failure, unnamed-chat
rendering, and unloaded-task cleanup; these have host regression coverage.

## Send waiting state (2026-10-17)

The user reported that short Confirm sends successfully but briefly shows a
disconnected pet. Ordinary control views expire after three seconds, while a
native Send request may wait up to 24 seconds. The existing local startup state
covered Dictate only; Send retained the ordinary view during that wait. No new
per-action connection trace has yet established an actual transport loss for
the reported Send.

The card now enters local mode 12 (SENDING) when its worker dispatches OK from
chat-list mode 1. The UI shows a bounded sending state and consumes additional
keys until the authenticated reply or transport failure replaces it. It remains
online for less than 24 seconds; mode 0 still reports a real failure immediately.
Project selection and approval confirmation do not enter SENDING. Mode 12 is
never accepted from the wire, and the desktop still presses the actual Send
button once. This requires a new application flash; it changes no partition,
Wi-Fi, pairing or audio setting.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (complete host gate plus the full-dependency 116 bridge checks;
button policy covers the three-second false-offline interval, 24-second limit,
genuine failure, duplicate gestures, and Send/project/approval/Dictate mappings).
Device tests: PASS for the authorized application-only write, verified Flash hash,
matching boot ELF, retained Wi-Fi connection and received overview. A bounded
35-second startup capture contained no crash markers; the first overview arrived
at 10.515 seconds with 76,044 free heap bytes and a 65,536-byte largest block.
Unverified: SENDING rendering, the reported Send/disconnect symptom and the latest
desktop Dictate selection/latency; these still require physical button acceptance.

Flashed archive: `build/firmware/199bbe9a3071c5762d3ac5300edddf95194b8661a4338156d6426a8602791cee/`.
Full-image SHA-256: `199bbe9a3071c5762d3ac5300edddf95194b8661a4338156d6426a8602791cee`.
Application: 2,744,640 bytes, SHA-256
`fe03c6c873db08c74dadba6b047204aa06be63f74144de2b931111b281d65256`.
Matching ELF SHA-256: `411eac983e720eb22494c9f7d07bffcf89ae2c6dad0dc59b9c74c69769c3a23d`.
The application was written at `0x10000` (sectors through `0x2aefff`) on
`/dev/cu.usbmodem21201`. A fresh installed-table read verified its MD5, bounds,
non-overlap and the existing 3 MiB factory partition before writing. The installed
bootloader, partition table and NVS were retained. The boot ELF prefix is
`411eac983`; the serial monitor has been closed.

## Native Codex dictation and Send (2026-10-16)

Short Confirm opens the selected existing chat and presses its actual Send button.
Hold Confirm starts that chat's native Dictate control using the PC microphone;
release presses Stop dictation to insert text. Sending remains a separate short
Confirm. Codex handles recognition and composer contents/settings. The card sends
only key controls. The card recorder, Whisper, draft prefill and CLI new-chat
executor have been deleted, along with input-mode switches. Create new chats on
the PC, then select them on the card.

The card firmware advertises PC-dictation support and uses mode 10 to wait for
release without accessing audio hardware. Older firmware receives an update
notice before any native microphone action. The desktop bridge is running in
native mode, and the updated device has reauthenticated. On 2026-10-17 the user
confirmed that holding Confirm starts native Codex Dictate. Sanitized bridge logs
showed five record/release cycles returning to the chat list without reported
composer errors. The user subsequently confirmed that release inserts text
without sending and a separate short Confirm sends through the interface.
The basic native Dictate/release/Send flow has passed physical acceptance.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (42 retained interaction regressions, 18 native-dictation/CLI
checks without skips, synthetic native accessibility tests, and the complete host
gate). Device tests: PASS for application write integrity, matching startup,
preserved Wi-Fi/pairing, authenticated encrypted overview receipt, and
user-confirmed native Dictate startup, insert-only release and short-press Send.
Unverified: the PC DICTATION display and disconnect/timeout behavior.

On 2026-10-16, with user approval, the verified 2,744,224-byte application was
flashed through `/dev/cu.usbmodem21201` at `0x10000`. Chip detection confirmed
ESP32-C3 and 8 MB Flash. The installed partition table passed MD5, bounds and
overlap checks; its 3 MiB factory partition fits the application. Only
`0x10000..0x2adfff` was erased/written, retaining the partition table, bootloader,
NVS and auxiliary data partitions. Esptool verified the write hash. A bounded
35-second startup observation matched ELF prefix `fca1ece48`, with no crash or
watchdog markers. Wi-Fi reconnected using saved settings, and an authenticated
encrypted overview arrived 10.707 seconds after boot (three running tasks, zero
waiting tasks). Startup free heap/largest block were 77,940/69,632 bytes; at
overview receipt they were 72,844/63,488 bytes. The serial port was closed. The
application is 64,832 bytes smaller than the preceding candidate. Physical
acceptance still requires holding Confirm while speaking into the PC microphone,
releasing to insert without sending, then short-pressing Confirm to send.
Archive: `build/firmware/7e5bb706492775239bd7389b4f7ea5915fd502cc6d7250981751727a7d0ece57/`.
Full-image SHA-256: `7e5bb706492775239bd7389b4f7ea5915fd502cc6d7250981751727a7d0ece57`.
Matching ELF SHA-256: `fca1ece4857853e9c37c12fdac5c649dd231f86413aadf6fed6b23a65ca90c16`.

## Dictation startup latency and connection indicator (2026-10-17)

The user accepted the native Dictate/release/Send flow, then reported a slow
hold-to-Dictate response and the pet showing disconnected, mainly while waiting
for Dictate to start. Startup previously
repeated broad accessibility traversals and resolved the entire project catalog
for its unique chat title. Current-chat discovery now visits shallow sidebar
rows first, reuses role reads and skips static text; active dictation controls
are checked together and readiness first checks the local composer group.
Title lookup reads only saved chat names, retaining fresh uniqueness checks.
A metadata-only local measurement was 264.1 ms for the old full catalog path
and 35.1 ms median for the new title lookup; this is not end-to-end latency.
A synthetic 1,000-level transcript requires fewer than 30 attribute reads for
current-chat binding. Real startup timing remains unmeasured after this change.

The card previously retained its normal chat-list state while waiting up to
24 seconds for the start reply, but displayed OFFLINE after three seconds
without a new view. The updated firmware enters local mode 11 (STARTING
DICTATION) before that request, keeps the pending UI visible for at most
24 seconds and consumes additional gestures. The authenticated reply or an
actual transport failure replaces the pending state. Mode 11 is never accepted
from the wire. Connection-loss/error handling is retained; actual Wi-Fi loss
has not been established by the earlier logs. The bridge now logs numeric
navigation/catalog/native timings and sanitized disconnect categories.

The complete validation gate and independent firmware archive verification pass.
Supplemental checks pass all 42 interaction tests and 21 native dictation checks;
the synthetic native helper and button-policy checks also pass. On 2026-10-17,
with user approval, the new application was flashed to the connected ESP32-C3.
Device tests PASS for write integrity and bounded startup only; physical startup
latency, pending-state rendering and connection stability remain unverified.

Flashed bundle: `build/firmware/eb4cd690c9e07eb5a173b01e79eb66104379c4e39e32d3535eea447916c7574e/`.
Application: 2,744,448 bytes, SHA-256
`af8162f7d876cbc5770ee6292a47233fbc2c4126e9173b23ba9ac4ca74db5ae3`.
Full-image SHA-256: `eb4cd690c9e07eb5a173b01e79eb66104379c4e39e32d3535eea447916c7574e`.
Matching ELF SHA-256: `126d261784f91b2324edab469cc07a90fdff74d8ad4c5eba91e9c13e623dc39e`.
The installed table passed MD5, bounds and overlap checks: its factory application
is 3 MiB at `0x10000` on the detected 8 MiB Flash. Only application sectors
`0x10000..0x2aefff` were written; the bootloader, partition table and NVS were
retained. The write hash verified. A 35-second startup capture matched ELF prefix
`126d26178`, contained no crash markers, obtained Wi-Fi and received the overview
at 10.608 seconds. The running bridge recorded encrypted sync count 30. Startup
free heap/largest block were 78,064/69,632 bytes and overview values were
72,972/63,488 bytes. The monitor was closed. Startup latency, pending-state
rendering and actual connection stability still require a physical
hold/release/Send acceptance test.

### Further native control scan optimization (2026-10-17)

After the startup-state application flash, the user reported no remaining
functional or connection-indicator issue, but Dictate still appeared 3–5 seconds
after a hold. Four physical starts in the bridge log spent 5,455–7,037 ms inside
the native helper, compared with 146–520 ms in navigation and 38–126 ms in title
lookup. The native duration includes the readiness check after the button press;
it does not directly measure when the microphone first becomes active.

The helper now reads structural attributes in one accessibility batch per node,
with individual-read fallback for providers without batching. One control scan
collects editable paths and action buttons, and ancestor matching uses the
collected paths. Fresh chat validation before pressing, exact action labels,
manual-dictation rejection and readiness checks remain. Unreadable structural
subtrees reject the action. Editor values and transcript contents are never
requested. A synthetic 200-message tree starts Dictate in fewer than 500
accessibility calls, including target revalidation and readiness. Replacement
control groups, unsupported batching and unreadable-tree cases are covered.

The helper reports only fixed numeric setup/target/controls/press/ready timings
and control counts; the Python logger rejects unknown fields, nonnumeric and
out-of-range values. A physical attempt after deployment failed with
`multiple-writable-editors` before pressing anything. Selection was then refined
to require exactly one editor in an action-bearing ancestor group, stopping
before a shared ancestor containing multiple editors. Unrelated editable panels
are covered by tests; multiple eligible composers still reject the action.
Live button labels/enabled state and the chat are checked again before Press.

The scoped revision is deployed through bridge PID 87859, with successful
authentication and encrypted synchronization. A second physical attempt still
found two editors and two eligible Dictate groups (291 buttons), so it safely
rejected the action before Press. Its native duration was 2,569 ms: setup 213 ms,
target 774 ms and controls 977 ms, with zero press/readiness time. These are
failure timings, not a successful startup measurement. Structured test questions
were open during these attempts; possible interference from their own input
controls remains a hypothesis. The next physical test must use a plain chat
reply with no pending test-question form. Those two device attempts failed in that test context; startup latency remains
unverified. A subsequent desktop revision prefers the unique Dictate input whose
own single-editor group also contains the chat Send button, including a disabled
Send on an empty draft. Groups never borrow controls across another editor; two
message composers remain ambiguous. Synthetic regressions cover a question input
with Dictate beside the message composer, insert-only release and two actual
message composers. The updated helper and a specific multiple-input error message
are deployed in bridge PID 92476. Physical acceptance of this revision is NOT RUN;
plain chat replies are used for subsequent tests instead of new test forms.

The complete gate and independent archive verification pass; the final static
rerun after the scoped correction passes, including 116 bridge regressions
without skips (20 status-sync, 10 bridge, 45 interaction, 24 native dictation and
17 dashboard cases), native helper simulation and the remaining repository tests.
No firmware source changed and no additional flash was performed. Validation-only
bundle: `build/firmware/4203ce536d222ff21f32c9c0a6801f6e0d81ad9783daff96e87c295edb98586d/`;
full-image SHA-256 `4203ce536d222ff21f32c9c0a6801f6e0d81ad9783daff96e87c295edb98586d`,
matching ELF `041c20378914b823894c2c719ab0db1a01a167d5061bf13cc0ddcfa8f9efcb16`.
The card retains the previously flashed application and ELF above.

## Native chat identification correction (2026-10-16)

Physical holds returned `chat-not-found` before pressing Dictate. The user
confirmed that navigation had opened the correct selected chat. Adding the
installed desktop's `/dots/:conversationId` and `/o/:conversationId` routes did
not resolve two subsequent physical attempts. Static bundle inspection then
identified the structural difference: current sidebar chat rows are buttons with
`aria-current="page"`, an accessible chat title and the `sidebar-item` class;
they no longer expose a chat link. The helper had required a current link.

The bridge now supplies a fresh title only when it uniquely identifies the
selected chat in the local saved-chat catalog. The helper binds the trusted
application shell through that exact title, the current-page marker, button role
and sidebar class, while retaining URL matching for older link-based versions.
Duplicate titles, missing metadata, changed chats and external browser views
remain unbound. Titles travel only over helper stdin and are never logged.
The card now distinguishes chat-discovery, permissions, unavailable controls and
already-active dictation errors. Failed discovery also produces numeric
view/link/current-marker counts only, triggered by a physical card action.

A physical retry of the sidebar-button version also failed. Its diagnostic
reported zero web areas, links and current markers: discovery never reached the
web content, so the route/title changes did not resolve the observed failure.
The activation request previously ignored its result and discovery started only
from `AXWindows`. The latest bridge also reads the same application's main
window, focused window and application children, deduplicating the same view
while rejecting distinct ambiguous views. Failure diagnostics now include
numeric root counts, attribute-read errors, activation status and readback.
No readable web view is reported as `Codex UI not readable`, separately from a
missing selected chat.

Local binary string checks found `AXEnhancedUserInterface` in the installed
framework, but did not find Electron's `AXManualAccessibility` in either the
application or framework. The helper now falls back to the Chromium activation
attribute only when the manual attribute is unsupported or accepted without any
readback; an already-enabled enhanced interface is left enabled. Permission and
communication errors do not trigger that fallback. Chromium's
[application implementation](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/chrome_browser_application_mac.mm)
can debounce activation for two seconds, so read-only discovery now allows up to
four seconds instead of 1.6 seconds. Activation remains scoped to the target
application. On 2026-10-17 the user confirmed that the final correction starts
native Codex dictation on hold. The running bridge logged five record/release
cycles, each returning from mode 10 to the chat list without composer errors or
tracebacks. A subsequent sixth record/release cycle and one short Confirm
were observed without reported errors. The user confirmed insert-only release
and successful interface Send on the separate short press. Host regression checks cover current
sidebar buttons, wrong titles, absent sidebar classes, duplicate catalog titles,
stale routes, external browser views and numeric-only diagnostic logging.
The flashed application remains the `7e5bb706...` bundle above; these are desktop
bridge changes and require no firmware flash.

Build: PASS (complete ESP-IDF 5.5.3 gate and archive verification).
Host tests: PASS (complete host gate rerun after the final helper change; 42
interaction, 15 dashboard and 21 native-dictation/CLI checks without skips,
plus synthetic native accessibility tests). Device tests: PASS for user-confirmed
native Dictate startup, insert-only release and separate interface Send after
the application-root/Chromium activation changes; the earlier sidebar-only
version failed. Unverified: disconnect/timeout behavior. Validation-only archive (not flashed):
`build/firmware/47dcd95f284417b3c1ee45b2fd732944bc0bcae8a08be0e937e8073fbd1597fa/`.

## Startup task synchronization (2026-10-15)

The bridge reads already-running local desktop tasks at startup and reconciles
later snapshots with live hooks. Before confirmation, the card shows a syncing
message, faster blinking and three hopping violet dots; a timeout shows unknown
status instead of claiming there are no tasks. The syncing text is also stored
in firmware for the interval before the first encrypted overview arrives.
A read-only desktop check found the first running task in about 0.10 seconds and
all three in about 0.33 seconds; the full 194-chat sweep finished in 10.05 seconds.
These are PC discovery measurements, not measured device display latency.

Build: PASS (complete ESP-IDF 5.5.3 gate and independent archive verification).
Host tests: PASS (144 bridge checks without skips, plus the repository C and other
host checks). Device tests: PASS for application write integrity, matching startup,
preserved Wi-Fi/pairing, encrypted task overview receipt, and user-confirmed
physical task counts, syncing text and pet animation.
Unverified: empty-task confirmation, timeout/recovery and disconnection.
The firmware inputs were unchanged throughout validation. On 2026-10-16, with
user approval, the verified application was flashed at `0x10000`; its 2,808,704
bytes fit the installed 3 MiB factory partition. The installed partition table,
bootloader, NVS and auxiliary data partitions were retained. The matching bridge
was restarted and remains running. A bounded 40-second serial observation matched
ELF prefix `849a94f00`, with no crash/watchdog markers. The device received an
authenticated encrypted overview of two running tasks and zero waiting tasks
10.679 seconds after boot. Startup free heap/largest block were 74,480/65,536 bytes;
at overview receipt they were 72,504/61,440 bytes. The serial port was closed.
The logs establish device receipt. The user subsequently confirmed normal task
display/counts, syncing text and pet animation on the physical screen. End-to-end
display latency was not measured.
Archive: `build/firmware/915fdf61535cad831058d59f79be542de5217cdf8529b5ccdd06f2ef8a398452/`.
Full-image SHA-256: `915fdf61535cad831058d59f79be542de5217cdf8529b5ccdd06f2ef8a398452`.
Matching ELF SHA-256: `849a94f005ef57b71c0442fff859c425cf9188a7d12a4a7db5ca47a342cd39bf`.

## Plain-text source-position marks (2026-10-15)

A subsequent physical test failed before submission: the desktop editor stored
ordinary text with `startend` source-position marks, which the bridge rejected
as formatting. The parser now accepts these metadata marks while still rejecting
formatting, mentions and malformed marks. Regression coverage checks pending-fill
acknowledgement, sending the latest edited PC text and rejection of mixed marks.
This is a PC bridge correction; no firmware flash is needed. After the running
bridge update, sanitized diagnostics confirmed three saved transcription fills
and one physical Confirm action with a successful desktop send acknowledgement.
The resulting test message arrived in this chat. Submission after a PC edit and
approval actions remain unverified; the earlier send acceptance below is historical.

Build: PASS (complete ESP-IDF 5.5.3 gate and archive verification).
Host tests: PASS (120 bridge checks, including 88 interaction tests).
Device tests: PASS (transcription saving and physical Confirm sending).
Unverified: PC-edit submission, approval confirmation and approval-time recording.
The validation-only workspace archive was not flashed:
`build/firmware/a7f060a12b6d2a9cef47befbd998bc96d3404d7a02adc7a92f25b5f328464ea7/`.
Its matching ELF SHA-256 is
`52fa91b4460a0813c87aca1ef75e8aa9000f866067696da8cd8865df30146b88`.

## Delayed PC-input acknowledgement (2026-10-14)

The user observed that PC text appeared while the card reported a fill failure.
The bridge had treated a missing exact persisted draft within 2.5 seconds as a
failed route. Delayed saving now leaves the fill pending and returns to the list;
actual route-launch errors still show a dismissible error. Sending waits for
recent PC edits and requires a pending fill to reach disk as the expected voice
or changed PC text, preventing submission of the preceding input.

The complete ESP-IDF 5.5.3 gate and independent archive verification passed.
All 118 bridge tests passed without skips, including 86 interaction checks and
18 focused desktop-adapter checks. The running bridge was updated with its
existing settings; authentication and 30 encrypted syncs were observed without
a traceback. Firmware source was unchanged and no image was flashed for this
bridge correction. The device retains the deployed `df205d62...3dcb` archive
identified in the following section.

The user confirmed successful transcription into the PC input, return to the
session list and a separate Confirm send. Sanitized bridge diagnostics also
observed three recording/release cycles with pending saves returning to the list
without a fill error. The send result is user-confirmed; no transcript text was
logged.

Build: PASS. Host tests: PASS. Device tests: PASS for user-confirmed transcription,
list return and Confirm sending. Unverified: submission after editing the PC
text, approval confirmation and approval-time recording after this bridge update.

Validation-only archive (not flashed):
`build/firmware/159186e39f252d91dbd5719518e3f2d73b69909c527c8e345e7df3e9890d63d8/`.
Merged-image SHA-256:
`159186e39f252d91dbd5719518e3f2d73b69909c527c8e345e7df3e9890d63d8`.
Matching ELF SHA-256:
`922080bc020b805a0a6f8ab100c3c26909266ecb0d0b7457e9a83ea5c0bad243`.

## Confirm and PC-input sending (2026-10-14)

Clicking Confirm in a selected session now sends that chat's current PC input,
including computer edits, without requiring a voice preview. Empty input sends
nothing. On an approval, Confirm decides only the displayed request after all
pages have been seen. Holding Confirm records and transcribes; existing-chat
text fills the PC input and the card returns to the session list. During approval,
recording restores the same request afterwards. No transcript is rendered or
stored on the card; new-chat text stays only in bridge memory behind a generic
ready notice. Selection, project navigation and pet wake remain unchanged.

The complete ESP-IDF 5.5.3 gate and independent archive verification passed.
The final focused interaction suite passed 83 tests; the full-dependency static
suite passed all 115 bridge checks without skips. After the user's commit/flash
request, the installed partition table passed MD5, bounds and non-overlap checks.
Its 3 MB factory partition fits this image. Only application sectors `0x10000`
through `0x2bcfff` were written, with write-hash verification. The bootloader,
partition table, NVS, PHY and resource/identity partitions were retained.

A bounded 25-second startup observation matched ELF prefix `c89576f50`, confirmed
a station IP and overview delivery, and found no fault markers. Free heap/largest
block were 72,552/63,488 bytes. The existing bridge reauthenticated and completed
30 encrypted syncs without a traceback. The serial port was closed.

Build: PASS. Host tests: PASS. Device tests: PASS for write integrity, matching
startup, retained Wi-Fi/pairing and encrypted synchronization. Physical testing
of the new button behavior remains pending.
Unverified: physical button hints, approval-time recording, transcription/input
acknowledgement, current PC-input sending and rich-input rejection on the device.

Verified deployed archive:
`build/firmware/df205d62acf74a0042610eb3a90dd29f815ff34d643ef7177ee57e840f3b3dcb/`.
Merged-image SHA-256:
`df205d62acf74a0042610eb3a90dd29f815ff34d643ef7177ee57e840f3b3dcb`.
Matching ELF SHA-256:
`c89576f5027f8f3409da8a812aa139942e213345a1e8e331ce48156ddea3ccc7`.
The application is 2,804,256 bytes at `0x10000`, written through
`/dev/cu.usbmodem21201`. It was built and validated as `7faffc9-dirty`; the commit
records the corresponding source without rebuilding this approved artifact.
This deployment used the archived application image; writing the merged image
at `0x0` can reset stored data.

## One voice instruction before Confirm (2026-10-14)

Unconfirmed voice now remains one draft through waiting, automatic pet return,
control reconnection and failed additions. Confirm sends the whole draft once.
The full-dependency static gate passed, including 108 bridge checks without skips.
The complete gate passed its host checks, but ESP-IDF configuration was blocked
by the sandbox denying the component manager's process-tree query (`sysctl`).
Both existing IDF Python environments use that query. No new validated firmware
archive was produced; this correction changes only the bridge.

Build: FAIL (environment restriction). Host tests: PASS. Device tests: NOT RUN.
Unverified: physical multi-recording accumulation and one final desktop submission.
The running bridge was retained because this sandbox denies local port binding;
restart it from a local terminal to apply the correction. Unconfirmed voice is
held only in memory and does not survive that bridge restart.

## Fixed-height project and session rows (2026-10-14)

Both lists use five fixed 44-pixel slots across their 224-pixel panel, with
two pixels of padding at each end. Rows show only the project name or saved
sidebar title; long names use a width-checked ellipsis and the selected row
keeps the same height. Small lists retain empty slots. Session counts are
omitted from the project list.

The complete ESP-IDF 5.5.3 gate and full-dependency static checks passed,
including 106 bridge checks without skips. The native five-entry bridge was
restarted with its existing settings; authenticated device reconnection and
30 encrypted syncs were observed without a traceback. This bridge-rendered
layout uses the deployed 216-by-224 firmware format.

Build: PASS. Host tests: PASS. Device tests: NOT RUN for physical list acceptance.
Unverified: fixed row spacing, long-name ellipses and selection/scrolling on
the actual screen. The local rendering preview covers these cases.

Validation archive (not flashed):
`build/firmware/4eceb5abf51b2834770cdec93e0e22f4c5466852f51cd7bb70bbdb4c4f57666a/`.
Merged-image SHA-256:
`4eceb5abf51b2834770cdec93e0e22f4c5466852f51cd7bb70bbdb4c4f57666a`.
Matching ELF SHA-256:
`6872dace7832300fa941e6f8c30ad485cc72c210f3847f0f58ab40272c92d31a`.

## Five-entry deployment (2026-10-14)

After the user's flash approval, the current firmware/bridge source and test
hashes still matched the final validated snapshot. The image includes saved
changes from other chats in this checkout, including no-speech error dismissal.
The verified archive is
`build/firmware/12bd6f49880368662404a8c91e17421a74c590b43b33a1bb17ff26e4dce921c1/`.

A fresh read of the installed partition table passed MD5, bounds and non-overlap
checks. Its 3 MB factory partition at `0x10000` fits the 2,804,224-byte application.
Only the application sectors `0x10000` through `0x2bcfff` were updated through
`/dev/cu.usbmodem21201`; the write hash was verified. Bootloader, partition table,
NVS, PHY and resource/identity partitions were retained.

A 25-second startup observation matched ELF prefix `aedb0e3a6`, confirmed a
station IP and found no fault markers. Free heap/largest block were 74,476/65,536
bytes. The existing bridge stopped gracefully without interrupting a new-chat
job. The temporary four-entry override was removed; the bridge now runs the
native 216-by-224/five-entry format with the existing settings. Authentication,
a 6,065-byte control payload, multiple encrypted syncs and overview delivery
were observed. A further 30-second serial window found no crash markers, and
the bridge had no tracebacks. The serial port was closed; the bridge remains running.

Build: PASS. Host tests: PASS (105 bridge checks and portable layout checks).
Device tests: PASS for write integrity, matching startup, preserved Wi-Fi/pairing
and authenticated synchronization. The user also confirmed that five entries,
removed position counters, UP/DOWN scrolling, selected highlight and the list
footer display and operate normally. Unverified: review-page/footer separation
and runtime/audio memory headroom under recording load.

## Five-entry list candidate (2026-10-14)

Project and session lists now show up to five entries in a 216-by-224 bitmap
at y=45. The 16-pixel font, 20-pixel line pitch, selected title's two-line
wrap, full-width highlight and metadata remain. List position counters stay
hidden. Review pages retain their 192-pixel crop at y=85, with the button hints
at y=278. The largest list uses eleven lines (220 pixels), leaving room below.
The encrypted control record is 6,081 bytes, within the 6,144-byte ceiling.
Static BSS grows by 3,456 bytes compared with the deployed four-entry build.

The complete ESP-IDF 5.5.3 gate, all 105 bridge checks in the full dependency
environment, portable layout checks and independent archive verification passed.
The stable source includes the concurrent no-speech error-dismissal fix.
Firmware/configuration/asset/bridge and test-file hashes remained unchanged
through the final validation. Long Chinese names, first/last selections, complete
highlights, overflow rejection and matching firmware/bridge dimensions were checked.

Verified archive:
`build/firmware/12bd6f49880368662404a8c91e17421a74c590b43b33a1bb17ff26e4dce921c1/`.
Merged image: 2,869,760 bytes; SHA-256:
`12bd6f49880368662404a8c91e17421a74c590b43b33a1bb17ff26e4dce921c1`.
Application: 2,804,224 bytes at `0x10000`; SHA-256:
`7b3ea8a64a0b06c3474eda162729465b3b40e8cd53bd061752500e6c924b3b9b`.
Matching ELF SHA-256:
`aedb0e3a6b91423b8081cbc362e8fe90e271f51bb6eb8d398ce5899db22ab8bb`.

Build: PASS. Host tests: PASS. Device tests: NOT RUN for this candidate.
Unverified: physical five-entry readability, first/last scrolling, selected
highlight, review-page footer separation and runtime/audio memory headroom.
Read-only discovery found `/dev/cu.usbmodem21201`. Firmware and bridge need to
be deployed together. The ignored local launcher retains 192-pixel/four-entry
compatibility until deployment. Application-only flashing requires approval and
a fresh installed-partition check; the image fits the previously recorded 3 MB
factory partition. The merged image at `0x0` can reset stored data.

## Combined deployment (2026-10-13)

After the other related chats finished and the user authorized continuation,
the current saved firmware/configuration and bridge sources were validated
together. The complete ESP-IDF 5.5.3 gate, all 103 full-dependency bridge checks,
and independent archive verification passed. Source inventories remained
unchanged during validation and were checked again before writing.

Deployed archive:
`build/firmware/52dcb26587aca8fe16bdc8d33c5f4d5b0881cb4905241c9a8212ce08af622ed8/`.
Merged-image SHA-256:
`52dcb26587aca8fe16bdc8d33c5f4d5b0881cb4905241c9a8212ce08af622ed8`.
Matching ELF SHA-256:
`cc73f7ee1170288927ffb3d947c163c88b9dd68db4a7a06e4688ed85be7563e3`.
Only the verified 2,804,192-byte application was written to
`/dev/cu.usbmodem21201` at `0x10000`, updating sectors through `0x2bcfff`.
A fresh installed-table read verified MD5, bounds and non-overlap; its 3 MB
factory partition fits the image. Bootloader, partition table, NVS, PHY and
the other data/resource partitions were retained. Esptool verified the write hash.

A bounded 25-second startup capture matched ELF prefix `cc73f7ee1`, confirmed
a station IP and found no crash/allocation fault markers. Startup free heap and
largest block were 78,064/69,632 bytes. An additional 12-second connected
observation found no fault markers. The serial port was closed.

The existing bridge stopped gracefully with no active new-chat subprocess.
Its temporary 144-pixel/three-entry compatibility override was removed, retaining
the previous wrapper locally. The latest bridge restarted with its existing
settings, including the new-chat voice fix and other voice-input changes.
Authenticated reconnect, 216-by-192/four-entry configuration, a 5,201-byte
control payload and 30 encrypted syncs were observed without a traceback.
The bridge remains running.

Build: PASS. Host tests: PASS. Device tests: PASS for write integrity, matching
startup, retained Wi-Fi/pairing and encrypted connectivity only.
Unverified: physical four-entry readability, removed list counters, scrolling
and highlight, microphone transcription, first-voice submission and desktop handoff.

## Four-entry list candidate (2026-10-13)

Project and session lists now show up to four nearby entries without position
counters. The control bitmap grows to 216-by-192 at y=49 for lists, retaining
the 16-pixel font, two-line selected title, full-width highlight, project chat
counts and selected-chat short ID. A local two-screen rendering checked long
Chinese titles and the last selected entry. Update bridge and firmware together;
the independent home overview retains its three active-chat rows.

The complete ESP-IDF 5.5.3 gate and independent archive verification passed.
The full bridge dependency environment passed 102 focused checks without skips:
71 interaction, 7 new-chat, 14 overview and 10 hook/bridge tests. These cover the
optional dependency/rendering tests skipped in the activated IDF environment.

Verified archive:
`build/firmware/cf3d6c10e85a1278a62a5834257653bf8a6e776ebba4ef1cca0589f6fe004927/`.
Merged image: 2,869,728 bytes; SHA-256:
`cf3d6c10e85a1278a62a5834257653bf8a6e776ebba4ef1cca0589f6fe004927`.
Application: 2,804,192 bytes at `0x10000`. Matching ELF SHA-256:
`2d085f7bbeb071628b96f0f07dccb0e86aeb3bf95ff1477836516289de33a347`.
A merged flash from `0x0` can reset stored data; keeping Wi-Fi/pairing requires a
compatible segmented application flash and fresh installed-layout checks.
Read-only discovery found `/dev/cu.usbmodem21201`; this list iteration has not
flashed firmware.

Build: PASS. Host tests: PASS. Device tests: NOT RUN.
Unverified: physical four-entry readability, first/last scrolling, highlight,
and voice/approval regression after synchronized deployment.

## Idle/disconnection candidate (2026-10-13)

Separated empty/idle lifecycle state, stale active turns and connection loss.
Idle uses relaxed blinking; disconnected uses a still, downcast original pose
and local Chinese text. The complete ESP-IDF 5.5.3 gate and independent archive
verification passed. All 86 bridge checks passed in the full dependency
environment (10 hooks/bridge, 62 interaction/speech and 14 overview/rendering).
A local two-screen preview checked message fit and distinct poses.

Verified archive:
`build/firmware/237f556fc82376269afcc405a61f3df80f3b73040eced38022d7d6ffab03eb5b/`.
Merged image: 2,869,712 bytes; SHA-256
`237f556fc82376269afcc405a61f3df80f3b73040eced38022d7d6ffab03eb5b`.
Application: 2,804,176 bytes at `0x10000`; SHA-256
`46eeffdb3fc7d80fe9f2a36b55f0cca2d352f8e5614bcb0b4f5b4c16c482636c`.
Matching ELF SHA-256:
`c6fd2eb9df27276079fbb0c24d46e9f2f6510925c78508b37b4227c5d3044b6e`.
The application fits the previously recorded 3 MB factory partition. Flashing
the merged image from `0x0` can reset stored data; preserving Wi-Fi/pairing
settings requires rechecking the installed layout and flashing only compatible
application sectors. The running bridge has not been restarted and this
candidate has not been flashed. Read-only discovery found `/dev/cu.usbmodem21201`.

Build: PASS. Host tests: PASS. Device tests: NOT RUN for this candidate.
Unverified: physical Chinese readability, idle blinking, disconnected pose,
real control-channel loss while UDP remains live, and reconnection recovery.
Deploy this firmware and the updated bridge together after flash approval.

## Dense overview deployment (2026-10-13)

Implemented the approved compact header, smaller animated pet, independent
multi-chat overview, priority highlighting, single-chat title area, and larger
idle pet. The complete gate and independent archive verification passed. In the
full bridge environment, 71 focused tests passed: 55 interaction/speech, nine
overview and seven hook/bridge tests. The portable overview decoder also passed.

Verified archive:
`build/firmware/eda7227b34e34e09acfbc6197bec85b44dc5328769de7256078f2869d192816d/`.
Merged image: 2,865,248 bytes; SHA-256
`eda7227b34e34e09acfbc6197bec85b44dc5328769de7256078f2869d192816d`.
Application: 2,799,712 bytes at `0x10000`; SHA-256
`0282e0390206bc9be0481fb3a2f962d8980cca8c9222f92e3c11cac0056461be`.
Matching ELF SHA-256:
`3af29966151633d1562954ed9b770634fc536cb84391baa3558bbce3daeedfc8`.

Following the user's implementation-and-flash authorization, the installed
partition table was checked for MD5, bounds and overlaps. The existing 3 MB
factory partition fits the application. Only application sectors `0x10000`
through `0x2bbfff` were updated on `/dev/cu.usbmodem21201`; esptool verified the
written hash. Bootloader, partition table, NVS, PHY and other data partitions
were retained. The updated bridge remains running. A bounded 25-second startup
observation matched ELF prefix `3af299661`, confirmed Wi-Fi and receipt of the
one-running/zero-waiting overview, and found no crash/allocation-error markers.
Startup free heap/largest block: 83,072/73,728 bytes; after overview activation:
81,104/69,632 bytes. The serial port was closed.

Build: PASS. Host tests: PASS. Device tests: PASS for write integrity, matching
startup, Wi-Fi preservation and authenticated overview receipt only.
Unverified: physical Chinese readability, pet/list positioning, multiple real
chats and pending approvals on screen, key navigation, 10-second home return,
and voice/approval regression acceptance.

## Display and controls

The home screen uses a single CodeX/connection/battery header, without an IP address
in normal operation. A 96-by-104 pet sits beside the overall state and separate
running/waiting counts. Up to three active chats show the saved project name,
real sidebar title and state; approvals/input take priority, with stable lifecycle
insertion order within each group and a remaining-chat count. The overview covers
all observed chats, independent of the selected voice/action target. A single chat
gets a larger title area; when no chat is active the pet returns to 144-by-156.
On bridge startup, the home view shows the Chinese equivalents of “Syncing tasks”
and “Reading PC task status”. The pet blinks faster with three violet dots hopping
in sequence, distinct from its relaxed idle animation. A background read of the
existing desktop owners discovers tasks already running before the bridge starts.
Active results appear as they arrive; checking unloaded history does not hold them
back. Only a complete successful scan with no active tasks permits “No tasks” and
“Ready for your next task”, with the relaxed blinking pet. If initial synchronization
has not succeeded within 15 seconds, show “Task state unknown” and retry; never
turn a timeout into an empty-task claim. Known running/waiting tasks remain visible.
The new syncing status (wire value 6) requires matching bridge and firmware updates. Idle sessions stay idle even after 30 minutes. An active
turn without a lifecycle update for 30 minutes instead shows the Chinese
equivalents of “Task state unknown” and “Check tasks on PC”; this does not
claim completion or a connection failure.
Loss of the encrypted connection hides the overview and shows a still, downcast
pet with the Chinese equivalents of “PC disconnected” and “Check the PC bridge”.
The device keeps this text locally, so it works without the bridge.
Once the interactive connection has been established, its loss overrides a
still-arriving UDP task heartbeat; reconnection restores the live overview and
matching animation. USB-only operation uses the five-second heartbeat deadline.
Startup shows the pet. With an interactive bridge,
clicking any of UP, DOWN or OK opens the session list and restores the last selected
project/chat; this first click only opens the screen. Hold DOWN in the session or
project list to return to the pet immediately, preserving selection. Wi-Fi setup
remains available by holding DOWN on the pet screen. After 10 seconds without
button activity, the pet returns even while Codex is working. Bridge heartbeats
and turn-state changes do not extend this timeout. PC dictation stays visible
until completion, then begins a fresh 10-second window. A sleeping approval
resumes its request without deciding it.
The bridge saves only the last chosen project/chat IDs in a private
`codex-pet-selection.json` under its Codex directory, restoring them across control
reconnections and bridge restarts. Archived or removed chats fall back to an available chat;
an empty list cannot dictate or submit. Hold UP in the session list to browse saved
projects, including empty projects. OK enters that project's complete saved-chat
list, including chats that are not currently open on the PC.
Project IDs keep equally named projects separate; unassigned chats appear under
`No project`. Returning preserves the selected project and chat.

The dense overview requires the matching bridge and firmware. Each opted-in
control request returns the original token-bound review screen followed by a
separately authenticated type-9 overview record. Its eight-byte header carries
state, active/waiting counts and visible-row/highlight metadata; 5,628 bitmap bytes
cover the 104-by-84 summary, 216-by-144 chat area and 216-by-24 footer. The 6,144-byte
encrypted record ceiling bounds device memory. Older clients that do not request
the overview still receive one response. Overview packets cannot send, approve,
or change selection. Fixed and dynamic text is rendered using the bridge's verified
local CJK font at 11/12/14/15/16 pixels; unsupported titles explicitly request PC
review. No system font is bundled. USB-only operation retains the basic status view.

The lists hide the pet and turn-state widgets and show up to five nearby entries
in a 216-by-224 panel at y=45 below the header, retaining the 16-pixel font.
Both lists reserve five fixed 44-pixel rows, with two pixels of padding
at both ends, filling the available list area vertically. Session rows show only
the actual Codex sidebar title; project names and short IDs are omitted.
Long titles are truncated by rendered width with an ellipsis, including the
selected title, and every selected card has the same full-width, fixed-height
highlight. Fewer than five entries leave empty slots without enlarging rows.
The first user prompt is never used as a title. The panel leaves nine pixels
before the button hints at y=278. Review pages retain their 192-pixel crop at
y=85. Project rows show only the project name, using the same single-line
ellipsis and fixed-height highlight; session counts are omitted.
List position counters are omitted.
Unnamed chats and unassigned projects have explicit fallback labels.
Working, waiting for approval/input, and finished
turns use different original animations. After five seconds without a valid
heartbeat the state becomes offline. A finished turn means Codex stopped its
turn; it does not certify that the requested work succeeded.

The [standalone button guide](codex-pet-buttons.md) contains the complete
per-screen map for clicks, holds, recording release, Power, Wi-Fi setup, and
automatic return behavior.

Holding UP on a saved local project prepares a new device chat. Hold OK to record,
release to transcribe, then click OK on the ready notice to create the chat and send the
first voice message. The project stays pinned; list refresh and wake cannot send
the draft to an existing chat. New-chat voice stays in bridge memory before
confirmation; the card does not receive the transcript. No placeholder prompt is sent. `No project`, unavailable folders,
and equal roots belonging to different projects cannot use this shortcut.
The current confirmation token is consumed before creation, so stale events or
uncertain acknowledgement cannot automatically create or resend a chat.
The dedicated hardware power button is not exposed
to software; the ADC keys have no supported simultaneous UP+DOWN gesture.
Project/notice screen modes require this firmware and bridge to be updated together.

Pet/session wake candidate (2026-10-12): the complete gate and independent archive
verification passed. All 68 focused bridge checks passed in the full dependency
environment (61 interaction/speech and 7 bridge tests). Portable navigation checks
cover the exact 10-second boundary, heartbeat-independent timeout, activity reset,
wake acknowledgement, disconnect and recording/transcription exceptions. Encrypted
transport tests cover opening without another action and restoring a selection
after reconnect; private-file tests cover restart and closed-chat fallback.
Build: PASS. Host tests: PASS. Device tests: NOT RUN for this candidate.
Unverified: physical wake during Codex work, last-selection restoration, the
10-second pet return, and voice/approval rendering after deployment. At candidate
validation time, neither firmware nor the running bridge had been updated. Read-only USB
discovery found `/dev/cu.usbmodem21201`. Deploy this firmware and bridge together;
an application-only flash requires fresh installed-partition checks and consent.

Verified archive:
`build/firmware/7b3a48e544c4399a3cb56108ecd560414abc453e2fc93923055d3addc33505f9/`.
Merged image: 2,862,000 bytes, SHA-256
`7b3a48e544c4399a3cb56108ecd560414abc453e2fc93923055d3addc33505f9`.
Application: 2,796,464 bytes at `0x10000`, SHA-256
`dfdd600b70b342abdb467c9d32f83ee77cabd53aeb6cb9b255a51285880f465f`.
Matching ELF SHA-256:
`bfbf50ff7b0b99bef86f18d03a833351a678b0ff2ab7c941979cc626d8cf11b8`.
The application fits the previously recorded 3 MB factory partition. The merged
image at `0x0` can reset stored data; use a compatible application-only workflow
to retain Wi-Fi/pairing settings.

Pet/session deployment (2026-10-13): after explicit approval, the application from
the `7b3a48e544c4399a3cb56108ecd560414abc453e2fc93923055d3addc33505f9`
bundle was written at `0x10000` through `/dev/cu.usbmodem21201`. A fresh installed
partition-table read passed MD5/bounds/non-overlap checks; the existing 3 MB
factory application partition fits the 2,796,464-byte image. Only application
sectors `0x10000` through `0x2bafff` were written, and write-hash verification passed.
Bootloader, partition table, NVS, PHY and resource/identity partitions were retained.
A bounded 25-second startup capture matched ELF prefix `bfbf50ff7`, showed no
crash markers and confirmed a station IP. Free heap: 108,604 bytes; largest block:
98,304 bytes. The serial port was closed. The previous bridge stopped gracefully;
the updated bridge started its resident speech worker, established an authenticated
encrypted connection and resumed recurring syncs and a real working-state heartbeat.
The bridge remains running. Build: PASS. Host tests: PASS. Device tests: PASS for
flash integrity, matching startup, Wi-Fi/pairing retention and encrypted connectivity.
Unverified: physical short-press wake during Codex work, last-chat persistence,
the 10-second return to the pet, and voice/approval interaction after deployment.

Project navigation candidate (2026-10-12): the complete gate and independent
archive verification passed. All 57 focused interaction tests passed in the
bridge environment, including CJK project-card bounds. Build: PASS. Host tests:
PASS. Device tests: NOT RUN for this candidate. Unverified: physical long-UP
navigation, the real desktop new-chat route/project selection, first-message
discovery, and existing voice/approval behavior after deployment. This navigation
request did not flash firmware or restart the bridge. USB discovery found
`/dev/cu.usbmodem21201` without opening it.

Verified archive:
`build/firmware/696ad0d4b2addd57a0bb8ed0879e1a7f762bee131b1466e7dbd2cd0441f73857/`.
Merged image: 2,861,168 bytes, SHA-256
`696ad0d4b2addd57a0bb8ed0879e1a7f762bee131b1466e7dbd2cd0441f73857`.
Application: 2,795,632 bytes at `0x10000`, SHA-256
`f83a217c2ffc05d47217290debccab359913f7be0f65f54d8215a0ea155d98cc`.
Matching ELF SHA-256:
`23e54a3c0153d88078f6ee2c89e03fde537400861468b1d4a80573712139f343`.
The application fits the previously recorded 3 MB factory partition. A later
authorized application-only flash must recheck the installed partition table;
the merged image at `0x0` can reset stored data.

Without an interactive bridge, OK plays the pet animation and holding DOWN
opens Wi-Fi setup. Long OK presses never approve a request. Session selection
shows saved sidebar titles. Recording
and transcription pin the destination; buttons cannot switch it until completion or
cancellation. A displayed review token, rather than the latest unseen network
update, accompanies every action. Confirmation consumes a review before sending;
a missing desktop acknowledgement displays an uncertain outcome and never retries.

Fixed labels use the bundled Chinese font subsets. Dynamic text is rasterized on the computer
using a locally installed CJK font and transferred as a 216 × 224 one-bit image
(6,048 bytes; 6,081 bytes per encrypted record including headers and tag).
This control-panel size requires the matching bridge and firmware
to be updated together; the independent home overview keeps its existing dimensions.
The bridge checks the font's Unicode coverage before rendering;
unsupported approval text disables confirmation and directs the user to the PC.
Voice text is not rendered on the card and does not require card font coverage.
System fonts are not redistributed; the bundled device subset is OFL-licensed.
The UI owns a small image buffer; PCM is streamed in
1,024-byte chunks without retaining a complete recording on the ESP32-C3.

Wi-Fi credentials and the pairing key are stored in the application's NVS
namespace. The default partitions remain unchanged; startup/setup do not erase NVS.

## Import the pet artwork

The original artwork is imported from your own Codex installation for local use.
It and the generated frames are Git-ignored; redistribution permission has not
been established. The importer accepts the Codex v6/v2 sheet: 1536 × 2288 pixels,
8 columns and 11 rows, with 192 × 208 cells. A future app version with another
layout needs an explicit importer update.

Use a Python environment with [the dependencies](../tools/codex_pet/requirements.txt):

```bash
python3 tools/codex_pet/prepare_sprites.py --asar /Applications/ChatGPT.app/Contents/Resources/app.asar
# Or supply an exported compatible sheet:
python3 tools/codex_pet/prepare_sprites.py --sheet /absolute/path/to/codex-sheet.webp
```

The output is `assets/images/codex-pet/source.webp`, `frames.inc` and `offline.inc`. The 31
144 × 156 RGB565 frames occupy 1,392,768 bytes in Flash. Frames are read directly
by LVGL; there is no full-sheet decoder or framebuffer allocation in RAM.
The offline text is a 216 × 144 one-bit bitmap (3,888 Flash bytes), rendered
from the same checked local CJK font as the bridge at 16/12 pixels and displayed
through the existing list buffer. Re-run the importer for older assets. On
systems without macOS Arial Unicode, supply `--font /path/to/local-cjk-font.ttf`.
Missing offline-label glyphs stop generation; no font is bundled or redistributed.

## First Wi-Fi setup

1. After authorized flashing, power on the device. With no saved network it
   starts a WPA2-protected `CodexPet-xxxx` hotspot. The screen shows a large Wi-Fi
   QR code plus the hotspot name and temporary password for manual connection.
2. Scan with your phone's camera/Wi-Fi scanner and confirm joining the device
   hotspot. Keep it connected even if the phone reports no Internet. Compatible
   phones open the setup portal automatically. If it does not open, click OK on
   the device for a second QR code that opens `http://192.168.4.1/` **after joining
   the hotspot**, or enter that address in a browser. Click OK again to return
   to the Wi-Fi QR. Phone/model compatibility still requires device acceptance.
3. Select your normal 2.4 GHz Wi-Fi from the nearby-network list, or type a hidden
   network's name, then enter its password. The browser offers refresh and show
   password controls. SSID accepts 1–32 UTF-8 bytes; password accepts empty for
   an open network or 8–63 bytes for WPA networks. The page checks connection
   status while the setup hotspot remains active. Incorrect credentials,
   unavailable networks or a 25-second connection timeout leave the portal
   available for retry; previous saved credentials are not replaced by those
   failed attempts. After obtaining an IP, the device saves both fields as one
   NVS blob and restarts after an eight-second status window. Save the page's
   desktop pairing key privately, then rejoin your normal network. The device
   displays its IPv4 address after restart. The QR transfers temporary hotspot
   credentials; it does not read your phone's saved home Wi-Fi password.
4. Pair the desktop bridge, entering the key at its hidden input prompt:

```bash
python3 tools/codex_pet/bridge.py pair --host <device-IP>
```

This saves a private configuration at `~/.config/ai-passport/codex-pet.json`.
If the device's address changes, pair again using the new address and the same
key. Hold DOWN on the pet screen to reopen setup and retrieve the key or change
networks. The setup
web server runs only in hotspot mode; it is not exposed during normal operation.
During normal operation an unavailable saved network causes five-second reconnect
attempts; hold DOWN on the pet screen to reopen setup. The setup portal uses local DNS replies,
HTTP probe redirects and a DHCP captive-portal URI; the URI serves a captive
portal JSON response. HTTPS destinations are not intercepted. Phone behavior
varies, so the webpage QR/manual address remain available. Scans, DNS work,
connection validation and persistence run in the application worker; no BLE stack
or additional DNS task is allocated.

## Connect Codex lifecycle events

The bridge uses [official Codex hooks](https://learn.chatgpt.com/docs/hooks).
It needs no model API key, extra inference, or cloud service. Install the small
handlers beside the active user configuration:

```bash
python3 tools/codex_pet/bridge.py install-hooks
python3 tools/codex_pet/bridge.py run
```

Installation preserves unrelated hooks, backs up an existing file, and adds
handlers for session start/end, user prompts, tool start/end, approval requests,
turn stops, and interrupts. **Review and trust the new hook definition in Codex;
untrusted hooks are skipped.** Reload the Codex session/configuration as needed
and start a new turn. CLI-only sessions rely on observed hooks; local desktop
sessions also receive the startup snapshot reconciliation described below.

Lifecycle hooks send event kinds, hashed session/turn/tool IDs, and an input-wait
flag to loopback UDP 19283. They do not forward prompts, results or assistant
messages. In interactive mode, a PermissionRequest hook additionally sends its
session ID, tool name and arguments to a bounded **local-only** broker on TCP
19286. Those details are necessary to review the actual operation. They are
neither logged nor stored by the bridge. A decision applies to that exact pending
request; interruption, expiry or duplicate Confirm cannot authorize a different
request. The hook waits at most 115 seconds, then returns `{}` so Codex continues
with its ordinary desktop approval. When the bridge is absent it returns quickly.
The installed PermissionRequest hook timeout is 120 seconds; other hooks use one.
See [Codex's supported hook decisions](https://learn.chatgpt.com/docs/hooks).

Status heartbeats use HMAC-SHA256 over UDP 19284 once per second. The key is not
transmitted; increasing counters reject duplicate/reordered frames during a boot.
Status is authenticated but unencrypted. The overview combines observed hooks with
read-only snapshots of local desktop-owned chats, independently of the selected
voice/action target. Owner discovery is pipelined on one temporary IPC connection;
a sweep has a 12-second deadline and unsubscribes its snapshot observers. It starts
at bridge startup and repeats 10 seconds after success, or 5 seconds after failure.
Snapshots retain only status facts in memory and never log conversation content.
Newer hooks, including session closure, take precedence over a concurrent snapshot.
CLI chats continue to use hooks; remote/cloud execution is outside this local scan.
An incompatible desktop IPC version produces unknown status instead of false idle.
A stopped turn is not proof of task success. Lost hooks are not replayed; an active
turn with neither fresh hooks nor a desktop snapshot for 30 minutes becomes unknown.

Control, audio and rendered text use TCP 19285. A mutual HMAC challenge authenticates
both peers with the pairing key; random client/server nonces derive separate
AES-256-GCM keys for each direction and connection. Counters and authenticated
records reject tampering/replay. A disconnect discards unfinished audio; bridge drafts resume after authenticated reconnection.
Only the authenticated status sender identifies the desktop IP. Allow local UDP
and TCP through the firewall; guest/client-isolated networks or leaving Wi-Fi
range disconnect the companion. The computer bridge must remain running.

## Enable voice and Confirm

Install the [bridge dependencies](../tools/codex_pet/requirements.txt) in a local
Python environment and run the bridge with the Codex desktop open:

```bash
python3 tools/codex_pet/bridge.py install-hooks
python3 tools/codex_pet/bridge.py run --interactive
```

Trust/reload the hooks in Codex. Native controls require macOS Accessibility access
for the process launching the bridge, Codex microphone permission, and the updated
card firmware. The microphone selected in Codex is used. No local recognizer,
model download, audio upload from the card, or input-mode selection is needed.
The old speech/model/language options, card recorder, PCM receiver, transcript
cache/prefill and CLI first-message runner have been removed. Cached models and
installed user software are not deleted.

Choose an existing chat's project and title on the card, or hold Up in the
project list to open a native new chat in the selected saved project. In the
session list or new-chat view, hold Confirm to press the composer's Dictate button. Speak toward the
computer microphone once PC DICTATION appears. Release Confirm to press Stop
dictation, which inserts text; Transcribe and send is never pressed. Codex owns
recognition, language, punctuation and insertion. Wait for the text to appear,
then short-press Confirm to press the chat's Send button. The live composer owns
attachments, mentions, settings, validation and clearing; the bridge does not
read/reconstruct a saved draft or submit a turn through IPC. During an active run,
Confirm presses the native Queue or Steer control according to Codex's current
submission mode. Disabled controls and Stop/Resume are never pressed as Send.

Only one exactly identified chat view is accepted, using its page URL or current
sidebar link. Embedded browser panels/dialogs cannot supply the controls. The
`composer_action.m` helper is compiled once at bridge startup with Xcode Command
Line Tools. It uses Accessibility actions, without screen coordinates, global
keystrokes or desktop-state writes. Controls support English, Simplified Chinese
and Traditional Chinese labels. A press acknowledgement is not proof of message
delivery: Codex may still show validation or a confirmation dialog.

The card advertises `pc_dictation: true` and accepts mode 10. Its worker waits
for release without audio hardware access and sends Stop on release or after a
30-second hold. Old firmware receives an update notice before PC capture starts.
The bridge cancels its owned capture on disconnection, a 35-second receive timeout
or shutdown. It rejects existing manual dictation. Stop/Cancel never navigate or
fall back to Send. If cleanup cannot find the controls, stop dictation on the PC.
Do not manually replace the same capture while holding the card button.

Confirm consumes the current screen token before any side effect; uncertain
outcomes are not retried. Failure logs contain only reason codes. During an
approval, hold/release operates dictation and restores the same request/page;
short Confirm approves only that request after all pages have been seen. No
transcript is shown or stored on the card. Cross-application/global dictation is
outside this selected-chat integration.

## Validation and device acceptance

Run `./tools/validate.sh` with ESP-IDF 5.5.3 activated. Host tests cover strict USB
snapshot parsing, partial/oversized input, heartbeat expiry, multiple sessions,
waiting priority, stale turn events, privacy filtering, hook installation, and
wireless packet signatures, button policy, cross-session isolation, paged review,
approval expiry/interrupts, and encrypted transport. Firmware validation builds and verifies the merged
image and matching debug archive. Artwork must be imported before building.

After explicit flash approval, verify QR readability and Wi-Fi joining on iPhone
and Android, automatic portal opening and both manual fallbacks, scan refresh and
hidden/Unicode SSIDs, wrong-password/timeout retry, credential retention on failed
connection and successful save/restart. Verify pet appearance/animations, first setup,
wrong credentials, saved credentials, offline transition and reconnection. Check
all three physical keys, press/release/long-press ordering, PC microphone,
30-second hold limit, Chinese approval pagination, duplicate-title Session
selection, cancellation, stale/expired Confirm, and actual Codex follow-up and
tool approval/denial. Check that unrelated approvals and Session closure cannot
redirect an action. Measure heap/largest block during dictation control, animation and Wi-Fi,
and battery runtime. Compilation does not establish runtime/power behavior.

Current delivery checkpoint: wireless status, Session buttons, native Codex
dictation/Send, paged approvals and request-specific permission broker are
implemented. Host tests and complete build identities are reported with delivery;
complete functional acceptance and Codex write operations remain unverified. See the [device handoff](development/ai-guide.md#offer-on-device-testing)
and [flashing/data policy](development/engineering/firmware-layout.md#flashing-and-stored-data).

The following checkpoints record the retired implementation and do not establish
physical acceptance of the current native controls.

Historical merged image: 2,809,024 bytes, SHA-256 `68972f2ebd773cdb2e37a081dc751f642754e771d937d26286a78ebfa727e6d3`.
Build: PASS. Host tests: PASS. Device tests: PASS for flash integrity, a bounded 25-second startup observation, Wi-Fi reachability and the encrypted bridge handshake only.
Unverified: transcript accuracy, remaining button/review edge cases, reconnect behavior, and real permission execution.

Device checkpoint (2026-10-11): flashed the matching bootloader at `0x0` and
application at `0x10000` via `/dev/cu.usbmodem21201`; write hashes verified.
The existing partition table was retained (factory: 3 MB at `0x10000`), along
with NVS, PHY, image/audio and identity data regions. The application fits this
on-device layout; the merged image was not written. Startup reached LVGL, battery,
buttons and the setup AP without crash markers. Free heap: 96,852 bytes; largest
block: 86,016 bytes. This is startup evidence, not a peak-audio memory measurement.

Wireless checkpoint (2026-10-11): after user setup, the device joined the local
Wi-Fi network and remained reachable after restart. Its application pairing key
was saved directly into the private desktop configuration (mode `0600`); the
temporary NVS capture was deleted. The bridge authenticated the device and
established its AES-GCM control channel on TCP 19285, returning the Session
screen. This confirms transport, not physical rendering or button acceptance.
The bridge is running locally; no lifecycle event has yet been observed.

The user confirmed the physical Session screen and successful UP/DOWN chat
switching. Corresponding authenticated button commands were observed by the
bridge. Voice review and subsequent send/approval acceptance remain pending.

Hook checkpoint (2026-10-11): all eight companion definitions are enabled and
trusted, verified through Codex hooks/list after the user authorized trust.
No lifecycle event is observed in the running bridge yet; existing desktop
chats may need to reload configuration. Device commands also delivered 75,776
PCM bytes, reached transcript-review mode, and processed a physical Confirm
without a desktop-send error. Transcript accuracy, destination visibility and
real permission execution remain unverified.

Restart checkpoint (2026-10-11): the user reported that work-state display
recovered after restarting Codex, and the bridge observed `CP1 working 1 0`.
A separate EOF during owner discovery had left its refresh flag set; the bridge
now clears that flag on failure and retries discovery. Diagnostics can be enabled
with `--diagnostics`; they log event kinds, selection-match flags and counts,
without prompts, tool arguments, transcripts, keys or Session IDs.

Reconnect testing also exposed a firmware key-change defect: ESP-IDF's AES-GCM
context retains its GHASH table after setting a new key. A new authenticated
TCP connection derives new keys, so reusing the old contexts breaks record
authentication after the first connection. The correction frees and initializes both GCM contexts before installing each
new connection's keys. Host tests cover desktop EOF recovery, uncertain-send
handling, and fresh connection keys rejecting records from a previous connection.
The firmware correction passed the complete validation gate and archive verification;
authorized flashing and bounded reconnect checks are complete. Physical interaction
acceptance after the update remains pending.

Reconnect-fix candidate: merged image 2,809,072 bytes, SHA-256
`63b9ec9b0b256ef68a2ac97bef8741edd88cac7b717909aa56f6cf69d13cc518`;
application 2,743,536 bytes, SHA-256
`70b1566b1108834fd1cf1ad9c03a626d44818e4ca0e40124138e45f3ab88efa5`;
matching ELF SHA-256
`6661fecc22a6d20048ab4990de711a9ee37ac161c2fb4d13871f5bde4c0d2720`.
The application fits the retained 3 MB factory partition. Following explicit user
approval, only this application was written at `0x10000` via `/dev/cu.usbmodem21201`,
preserving the bootloader, partition table and stored data. The write hash passed.
A bounded 25-second startup capture showed the matching ELF prefix `6661fecc2`,
no crash markers, 109,900 bytes free heap and a 98,304-byte largest block.
The saved Wi-Fi and pairing remained usable. Three successive bridge restarts
each established exactly one authenticated connection, received at least five valid
encrypted sync requests and returned the Session frame without a traceback.
The final connection continued through at least 30 encrypted syncs, with a loaded
chat selection and real lifecycle events. The desktop bridge remains running;
the serial capture is closed.
Build: PASS. Host tests: PASS. Device tests: PASS for flash integrity, startup,
Wi-Fi/pairing retention and three encrypted reconnects.
Unverified: physical interaction after reconnect, transcript accuracy and real tool approval.

Source-level rekey reproduction: compiled the actual ESP-IDF 5.5.3 GCM port
with a macOS CommonCrypto software AES adapter and compared it with
cryptography AESGCM. Reusing the context with a second key produced a mismatched
tag; freeing/initializing it before the second key matched both ciphertext
and tag. This is a host reproduction, not a hardware crypto test.

QR provisioning checkpoint (2026-10-12): the setup screen now has a Wi-Fi QR and
an OK-toggle webpage QR, retaining manual AP credentials/address. The portal
adds asynchronous network discovery and validates a target connection before
persisting credentials. Host checks cover QR escaping/bounds, malformed DNS and
A/AAAA responses, connection timeout and retry policy. A 390-pixel browser
check against synthetic endpoints passed network selection, password visibility,
failed-connection retry, safe SSID text rendering and success/key handoff. These
checks do not test the real radio, DHCP or phone captive-portal detection. Exact
firmware/debug identities are reported in the delivery; real iPhone/Android QR
scanning, automatic opening, repeated setup and memory use remain unverified.

Validated QR-provisioning candidate: merged image 2,860,528 bytes, SHA-256
`a919e0c561269054125fb1acc8d15c7342ab5d6bf1dcc7cd96e9f8882ca2157f`;
application 2,794,992 bytes at `0x10000`, matching ELF SHA-256
`805a23154547f9cbb3750e90b63ca56fd9344dd3d81d37278f7348a5bb9b1737`.
The debug bundle is `build/firmware/a919e0c561269054125fb1acc8d15c7342ab5d6bf1dcc7cd96e9f8882ca2157f/`.
The complete gate and explicit archive verification passed. The application fits
the previously recorded 3 MB factory partition; no firmware was flashed for this
iteration. Build: PASS. Host tests: PASS. Device tests: NOT RUN.
Unverified: physical QR rendering/scanning, phone portal detection, radio setup
retry/save/restart and setup heap/stack usage.

QR firmware flash checkpoint (2026-10-12): after explicit approval, the application
from the `a919e0c561269054125fb1acc8d15c7342ab5d6bf1dcc7cd96e9f8882ca2157f`
bundle was written at `0x10000` through `/dev/cu.usbmodem21201`. Application SHA-256
`496af7ee202484fecf3834ef433c8270c407ca1ca40981afab52f4f7c81091be`.
The installed partition table was parsed and its MD5 checked before writing:
the existing factory application occupies 3 MB at `0x10000`, and the application
fits. The write hash passed; bootloader, partition table, NVS, PHY and resource/
identity data partitions were not written. A bounded 25-second startup capture
showed matching ELF prefix `805a23154`, no crash markers, 101,496 bytes free heap
and a 90,112-byte largest block. The device started in setup AP+STA mode with
its AP DHCP server running; no station IP was observed during this window. The
serial port was closed. Build: PASS. Host tests: PASS. Device tests: PASS only
for flash integrity, matching startup and AP/DHCP initialization.
Unverified: physical QR rendering, OK switching, phone QR joining/automatic
portal opening and actual configuration scan/retry/save/restart.

Session/voice checkpoint (2026-10-12): the interactive list hides the pet and
shows sidebar titles, named projects, selection position, and nearby chats.
Legacy desktop project assignments and saved project-root matching are supported.
Releasing OK stages recognized text in the selected desktop composer; device OK
reads the current persisted draft, including PC edits. Desktop submit/delete ends
review, while cancellation preserves the PC draft. Existing drafts are not
overwritten. Empty desktop prefill routes cannot clear the composer after device
submission; check retained text on the PC. These changes were subsequently deployed in the authorized flash checkpoint below. Focused bridge tests: 30 PASS, including
encrypted voice transport, edited drafts, missing acknowledgement, uncertain-send
consumption, title/project metadata, and CJK panel bounds. The complete gate and
final static gate passed; independent firmware archive verification passed.

Verified merged image: 2,860,608 bytes, SHA-256
`2761da14ad58108f44b645184034e236bc8d8077e70232a5fc3e7cd4138f73d1`.
Application: 2,795,072 bytes at `0x10000`, SHA-256
`df124e610fbd071c8e1a813b3882967dfcc7a964e19d7c380c4edc49262189fc`.
Matching ELF SHA-256:
`8fa45e1378e1629627d9d3b8f0244835ebc4c3ee43f495658621d9ea4745a2d6`.
Archive: `build/firmware/2761da14ad58108f44b645184034e236bc8d8077e70232a5fc3e7cd4138f73d1/`.
Session/voice device flash checkpoint (2026-10-12): after explicit approval, the
verified application above was written at `0x10000` through `/dev/cu.usbmodem21201`.
A fresh installed partition-table read passed MD5 and bounds checks; the existing
3 MB factory partition was retained. Only application sectors `0x10000` through
`0x2bafff` were erased/written. Write-hash verification passed. A bounded 25-second
startup capture matched ELF prefix `8fa45e137`, showed no crash markers and
confirmed a station IP. Free heap was 108,656 bytes; largest block was 98,304 bytes.
The serial monitor was closed. The previous bridge was stopped gracefully and
restarted with the updated implementation. An authenticated encrypted device
connection, list screen mode and recurring encrypted syncs were observed.
Build: PASS. Host tests: PASS. Device tests: PASS for application write integrity,
matching startup, Wi-Fi initialization and encrypted bridge connectivity only.
Unverified: physical list/CJK layout, microphone/transcript quality, actual desktop
prefill/edit/submit, composer state after device send, and voice-flow timing/reconnect.
The first physical voice attempt received 59,392 PCM bytes and produced a transcript,
but staging failed because this desktop stores `prompt` as a document rather than a
string. The bridge now decodes text paragraphs, line breaks and position marks,
while rejecting attachments/mentions and preserving existing drafts. All five
current persisted drafts decoded successfully without exposing their text. Two
regression tests cover document edits, empty prefill, duplicate-send suppression
and rejection of rich context; all 30 focused tests passed. The bridge was restarted
again with this fix. The bridge remains running for physical acceptance; logs contain
action kinds and acknowledgement outcomes without transcript text or conversation
identifiers. Actual composer acknowledgement and device submit await a repeat test.

Continuous dictation follow-up (2026-10-12): after the user clarified that speech
must extend an existing draft, the adapter now appends each segment to the latest
persisted text, including PC edits. Review mode permits another long OK without
submitting. The firmware now wakes the codec before repeated recording; previously,
the first recording slept it and the next format call rejected the sleeping state,
causing control reconnects. The review footer explains add/send. Cursor-position
insertion remains unsupported by the current prefill route. This follow-up firmware
is a new candidate and has not yet been flashed; do not confuse the initial flash
checkpoint with validation of repeated recording.

Verified continuous-dictation candidate: merged image 2,860,944 bytes, SHA-256
`f3773dfd781f25d8252fb610873df1449bb835d85c3e9379b4a4db22c032588c`.
Application 2,795,408 bytes at `0x10000`, SHA-256
`46d33b90ce22b43a83c72215695035d43431bfd5afd10c3acf3c50d4412a4408`.
Matching ELF SHA-256
`a3baf0384e1de34683bd926901e931ddfdccf288e065f97b0775a1a8a7c82712`.
Archive: `build/firmware/f3773dfd781f25d8252fb610873df1449bb835d85c3e9379b4a4db22c032588c/`.
Complete gate and independent archive verification passed. Focused bridge tests:
32 PASS. Build: PASS. Host tests: PASS. Device tests: NOT RUN for this candidate.
Unverified: repeated microphone wake/capture, accumulated desktop draft/prefill,
PC edits followed by device submit, and actual screen behavior. Automatic cursor
insertion is not implemented; only preserving text and appending at the end is
implemented. Approval for the initial flashed image does not identify this new
candidate; obtain its flash consent before an application-only write.

Continuous-dictation application flash (2026-10-12): after explicit approval, the
`f3773dfd781f25d8252fb610873df1449bb835d85c3e9379b4a4db22c032588c`
candidate was deployed through `/dev/cu.usbmodem21201`. A fresh installed
partition-table read passed MD5 and bounds checks; the existing 3 MB factory
application partition at `0x10000` fits the verified 2,795,408-byte application.
Only sectors `0x10000` through `0x2bafff` were written, and the write hash passed.
Bootloader, partition table, NVS, PHY and resource/identity partitions were retained.
The bounded 25-second startup capture matched ELF prefix `a3baf0384`, showed no
crash markers and confirmed a station IP. Free heap was 108,656 bytes; largest
block was 98,304 bytes. The serial monitor was closed. The updated bridge was
restarted and observed a fresh authenticated encrypted connection, list screen
mode and recurring encrypted syncs. Build: PASS. Host tests: PASS (32 focused
bridge tests). Device tests: PASS for flash integrity, matching startup, Wi-Fi and
encrypted bridge connectivity only. Unverified: physical repeated recording,
accumulated desktop text, PC edit/device send and screen rendering. Automatic
cursor-position insertion remains unsupported; segments append at the end.

Selection/script follow-up (2026-10-12): the bridge now renders the entire selected
chat row as a full-width inverted rounded card, including title and project; the
position badge is on the project line to preserve title space. The 216x144 panel,
3,888-byte bitmap and 3,905-byte encrypted screen payload remain unchanged; no
firmware change is needed. New transcripts use OpenCC `t2s` by default, as explicitly
requested by the user, while existing drafts are retained verbatim. Host tests cover
highlight movement/first-last positions, panel bounds, script conversion, English
preservation, multi-segment append and unchanged existing traditional text.
Focused bridge tests: 36 PASS. The updated bridge was restarted without flashing firmware; authenticated encrypted
syncs resumed. The user confirmed that the physical highlight and Simplified Chinese
output both work as expected. A new voice capture received 312,320 PCM bytes and
staged a 37-character transcript with desktop composer acknowledgement; a subsequent
selected-chat UserPromptSubmit event was observed. No transcript text was logged.
Device tests: PASS for the user-confirmed highlight/script behavior and observed
voice transport/composer acknowledgement. Remaining checks: long-recording limits,
reconnect during capture, and concurrent desktop edits during prefill.

Selection/script complete gate: PASS, including independent archive verification.
Validation archive (not flashed): `build/firmware/5bcaed966b005bd840b24e7c6f5504e3cabe07502ef6887681d850a05149b2a2/`.
Merged-image SHA-256 `5bcaed966b005bd840b24e7c6f5504e3cabe07502ef6887681d850a05149b2a2`; matching ELF SHA-256 `144cfc5dcda660b24a65352d4f6a12fc5b7e829761a2530e2f0fffe6db6ca8fa`.
The device remains on the approved `f3773dfd…` flash checkpoint; these UI/script
changes run in the restarted computer bridge. Build: PASS. Host tests: PASS
(36 focused tests). Device tests: PASS for the confirmed highlight and simplified
output samples. Unverified: long captures, capture-time reconnect and concurrent
PC edits during whole-document prefill.

Voice-speed/sentence follow-up (2026-10-12): reuse a bridge-owned local Whisper
worker and keep automatic language detection for Chinese/English, as requested.
The same base multilingual model is retained. Finish each new segment with `。`
when it contains Chinese or `.` for English, preserving existing sentence
terminators and every character of the prior draft. Focused tests additionally
cover worker reuse, loopback multipart WAV transport, bounded responses, startup
timeout/forced cleanup, failure recovery and successive bilingual sentence endings.
A synthetic 6.152-second Mandarin clip, three runs per backend on this Apple M4,
took 2.539 seconds median with CLI loading versus 0.457 seconds with the resident
worker (about 82% less transcription time); all six transcripts were identical.
Worker startup took 1.592 seconds before recording. These measurements exclude
audio capture, encrypted transport, the draft-settling delay and desktop prefill.
Separate English and Mandarin clips passed local inference. A concatenated clip
switching from a full Mandarin sentence to English omitted the English tail with
both backends; this sample does not establish mixed-speech accuracy. The bridge
was restarted with the resident worker. Concurrent project-navigation changes in
the shared workspace introduce new screen modes; the previously flashed firmware
does not support them. Device tests: NOT RUN for the speed/punctuation change.
Unverified: physical voice-release-to-composer timing, punctuation and mixed-speech
accuracy on the user's microphone; project UI requires its matching firmware.

Voice follow-up validation: complete gate and independent archive verification
PASS. Focused bridge checks: 64 PASS (57 interaction/speech and 7 bridge tests).
Validation archive (not flashed):
`build/firmware/90f5c284a18ddacb34b43196cacb003074cb651803cdd6d3805771956b2d7833/`.
Matching ELF SHA-256:
`27070d5a993990d028b26a172e5ba8e6e5d205ba891632ca72e35db221e24028`.
Build: PASS. Host tests: PASS. Device tests: NOT RUN for this voice follow-up.
The speech changes run in the restarted bridge; the shared project-page firmware
candidate is a separate device-deployment concern.

Project session catalog fix (2026-10-13): entering a project lists all its saved
nonarchived root chats, including unloaded chats and entries beyond the previous
80-chat limit. Current-host project migration IDs now match the catalog and chat
assignments. All 62 focused interaction tests passed in the bridge environment;
the complete gate and independent firmware archive verification passed. The
bridge was restarted and the device resumed authenticated encrypted syncs. No
firmware source changed and no firmware was flashed for this fix.
Validation archive: `build/firmware/837b587f8d66973343e4fccd0a8df3bfaed89385923696ef8c744b8690b1f444/`.
Merged-image SHA-256: `837b587f8d66973343e4fccd0a8df3bfaed89385923696ef8c744b8690b1f444`.
Matching ELF SHA-256: `ad564fb5e3dde53b2c5a42aa0c250bc1b4a2c0db5782be336ab2a449e3e85321`.
Build: PASS. Host tests: PASS. Device tests: NOT RUN for physical project-list
acceptance. Unverified: physical project entry, complete-list navigation and
selection restoration on the device.

Voice composer restoration (2026-10-13): releasing OK transcribes and appends
text to the selected desktop chat's existing input; a separate OK click submits
the current PC draft. PC edits refresh the device preview, and exiting preview
preserves the PC draft. The adapter waits for prefill acknowledgement and checks
the draft again before submitting. All 62 focused interaction tests passed in
the live bridge's dependency environment. Repository checks passed. The bridge
was restarted and the device reconnected with authenticated encrypted syncs.
No firmware code was changed or flashed for this voice correction.
Build: FAIL for the current workspace gate because the separately changed
firmware requires the missing `assets/images/codex-pet/offline.inc` asset.
Host tests: FAIL for the overall suite: two lifecycle tests and one overview test
still expect `offline` while the separately changed state logic returns
`idle`/`error`; the 62 voice/interaction tests passed. Device tests: NOT RUN for
the corrected voice workflow. Unverified: microphone release-to-prefill timing,
actual PC edits/device submit, concurrent edits during whole-text prefill, and
the input box after submission.


Voice transcription independence (2026-10-13): hold OK to record, release to
transcribe and fill the selected PC input, then click OK to send only the
device's voice transcript. The bridge no longer reads persisted PC drafts,
tracks PC edits/clears/submissions, waits for prefill acknowledgement, or checks
for a loaded owner before recording. Consecutive recordings accumulate only
voice text within the current bridge draft; input filling replaces existing PC text.
A failed fill retains the transcript. Explicit sending still consumes the review
token before IPC, preventing retries with the same confirmation. The running
bridge was restarted with its existing settings; authenticated device reconnect
and 30 encrypted syncs were observed without a runtime traceback. No firmware
behavior changed and no firmware was flashed for this fix.

Build: PASS (`./tools/validate.sh --firmware` and independent archive verification).
Host tests: PASS (86 focused tests: 62 interaction/speech, 10 bridge and 14 overview).
Device tests: NOT RUN for physical voice/fill/send acceptance.
Unverified: microphone transcription, actual PC filling and device-confirmed
voice submission. The complete `./tools/validate.sh` gate stopped at pre-existing
English-document language errors in `assets/README.md` and this guide's status
text; those unrelated changes were preserved.
Validation archive (not flashed): `build/firmware/df2b125065f9a0d6748d0e37c870f5e2f275b133a1b240002e7fa31e83d9c4b7/`.
Merged-image SHA-256: `df2b125065f9a0d6748d0e37c870f5e2f275b133a1b240002e7fa31e83d9c4b7`.
Matching ELF SHA-256: `fd8a9e33b96cebe8a4546b491cab38f44da93813b870e62cc4f2c5eaeb5fa7ea`.

New-chat voice fix (2026-10-13): holding UP in a saved project now prepares a
recordable device draft instead of leaving the device in a notice that consumes
OK-hold. Hold OK, release to transcribe, then click OK to create the chat and send
the first voice message through the approved local CLI path. Cancel, expiry and
stale confirmation do not create or resend a chat. The selected project remains
pinned; database and legacy roots are merged, including resolved symlink paths.
The desktop opens the exact created chat only after the first CLI process exits.

The complete ESP-IDF 5.5.3 gate and independent archive verification passed.
The final full-dependency static gate passed 103 focused bridge checks without
skips: 71 interaction/speech, eight fresh-chat subprocess/project tests, ten
hooks/bridge and 14 overview/rendering tests. The installed CLI and all seven
saved project folders were checked without sending a real prompt.

The bridge was restarted with its existing configuration. The separate four-entry
candidate changes the control bitmap to 216-by-192, while the deployed firmware
expects 216-by-144. The ignored local deployment wrapper retains the deployed
height and three list entries; source changes for the four-entry candidate are
preserved. Legacy project/session/new-chat frame sizes were checked locally.
Authenticated reconnect and sustained encrypted syncs were observed after this
compatibility adjustment. No firmware was flashed for this bridge fix.

Build: PASS. Host tests: PASS. Device tests: NOT RUN for physical new-chat voice.
Unverified: microphone transcription, real first-voice submission, CLI-to-desktop
handoff and follow-up on the device, abrupt bridge termination and manual takeover.
Verified validation archive (not flashed):
`build/firmware/b3b16ffb96e8934d090a86594bf33860d9126f57acc5f4ac6c0f9951e2aa9422/`.
Merged-image SHA-256: `b3b16ffb96e8934d090a86594bf33860d9126f57acc5f4ac6c0f9951e2aa9422`.
Matching ELF SHA-256: `7880cd687aec36aa42061415d7df2742fa9089fcb5e43f4ea50dd12e4332fa8d`.
