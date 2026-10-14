#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "bsp_button.h"
#include "pet_home.h"
#include "pet_control_layout.h"
typedef struct {
    uint8_t mode; // 0 offline; 1 Session; 2 new-chat ready; 3 approval; 4 error; 5 record; 6 transcribe; 7 projects; 8 notice
    uint8_t token[16];
    uint8_t pixels[PET_CONTROL_PIXELS];
    uint64_t received_ms;
    uint32_t opened; // Acknowledged local wake requests, independent of sync frames.
    pet_home_view_t home;
    bool has_home;
} pet_control_view_t;
bool pet_control_start(void);
void pet_control_snapshot(pet_control_view_t *view);
// The token is from the view actually presented by LVGL, never an unseen update.
bool pet_control_input(bsp_btn_t btn, bsp_btn_ev_t event, const pet_control_view_t *presented);
bool pet_control_open(const pet_control_view_t *presented);

// Bounded atomic edge tracking, safe in the shared timer callback.
void pet_control_key_edge(bsp_btn_t btn, bsp_btn_ev_t event);
