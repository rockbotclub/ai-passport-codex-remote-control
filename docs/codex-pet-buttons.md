<p align="right">
  <a href="codex-pet-buttons.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# Codex Pet Button Guide

This guide describes the current Codex pet application, including the new
hold-DOWN shortcut from the session/project list to the pet. Install the matching
firmware before expecting that shortcut on a device. See the
[application guide](codex-pet.md) for setup and desktop bridge instructions.

## Buttons and gestures

- **UP**, **DOWN**, and **OK** are the three software-readable function buttons.
- **Click** means press and release once. **Hold** means keep the button pressed
  for approximately 0.5 seconds until its long-press action triggers.
- **Power** controls hardware power independently; the current BSP exposes no
  software event for it. It cannot serve as a return/navigation button.
- Double-clicks have no assigned action. Simultaneous UP+DOWN is not a supported
  gesture. Use one function button at a time.

## Complete button map

“No action” means no application command is assigned to that gesture.

| Screen | Click UP | Click DOWN | Click OK | Hold UP | Hold DOWN | Hold OK |
| --- | --- | --- | --- | --- | --- | --- |
| Pet, interactive bridge connected | Open remembered session list or resume review | Same as UP | Same as UP | No action | Restart into Wi-Fi setup | No action |
| Project list | Previous project | Next project | Enter selected project's sessions | Prepare a new chat in the selected project | Return to pet immediately | No action |
| New chat, before recording | No action | No action | No action | Cancel draft and return to projects | Return to pet; preserve draft | Record first voice message; release to transcribe |
| Session list | Previous saved chat | Next saved chat | No action | Return to project list | Return to pet immediately | Record voice for selected chat; release to transcribe |
| Voice preview | Previous text page | Next text page | Submit voice to selected chat or create the prepared new chat | Exit review, keep PC draft, return to preceding list | Exit review, keep PC draft, return to preceding list | Record additional voice; release to append; fill PC input for existing chats |
| Approval | Next request page | Deny request and return to sessions | Allow after every page has been displayed | Deny request and return to sessions | Deny request and return to sessions | No action |
| Error | Dismiss and return to preceding list or prepared new-chat draft | Same as UP | Same as UP | Dismiss and return to preceding list or prepared new-chat draft | Same as hold UP | No action |
| New-chat notice | No action | No action | No action | Dismiss and return to preceding list | Dismiss and return to preceding list | No action |
| Recording | Locked | Locked | Locked | Locked | Locked | Keep recording; release OK to finish |
| Transcribing | Locked | Locked | Locked | Locked | Locked | Locked |
| Wi-Fi setup | No action | No action | Toggle hotspot QR / setup webpage QR | No action | No action | No action |
| Basic pet, no interactive control mode | No action | No action | Play pet interaction | No action | Restart into Wi-Fi setup, when networking is available | No action |

## Returning to the pet and reopening a screen

- **Hold DOWN in either list** to return to the pet. Selection stays unchanged;
  this local navigation does not cancel the PC chat or send a message.
- From the pet, **click any function button** to reopen the remembered list.
  The opening click does not also move selection, start recording, send voice,
  or approve a request. An unfinished voice preview or approval resumes instead.
- Project/session navigation wraps at the first and last entries. Voice-preview
  and approval pages also wrap.
- After **10 seconds without button activity**, interactive screens return to
  the pet even while Codex is working. Bridge heartbeats and status updates do
  not extend the timer. Recording/transcription remain visible until completion,
  then start a fresh 10-second window.
- Returning by inactivity does not submit the PC draft or decide an approval.
  Exiting voice review keeps the PC draft; deleting its text happens on the PC.
  Use the approval screen's controls to deny a request explicitly.
- After returning to the pet, release DOWN before holding it again for Wi-Fi
  setup. The return gesture itself does not enter setup.

## Voice, approval, and new-chat details

- Voice requires a live interactive bridge and either a selected existing chat
  or a prepared new-chat draft. The chat or new project remains pinned throughout
  recording, transcription, and review. Empty session lists still cannot record;
  return to projects and hold UP to prepare a new chat.
- Recording starts after the OK hold is recognized; speak when `RECORDING`
  appears. Release OK to finish. Capture is limited to 30 seconds. Releasing
  transcribes and requests filling the selected chat's PC input with the device
  transcript. A separate OK click sends that transcript to the selected chat.
- If no speech is recognized or transcription fails, click any function button
  to dismiss the error. The click only closes the error; it does not move the
  selection or send anything. The selected chat or prepared new-chat draft
  remains available, so a subsequent OK hold can record again. Holding UP or
  DOWN also dismisses the error. Install the updated firmware for click recovery
  and update the bridge for the matching speech-error instructions.
- Holding OK on a voice preview adds another recording to the device transcript,
  then fills the whole accumulated voice text on the PC. Existing PC input is
  replaced, not merged. The device does not read PC input, follow PC edits,
  detect PC sends/clears, or wait for prefill acknowledgement. Clicking OK sends
  only the device's voice text, even if the PC input was edited or cleared.
  Failed filling keeps the transcript available; no PC-input confirmation is
  required. Exiting preview keeps the PC text and starts a fresh voice transcript
  on the next recording. Device send may leave the PC input intact; manage it
  on the computer. If submission is not confirmed, check the chat before retrying.
- Approval UP advances to the next page; DOWN denies immediately. Clicking OK
  cannot allow a request until all its pages have been displayed. Holding UP
  or DOWN denies; it is not a neutral return-to-pet shortcut on this screen.
- Holding UP on a saved local project prepares a device draft. Hold OK to record,
  release to transcribe, then click OK to create the chat and send its first voice
  message. New-chat transcripts stay on the device until confirmation; they do
  not fill the PC composer. Holding OK in preview appends more voice. Cancel,
  expiry, and repeated confirmation never create or resend a chat automatically.
- The first turn runs through the local Codex CLI with its existing login and
  CLI configuration, without permission or hook-trust bypass flags. After that
  process exits, the bridge opens the saved chat on the desktop and selects it
  when discovered. Existing-chat follow-ups use desktop IPC. While the first
  CLI turn runs, the bridge cannot open or send another turn to that chat; do not
  open it manually on the PC. Keep the bridge running, and stop it gracefully
  with Ctrl+C to stop a pending first turn. An uncertain outcome requires a PC
  check before retrying. `No project`, unavailable folders, and shared project
  roots cannot use this shortcut.

## Wi-Fi and disconnected operation

- Enter Wi-Fi setup by holding DOWN **on the pet screen**. This restarts the
  device into its setup hotspot.
- In setup, click OK to switch between the hotspot-join QR and the webpage QR.
  Join the hotspot before opening `http://192.168.4.1/`. Other button gestures
  have no navigation action; complete configuration in the phone/browser.
- A successful connection saves the Wi-Fi settings and restarts after the
  eight-second status window. There is no function-button “exit setup” command.
- Without an interactive bridge, the basic pet supports OK-click interaction
  and DOWN-hold setup. Expired control data cannot select chats, send voice,
  or decide approvals; it does not turn an old OK action into pet interaction.

## Validation boundary

The hold-DOWN return implementation passed firmware compilation and host tests.
Its physical button response, screen hints, and remembered selection after
reopening still require testing on a device running that firmware.
