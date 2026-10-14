#pragma once
#include "pet_state.h"
// Structural validation only. The caller must authenticate payload/signature
// before applying next_state or advancing the replay counter.
typedef struct {
    const char *signature, *payload;
    size_t payload_length;
    uint64_t sequence;
    pet_state_t next_state;
} pet_packet_t;
bool pet_packet_decode(const char *packet, size_t length, uint64_t last_sequence,
                       uint64_t now_ms, pet_packet_t *result);
