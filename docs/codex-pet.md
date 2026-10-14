<p align="right"><a href="codex-pet.zh_CN.md">简体中文</a> · <strong>English</strong></p>

# Codex Pet on AI Passport

This application replaces the baseline test menu with a dedicated companion
screen using the original blue Codex pet. Normal operation is wireless: the
computer and AI Passport join the same 2.4 GHz Wi-Fi network, and the device runs
from its battery. USB is needed for initial flashing or optional wired status.

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
While the bridge is connected, no observed tasks or all closed sessions show
the Chinese equivalents of “No tasks” and “Ready for your next task”, with the
relaxed blinking pet. Idle sessions stay idle even after 30 minutes. An active
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
and turn-state changes do not extend this timeout. Recording and transcription
stay visible until completion, then begin a fresh 10-second window. A sleeping
voice preview or approval resumes its existing review without sending or deciding it.
The bridge saves only the last chosen project/chat IDs in a private
`codex-pet-selection.json` under its Codex directory, restoring them across control
reconnections and bridge restarts. Archived or removed chats fall back to an available chat;
an empty list cannot record or submit. Hold UP in the session list to browse saved
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
in a 216-by-224 panel at y=45 below the header, retaining the 16-pixel font and
20-pixel line spacing. The panel leaves nine pixels before the button hints at
y=278. Review pages retain their 192-pixel crop at y=85. The selected
entry can wrap its title onto two lines and has a full-width inverted card;
selected chats also retain their short ID. List position counters are omitted.
Project cards retain their saved-chat counts. Each chat row shows its
actual Codex sidebar title and saved project name; the first user prompt is never
used as its title. Unnamed chats and unassigned projects have explicit fallback labels.
Working, waiting for approval/input, and finished
turns use different original animations. After five seconds without a valid
heartbeat the state becomes offline. A finished turn means Codex stopped its
turn; it does not certify that the requested work succeeded.

The [standalone button guide](codex-pet-buttons.md) contains the complete
per-screen map for clicks, holds, recording release, Power, Wi-Fi setup, and
automatic return behavior.

Holding UP on a saved local project prepares a new device chat. Hold OK to record,
release to transcribe, then click OK in preview to create the chat and send the
first voice message. The project stays pinned; list refresh and wake cannot send
the draft to an existing chat. New-chat voice stays on the device before
confirmation. No placeholder prompt is sent. `No project`, unavailable folders,
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
shows a short ID so identically named chats remain distinguishable. Recording
and review pin the destination; buttons cannot switch it until completion or
cancellation. A displayed review token, rather than the latest unseen network
update, accompanies every action. Confirmation consumes a review before sending;
a missing desktop acknowledgement displays an uncertain outcome and never retries.

English labels use Montserrat. Dynamic Chinese text is rasterized on the computer
using a locally installed CJK font and transferred as a 216 × 224 one-bit image
(6,048 bytes; 6,081 bytes per encrypted record including headers and tag).
This control-panel size requires the matching bridge and firmware
to be updated together; the independent home overview keeps its existing dimensions.
The bridge checks the font's Unicode coverage before rendering;
unsupported review text disables confirmation and directs the user to the PC.
No fixed CJK menu subset is claimed to support arbitrary transcripts. Font files
are not redistributed. The UI owns a small image buffer; PCM is streamed in
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
and start a new turn. The bridge cannot reconstruct sessions that started before
it was running; the first complete observed turn establishes its state.

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
Status is authenticated but unencrypted. Interactive mode follows the selected
Session's observed hooks; a session without observed hooks remains unknown.
A stopped turn is not proof of task success. Lost lifecycle events are not replayed;
a crash with no terminal event becomes unknown after 30 minutes without hooks.

Control, audio and rendered text use TCP 19285. A mutual HMAC challenge authenticates
both peers with the pairing key; random client/server nonces derive separate
AES-256-GCM keys for each direction and connection. Counters and authenticated
records reject tampering/replay. A disconnect discards unfinished audio and reviews.
Only the authenticated status sender identifies the desktop IP. Allow local UDP
and TCP through the firewall; guest/client-isolated networks or leaving Wi-Fi
range disconnect the companion. The computer bridge must remain running.

## Enable voice and Confirm

Create a local Python environment and install
[bridge dependencies](../tools/codex_pet/requirements.txt). Install `whisper-cli` and `whisper-server`
from [whisper.cpp](https://github.com/ggml-org/whisper.cpp), then download a
multilingual GGML model using its official model downloader (the English-only
`.en` models do not cover Mandarin). The default model path is
`~/.cache/ai-passport/ggml-base.bin`; use `--model` for another local model.

```bash
python3 tools/codex_pet/bridge.py install-hooks
python3 tools/codex_pet/bridge.py run --interactive --model /absolute/path/to/ggml-base.bin
```

Trust/reload the updated hooks in Codex. No approval is enabled by changing the
trust store automatically. The computer transcribes locally, without a model API
key or uploading audio. Captures are 16 kHz, 16-bit, mono, limited to 30 seconds.
Each recording uses Whisper's automatic language detection. Newly recognized text
is normalized to Simplified Chinese with [OpenCC](https://github.com/yichen0831/opencc-python) by default before review,
so separate segments do not alternate scripts. Existing desktop text and chat
metadata are not converted. English and numbers remain intact. Each new recording
gets a sentence-ending period when missing (`。` for Chinese-containing text, `.`
for English); existing periods, question/exclamation marks and ellipses are retained.
Use `--chinese-script traditional` for traditional output or `--chinese-script keep`
to preserve the recognized Chinese script. Install the bridge requirements to obtain
`opencc-python-reimplemented`; conversion is local and does not improve recognition
accuracy or change a mistaken word into the intended word.
By default, the bridge starts its own `whisper-server`, bound only to `127.0.0.1`,
and loads the existing model before device recording. Subsequent recordings reuse
that model with zero text context across requests; language detection remains
automatic for Chinese, English and mixed speech. WAV requests stay in memory and
the worker is stopped when the bridge closes. An empty private directory is used
for its public-file root. If `whisper-server` is absent, `auto` uses the CLI; use
`--asr-backend cli` to explicitly return to per-recording loading, or `server` to
require the resident worker. A failed worker stops; the next recording can restart
it. CLI temporary WAV/transcript files are private and deleted after conversion;
a process crash may leave temporary files requiring manual cleanup. For existing chats, releasing OK
transcribes the recording, displays the voice text on the device, and requests
input filling for the selected desktop chat. Holding OK again in preview appends
the next segment to the device's voice text. Clicking device OK sends that voice
text to the selected chat, independently of the PC input. Recording and input
filling do not start a turn. Voice submission does not require visiting every
transcript page; tool approval still requires reviewing every page.

For existing-chat recordings, the bridge does not read the PC draft, synchronize PC edits, wait for prefill
acknowledgement, or infer whether the PC has sent or cleared its input. Each fill
requests the entire voice transcript through the macOS existing-chat route,
replacing any existing PC input rather than merging it. Only consecutive voice
segments within the current preview accumulate; exiting or expiring the preview
starts a fresh transcript on the next recording. PC editing, sending and clearing
remain independent. A failed input-fill request retains the device transcript
for review and explicit submission, without a PC-input error or automatic retry.
Cancel, expiry and disconnect end device review without clearing the PC input.
The route does not support insertion at the cursor or clearing the composer after
device send; manage the retained PC input directly on the computer.
The current review token is consumed before IPC submission, so stale or repeated
confirmation cannot retry a send whose acknowledgement is uncertain. Check the
selected chat on the PC if the send outcome is unknown. Actual input filling and
voice submission remain desktop/device acceptance checks, not established by
fake-desktop tests.

For existing chats the desktop adapter uses the local thread owner's coordination
IPC and never resumes a second executor. Only a confirmed new-chat first message
starts a fresh `codex exec --json --cd <saved-project-folder> -` process; voice
is passed through stdin without a shell or prompt logging. This uses existing
CLI authentication and configuration, retains normal sandbox/hook-trust rules,
and does not override the model or permissions. CLI settings may differ from the
desktop composer; the bridge does not grant additional edit or approval rights.
See [OpenAI's non-interactive CLI guide](https://developers.openai.com/codex/noninteractive).
`CODEX_CLI_PATH` can select an installed executable; on macOS a matching installed
Codex application bundle is checked before the PATH command. A broken CLI fails
preparation without changing the installation or user configuration.

The bridge tracks the fresh thread ID from JSON events and drains all remaining
output without retaining it. It opens the chat on the desktop only after the CLI
exits, then selects that exact chat after catalog discovery. Bridge recording,
input filling and submission cannot take over a CLI-owned chat. Only one new-chat
first turn runs at once. Do not open that chat manually before the first turn ends;
keep the bridge running and stop gracefully with Ctrl+C. Canceling a submitted
notice only changes navigation, not the submitted task. A failed/uncertain first
turn asks for a PC check and never retries automatically. Abrupt bridge termination
and manual desktop takeover still require acceptance testing.

The adapter reads all nonarchived root-chat
metadata, with no recent-chat limit or requirement for a loaded desktop owner.
The background refresh updates the list as chats are created, archived or moved.
Project membership resolves legacy IDs through the current local host's migration
map and uses saved database roots for CLI chats without a project ID. Archived
chats, subagents and bridge-owned first turns are excluded. Recording and input filling do
not require a loaded desktop owner. Explicit device submission still uses an
existing desktop owner; open the selected chat on the PC first if it is unloaded. This is a
version-sensitive integration validated for the locally installed 0.160.0 CLI /
October 2026 desktop code; future IPC/database changes must be revalidated.
No private authentication database or account token is read.

The initial controls cover voice follow-up submission and **tool permission**
allow/deny. They do not answer arbitrary multi-choice questions, MCP elicitation,
or sign-in dialogs. A busy/closed chat can reject a follow-up; an uncertain send
result instructs the user to check that chat. Actual voice submission and real
approval execution are device-acceptance checks, not inferred from mocks.

For a device-free bridge check:

```bash
python3 tools/codex_pet/bridge.py run --dry-run
```

Optional wired mode needs pyserial and an explicitly chosen device port:

```bash
python3 tools/codex_pet/bridge.py run --port /dev/cu.usbmodemDEVICE
```

Do not open arbitrary ports or flash from connection detection alone.

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
all three physical keys, press/release/long-press ordering, microphone level,
30-second capture limit, Chinese review pagination, duplicate-title Session
selection, cancellation, stale/expired Confirm, and actual Codex follow-up and
tool approval/denial. Check that unrelated approvals and Session closure cannot
redirect an action. Measure heap/largest block during audio, animation and Wi-Fi,
and battery runtime. Compilation does not establish runtime/power behavior.

Current delivery checkpoint: wireless status, Session buttons, streamed audio,
local transcription, paged review and request-specific permission broker are
implemented. Host tests and complete build identities are reported with delivery;
complete functional acceptance and Codex write operations remain unverified. See the [device handoff](development/ai-guide.md#offer-on-device-testing)
and [flashing/data policy](development/engineering/firmware-layout.md#flashing-and-stored-data).

Verified local merged image: 2,809,024 bytes, SHA-256 `68972f2ebd773cdb2e37a081dc751f642754e771d937d26286a78ebfa727e6d3`.
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
voice text within the current preview; input filling replaces existing PC text.
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
