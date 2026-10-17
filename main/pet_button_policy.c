#include "pet_button_policy.h"
unsigned pet_control_pending_mode(unsigned mode, pet_action_t action) {
    if (action == PET_ACTION_DICTATE && (mode == 1 || mode == 3)) return PET_CONTROL_STARTING;
    if (action == PET_ACTION_OK && mode == 1) return PET_CONTROL_SENDING;
    return 0;
}
void pet_navigation_update(pet_navigation_t *nav, unsigned mode, bool fresh,
                           uint32_t opened, uint64_t now_ms) {
    if (!mode || (!fresh && !pet_control_busy(mode))) {
        nav->visible = nav->opening = false;
        return;
    }
    if (nav->opening && opened != nav->opened) nav->opening = false;
    if (pet_control_busy(mode)) {
        nav->visible = true;
        nav->last_input_ms = now_ms;
    } else if (nav->visible && now_ms >= nav->last_input_ms &&
               now_ms - nav->last_input_ms >= 10000) {
        nav->visible = nav->opening = false;
    }
}
void pet_navigation_open(pet_navigation_t *nav, uint32_t opened, uint64_t now_ms) {
    *nav = (pet_navigation_t){.visible = true, .opening = true,
        .last_input_ms = now_ms, .opened = opened};
}
void pet_navigation_activity(pet_navigation_t *nav, uint64_t now_ms) {
    if (nav->visible) nav->last_input_ms = now_ms;
}
bool pet_navigation_input(pet_navigation_t *nav, unsigned mode, bool fresh,
                          unsigned key, unsigned event) {
    if (!nav->visible || pet_button_action(mode, fresh, key, event) != PET_ACTION_HOME)
        return false;
    nav->visible = nav->opening = false;
    return true;
}
pet_action_t pet_button_action(unsigned mode, bool fresh, unsigned key, unsigned event) {
    if ((mode && !pet_control_busy(mode) && !pet_control_mode_valid(mode)) || key > 2 || event > 4) return PET_ACTION_NONE;
    if (pet_control_busy(mode)) return PET_ACTION_CONSUME;
    if (key == 1 && event == 3) {
        if (mode == 1 || mode == 7) return PET_ACTION_HOME;
        if (!mode) return PET_ACTION_SETUP;
    }
    if (!mode) return key == 2 && event == 1 ? PET_ACTION_PLAY : PET_ACTION_NONE;
    if (!fresh) return PET_ACTION_CONSUME;
    if (key == 0 && event == 3) return mode == 7 ? PET_ACTION_NEW : PET_ACTION_BACK;
    if (key == 2 && event == 3) return (mode == 1 || mode == 3) ? PET_ACTION_DICTATE : PET_ACTION_CONSUME;
    if (key == 1 && event == 3) return PET_ACTION_CANCEL;
    if (event != 1) return PET_ACTION_NONE;
    // Recover from native control errors with a click; consume it as dismissal only.
    if (mode == 4) return PET_ACTION_CANCEL;
    return key == 0 ? PET_ACTION_UP : key == 1 ? PET_ACTION_DOWN : PET_ACTION_OK;
}
