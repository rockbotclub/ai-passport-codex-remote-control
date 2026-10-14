#pragma once
#include <stdbool.h>
#include <stdint.h>
// Portable policy. Key/event values match the BSP, asserted by its adapter.
typedef enum { PET_ACTION_NONE, PET_ACTION_CONSUME, PET_ACTION_UP, PET_ACTION_DOWN,
    PET_ACTION_OK, PET_ACTION_RECORD, PET_ACTION_CANCEL, PET_ACTION_SETUP, PET_ACTION_PLAY,
    PET_ACTION_BACK, PET_ACTION_NEW, PET_ACTION_HOME } pet_action_t;
pet_action_t pet_button_action(unsigned mode, bool fresh, unsigned key, unsigned event);

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
