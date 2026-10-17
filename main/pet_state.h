#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { PET_OFFLINE, PET_IDLE, PET_WORKING, PET_WAITING, PET_DONE, PET_ERROR, PET_SYNCING } pet_status_t;
typedef struct {
    pet_status_t status;
    unsigned active, waiting;
    uint64_t received_ms;
    bool connected;
} pet_state_t;
typedef struct { char line[64]; size_t length; bool overflow; } pet_parser_t;
// Only complete, strictly validated CP1 lines refresh the connection deadline.
bool pet_feed(pet_parser_t *parser, pet_state_t *state, char byte, uint64_t now_ms);
pet_status_t pet_visible_status(const pet_state_t *state, uint64_t now_ms);
// Once interactive control has connected, its loss overrides UDP heartbeats.
pet_status_t pet_fallback_status(pet_status_t heartbeat, bool control_seen, bool control_online);
typedef struct { unsigned row, first, count, period_ms; } pet_animation_t;
pet_animation_t pet_animation(pet_status_t status);
