#pragma once
#include <stdbool.h>
#include <stdint.h>

#define PET_CONTROL_WIDTH 216
#define PET_CONTROL_HEIGHT 224
#define PET_CONTROL_PIXELS (PET_CONTROL_WIDTH * PET_CONTROL_HEIGHT / 8)
#define PET_CONTROL_FOOTER_TOP 278

static inline bool pet_control_list_mode(uint8_t mode) {
    return mode == 1 || mode == 7;
}

// Review pages retain their original crop and position below the header.
static inline unsigned pet_control_panel_height(uint8_t mode) {
    return pet_control_list_mode(mode) ? PET_CONTROL_HEIGHT : 192;
}

static inline unsigned pet_control_panel_top(uint8_t mode) {
    return pet_control_list_mode(mode) ? 45 : 85;
}
