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
| Pet, interactive bridge connected | Open remembered session list or resume approval | Same as UP | Same as UP | No action | Restart into Wi-Fi setup | No action |
| Project list | Previous project | Next project | Enter selected project's sessions | Prepare a new chat in the selected project | Return to pet immediately | No action |
| New chat, before recording | No action | No action | No action | Cancel draft and return to projects | Return to pet; preserve draft | Record first voice message; release to transcribe |
| Session list | Previous saved chat | Next saved chat | Send current PC input | Return to project list | Return to pet immediately | Record voice for selected chat; release to transcribe |
| New-chat voice ready | No page change | No page change | Create the prepared chat and send its first message | Cancel draft and return to projects | Cancel draft and return to projects | Record additional voice; release to append in bridge memory |
| Approval | Next request page | Deny request and return to sessions | Allow after every page has been displayed | Deny request and return to sessions | Deny request and return to sessions | Record and fill PC input; restore the same approval on release |
| Error | Dismiss and restore preceding list, approval or prepared new-chat draft | Same as UP | Same as UP | Dismiss and restore preceding list, approval or prepared new-chat draft | Same as hold UP | No action |
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
  or approve a request. An unfinished approval or new-chat draft resumes instead.
- Project/session navigation wraps at the first and last entries. Approval
  pages also wrap.
- After **10 seconds without button activity**, interactive screens return to
  the pet even while Codex is working. Bridge heartbeats and status updates do
  not extend the timer. Recording/transcription remain visible until completion,
  then start a fresh 10-second window.
- Returning by inactivity does not submit the PC draft or decide an approval.
  Exiting the session list keeps the PC draft; deleting its text happens on the PC.
  Use the approval screen's controls to deny a request explicitly.
- After returning to the pet, release DOWN before holding it again for Wi-Fi
  setup. The return gesture itself does not enter setup.

## Voice, approval, and new-chat details

- Voice requires a live bridge and either a selected chat or prepared new-chat
  draft. Recording and transcription pin the target. Speak when `RECORDING`
  appears; release OK to transcribe. Recording is limited to 30 seconds.
- For existing chats, transcription fills the PC input and returns to the session
  list. No transcript text is displayed or saved on the card. Click OK to send
  the current PC text, including computer edits. This also works without voice.
  Empty or cleared input sends nothing; cached voice is never used as a fallback.
- Consecutive recordings accumulate in bridge memory until sending or leaving
  the selected chat. Filling replaces PC input with the accumulated voice and
  waits briefly for acknowledgement. Waiting, pet return and reconnection retain
  the bridge draft; restarting the bridge loses it. Failed transcription preserves
  earlier voice and PC text; unacknowledged filling requires checking the PC input. No transcript is written to the selection file.
- Click any function button to dismiss a speech/fill error. That click only
  dismisses the error; it cannot send or decide an approval. The preceding list,
  approval or new-chat draft remains available for another recording.
- Approval UP advances a page; DOWN denies immediately. OK confirms after all
  request pages have been displayed. Holding OK transcribes and fills PC input,
  then restores that request without sending or deciding it. Holding UP or DOWN
  denies the request.
- Holding UP on a saved project prepares a new-chat draft. Record the first
  message, then click OK on the generic ready notice to create and submit it.
  Its text stays only in bridge memory until confirmation; the card never shows
  the transcript. Another OK hold adds voice. Cancel/repeated events never create
  or resend automatically. Project navigation and pet wake retain their normal
  selection/open behavior.
- The first new-chat turn uses the local Codex CLI with existing authentication
  and configuration. After it exits, the bridge opens and selects that exact
  chat. Existing-chat sends use the desktop owner IPC. While the first CLI turn
  runs, do not take over that chat manually on the PC. A failed/uncertain send
  requires a PC check before retrying. The PC input may remain after IPC sending;
  clear it on the computer when appropriate.

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
