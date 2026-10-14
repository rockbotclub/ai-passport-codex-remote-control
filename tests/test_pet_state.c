#include "pet_state.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static bool line(pet_parser_t *parser, pet_state_t *state, const char *text, uint64_t now) {
    bool accepted = false;
    for (; *text; ++text) accepted = pet_feed(parser, state, *text, now);
    return accepted;
}
int main(void) {
    pet_parser_t parser = {0}; pet_state_t state = {0};
    assert(pet_visible_status(&state, 0) == PET_OFFLINE);
    assert(!line(&parser, &state, "CP1 work", 1));
    assert(line(&parser, &state, "ing 2 0\n", 10));
    assert(state.active == 2 && pet_visible_status(&state, 5009) == PET_WORKING);
    assert(pet_visible_status(&state, 5010) == PET_OFFLINE);
    assert(line(&parser, &state, "CP1 waiting 3 2\r\n", 20));
    assert(state.waiting == 2);
    const char *invalid[] = {"CP1 working 0 0\n", "CP1 waiting 1 2\n", "CP1 idle 1 0\n", "CP1 done 0 1\n", "CP1 wait 2 1\n", "CP1 working -1 0\n", "CP1 working 1000 0\n", "CP1 working 1 0extra\n", "CP1 working 1 0 \n", "noise\n"};
    for (unsigned i=0; i<sizeof(invalid)/sizeof(invalid[0]); ++i) {
        assert(!line(&parser, &state, invalid[i], 100));
        assert(state.received_ms == 20);
    }
    for (unsigned i=0; i<100; ++i) pet_feed(&parser, &state, 'x', 100);
    assert(!pet_feed(&parser, &state, '\n', 100));
    assert(line(&parser, &state, "CP1 done 0 0\n", 101));
    assert(pet_visible_status(&state, 100) == PET_OFFLINE);
    assert(pet_visible_status(&state, 102) == PET_DONE);
    pet_feed(&parser, &state, '\0', 103);
    assert(!line(&parser, &state, "CP1 idle 0 0\n", 103));
    assert(line(&parser, &state, "CP1 offline 0 0\n", 104));
    assert(pet_visible_status(&state, 104) == PET_OFFLINE);
    assert(line(&parser, &state, "CP1 idle 0 0\n", 200));
    assert(pet_visible_status(&state, 5199) == PET_IDLE);
    assert(pet_visible_status(&state, 5200) == PET_OFFLINE);
    assert(pet_fallback_status(PET_IDLE, false, false) == PET_IDLE); // USB only.
    assert(pet_fallback_status(PET_WORKING, true, false) == PET_OFFLINE); // UDP still alive.
    assert(pet_fallback_status(PET_IDLE, true, false) == PET_OFFLINE);
    assert(pet_fallback_status(PET_IDLE, true, true) == PET_IDLE); // Reconnected.
    pet_animation_t idle = pet_animation(PET_IDLE), offline = pet_animation(PET_OFFLINE);
    assert(idle.row != offline.row && idle.count > 1 && offline.count == 1);
    assert(offline.row == 5 && offline.first == 3);
    assert(idle.period_ms == 700);
    const unsigned counts[] = {[0] = 6, [4] = 5, [5] = 8, [6] = 6, [7] = 6};
    for (pet_status_t status = PET_OFFLINE; status <= PET_ERROR; ++status) {
        pet_animation_t animation = pet_animation(status);
        assert(animation.count && animation.period_ms);
        assert(animation.row < sizeof(counts) / sizeof(counts[0]));
        assert(animation.first + animation.count <= counts[animation.row]);
    }
    puts("Codex pet protocol and heartbeat tests: PASS");
}
