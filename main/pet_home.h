#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "pet_state.h"

#define PET_HOME_SUMMARY_BYTES (104 * 84 / 8)
#define PET_HOME_LIST_BYTES (216 * 144 / 8)
#define PET_HOME_FOOTER_BYTES (216 * 24 / 8)
#define PET_HOME_PIXELS (PET_HOME_SUMMARY_BYTES + PET_HOME_LIST_BYTES + PET_HOME_FOOTER_BYTES)
#define PET_HOME_FRAME_BYTES (8 + PET_HOME_PIXELS)
typedef struct {
    pet_status_t status;
    unsigned active, waiting;
    uint8_t rows, waiting_mask;
    uint8_t pixels[PET_HOME_PIXELS];
} pet_home_view_t;

// Validate the entire read-only overview before publishing any of it.
bool pet_home_decode(const uint8_t *frame, size_t length, pet_home_view_t *out);
