#include "pet_home.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    uint8_t frame[PET_HOME_FRAME_BYTES] = {9, PET_WAITING, 0, 5, 0, 1, 3, 1};
    pet_home_view_t view = {0};
    frame[8] = 0xa5; frame[PET_HOME_FRAME_BYTES - 1] = 0x5a;
    assert(pet_home_decode(frame, sizeof(frame), &view));
    assert(view.active == 5 && view.waiting == 1 && view.rows == 3 && view.waiting_mask == 1);
    assert(view.pixels[0] == 0xa5 && view.pixels[PET_HOME_PIXELS - 1] == 0x5a);
    pet_home_view_t original = view;
    assert(!pet_home_decode(frame, sizeof(frame) - 1, &view));
    assert(!memcmp(&original, &view, sizeof(view)));
    frame[7] = 2; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[7] = 1; frame[6] = 4; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[6] = 3; frame[5] = 6; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[5] = 0; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[1] = PET_WORKING; frame[7] = 0; assert(pet_home_decode(frame, sizeof(frame), &view));
    frame[1] = PET_IDLE; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[3] = 0; frame[6] = 0; assert(pet_home_decode(frame, sizeof(frame), &view));
    frame[1] = PET_OFFLINE; assert(pet_home_decode(frame, sizeof(frame), &view));
    frame[1] = PET_SYNCING; assert(pet_home_decode(frame, sizeof(frame), &view));
    assert(view.status == PET_SYNCING && view.active == 0);
    frame[3] = 1; frame[6] = 1; assert(!pet_home_decode(frame, sizeof(frame), &view));
    frame[3] = 0; frame[6] = 0;
    frame[1] = PET_SYNCING + 1; assert(!pet_home_decode(frame, sizeof(frame), &view));
    puts("Pet overview packet tests: PASS");
    return 0;
}
