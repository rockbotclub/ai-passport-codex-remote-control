#include "pet_home.h"
#include <string.h>

bool pet_home_decode(const uint8_t *frame, size_t length, pet_home_view_t *out) {
    if (!frame || !out || length != PET_HOME_FRAME_BYTES || frame[0] != 9 || frame[1] > PET_SYNCING)
        return false;
    unsigned active = (unsigned)frame[2] * 256 + frame[3];
    unsigned waiting = (unsigned)frame[4] * 256 + frame[5];
    unsigned rows = frame[6], mask = frame[7];
    if (active > 999 || waiting > active || rows > 3 || rows != (active < 3 ? active : 3) ||
        mask >= (1u << rows) ||
        (frame[1] == PET_WORKING && (!active || waiting)) ||
        (frame[1] == PET_WAITING && !waiting) ||
        ((frame[1] == PET_IDLE || frame[1] == PET_DONE || frame[1] == PET_OFFLINE || frame[1] == PET_SYNCING) && active))
        return false;
    unsigned highlighted = 0;
    for (unsigned i = 0; i < rows; ++i) highlighted += (mask >> i) & 1u;
    unsigned visible_waiting = waiting < 3 ? waiting : 3;
    if (highlighted != visible_waiting || mask != (1u << visible_waiting) - 1) return false;
    out->status = (pet_status_t)frame[1];
    out->active = active; out->waiting = waiting;
    out->rows = (uint8_t)rows; out->waiting_mask = (uint8_t)mask;
    memcpy(out->pixels, frame + 8, PET_HOME_PIXELS);
    return true;
}
