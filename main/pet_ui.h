#pragma once
#include "pet_state.h"
// Caller holds the BSP LVGL lock. UI and timer live for the application lifetime.
bool pet_ui_create(void);
void pet_ui_update(pet_status_t status, unsigned active, unsigned waiting, int battery);
void pet_ui_play(void);
void pet_ui_network(const char *link, const char *help);
void pet_ui_setup(const char *wifi_qr, const char *ap_help);
void pet_ui_setup_next(void);

#include "pet_control.h"
void pet_ui_control(const pet_control_view_t *view, bool visible);
