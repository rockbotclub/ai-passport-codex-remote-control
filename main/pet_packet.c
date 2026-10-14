#include "pet_packet.h"
#include <string.h>

bool pet_packet_decode(const char *packet, size_t length, uint64_t last_sequence,
                       uint64_t now_ms, pet_packet_t *result) {
    if (length < 80 || length >= 192 || memcmp(packet, "CPW1 ", 5) || packet[69] != ' ') return false;
    for (size_t i=5; i<69; ++i)
        if (!((packet[i]>='0' && packet[i]<='9') || (packet[i]>='a' && packet[i]<='f'))) return false;
    size_t index = 70, start = index;
    uint64_t sequence = 0;
    while (index < length && packet[index] >= '0' && packet[index] <= '9') {
        unsigned digit = (unsigned)(packet[index++] - '0');
        if (sequence > (UINT64_MAX-digit)/10 || index-start > 20) return false;
        sequence = sequence*10 + digit;
    }
    if (index == start || index >= length || packet[index++] != ' ' || sequence <= last_sequence) return false;
    pet_parser_t parser = {0}; pet_state_t state = {0}; bool accepted = false;
    for (; index < length; ++index) {
        if (packet[index] == '\n' && index+1 != length) return false;
        accepted = pet_feed(&parser, &state, packet[index], now_ms);
    }
    if (!accepted) return false;
    *result = (pet_packet_t){.signature=packet+5, .payload=packet+70,
        .payload_length=length-70, .sequence=sequence, .next_state=state};
    return true;
}
