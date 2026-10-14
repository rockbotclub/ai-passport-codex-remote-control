#include "pet_button_policy.h"
void pet_navigation_update(pet_navigation_t *nav, unsigned mode, bool fresh,
                           uint32_t opened, uint64_t now_ms) {
    if (!mode || (!fresh && mode != 5 && mode != 6)) {
        nav->visible = nav->opening = false;
        return;
    }
    if (nav->opening && opened != nav->opened) nav->opening = false;
    if (mode == 5 || mode == 6) {
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
    if (mode > 8 || key > 2 || event > 4) return PET_ACTION_NONE;
    if (mode == 5 || mode == 6) return PET_ACTION_CONSUME;
    if (key == 1 && event == 3) {
        if (mode == 1 || mode == 7) return PET_ACTION_HOME;
        if (!mode) return PET_ACTION_SETUP;
    }
    if (!mode) return key == 2 && event == 1 ? PET_ACTION_PLAY : PET_ACTION_NONE;
    if (!fresh) return PET_ACTION_CONSUME;
    if (key == 0 && event == 3) return mode == 7 ? PET_ACTION_NEW : PET_ACTION_BACK;
    if (key == 2 && event == 3) return mode <= 2 ? PET_ACTION_RECORD : PET_ACTION_CONSUME;
    if (key == 1 && event == 3) return PET_ACTION_CANCEL;
    if (event != 1) return PET_ACTION_NONE;
    // Recover from speech errors with a click; consume it as dismissal only.
    if (mode == 4) return PET_ACTION_CANCEL;
    if (mode == 8) return PET_ACTION_CONSUME;
    return key == 0 ? PET_ACTION_UP : key == 1 ? PET_ACTION_DOWN : PET_ACTION_OK;
}
