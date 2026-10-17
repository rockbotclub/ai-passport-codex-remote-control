#pragma once
#include <stdbool.h>
#include <stdint.h>
enum { PET_CONTROL_STARTING = 11, PET_CONTROL_SENDING = 12,
       PET_CONTROL_ACTION_TIMEOUT_MS = 24000 };
// Only these modes can arrive in an authenticated desktop control frame.
static inline bool pet_control_mode_valid(unsigned mode) {
    return mode == 1 || mode == 3 || mode == 4 || mode == 7 || mode == 10;
}
// Modes 6/11/12 are local pending actions; mode 10 waits for key release.
static inline bool pet_control_busy(unsigned mode) {
    return mode == 6 || mode == 10 || mode == PET_CONTROL_STARTING || mode == PET_CONTROL_SENDING;
}
static inline bool pet_control_online(unsigned mode, uint64_t received_ms, uint64_t now_ms) {
    if (!mode || now_ms < received_ms) return false;
    uint64_t age = now_ms - received_ms;
    if (mode == PET_CONTROL_STARTING || mode == PET_CONTROL_SENDING)
        return age < PET_CONTROL_ACTION_TIMEOUT_MS;
    return age < 3000 || pet_control_busy(mode);
}
// Portable policy. Key/event values match the BSP, asserted by its adapter.
typedef enum { PET_ACTION_NONE, PET_ACTION_CONSUME, PET_ACTION_UP, PET_ACTION_DOWN,
    PET_ACTION_OK, PET_ACTION_DICTATE, PET_ACTION_CANCEL, PET_ACTION_SETUP, PET_ACTION_PLAY,
    PET_ACTION_BACK, PET_ACTION_NEW, PET_ACTION_HOME } pet_action_t;
pet_action_t pet_button_action(unsigned mode, bool fresh, unsigned key, unsigned event);
// Only sending from the chat list and starting dictation need these local views.
unsigned pet_control_pending_mode(unsigned mode, pet_action_t action);

// Local screen lifetime is independent of bridge heartbeats and work status.
typedef struct {
    bool visible, opening;
    uint64_t last_input_ms;
    uint32_t opened;
} pet_navigation_t;
void pet_navigation_update(pet_navigation_t *nav, unsigned mode, bool fresh,
                           uint32_t opened, uint64_t now_ms);
void pet_navigation_open(pet_navigation_t *nav, uint32_t opened, uint64_t now_ms);
void pet_navigation_activity(pet_navigation_t *nav, uint64_t now_ms);
// Local return consumes the gesture without changing the bridge selection.
bool pet_navigation_input(pet_navigation_t *nav, unsigned mode, bool fresh,
                          unsigned key, unsigned event);
