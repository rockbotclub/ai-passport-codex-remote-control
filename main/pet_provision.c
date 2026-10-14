#include "pet_provision.h"
#include <string.h>

bool pet_provision_can_request(pet_setup_phase_t phase) {
    return phase == PET_SETUP_IDLE || phase == PET_SETUP_FAILED;
}

pet_setup_decision_t pet_provision_decide(uint64_t now_ms, uint64_t deadline_ms,
                                         bool connected, bool disconnected) {
    if (!deadline_ms) return PET_SETUP_WAIT;
    if (connected) return PET_SETUP_SAVE;
    return disconnected || now_ms >= deadline_ms ? PET_SETUP_RETRY : PET_SETUP_WAIT;
}

static bool append(char *out, size_t capacity, size_t *used, const char *text, bool escape) {
    for (; *text; ++text) {
        unsigned char c = (unsigned char)*text;
        if (c < 32 || c == 127) return false;
        if (escape && strchr("\\;,:\"", c)) {
            if (*used + 1 >= capacity) return false;
            out[(*used)++] = '\\';
        }
        if (*used + 1 >= capacity) return false;
        out[(*used)++] = *text;
    }
    out[*used] = 0;
    return true;
}

bool pet_provision_qr(char *out, size_t capacity, const char *ssid, const char *password) {
    if (!out || !capacity) return false;
    out[0] = 0;
    if (!ssid || !password || !*ssid || strlen(ssid) > 32 ||
        strlen(password) < 8 || strlen(password) > 63) return false;
    size_t used = 0;
    bool ok = append(out, capacity, &used, "WIFI:T:WPA;S:", false) &&
              append(out, capacity, &used, ssid, true) &&
              append(out, capacity, &used, ";P:", false) &&
              append(out, capacity, &used, password, true) &&
              append(out, capacity, &used, ";;", false);
    if (!ok) out[0] = 0;
    return ok;
}

size_t pet_provision_dns(const uint8_t *query, size_t length, uint8_t *out,
                         size_t capacity, const uint8_t ip[4]) {
    if (!query || !out || !ip || length < 17 || length > 512 ||
        (query[2] & 0xfe) || query[3] || query[4] || query[5] != 1 ||
        query[6] || query[7] || query[8] || query[9]) return 0;
    size_t end = 12;
    while (end < length && query[end]) {
        size_t label = query[end++];
        if (label > 63 || label > length - end) return 0; // No compression pointers in queries.
        end += label;
    }
    if (end >= length || end - 12 > 254 || length - end < 5) return 0;
    ++end;
    bool answer = query[end] == 0 && query[end+1] == 1 && query[end+2] == 0 && query[end+3] == 1;
    end += 4;
    size_t size = end + (answer ? 16 : 0);
    if (size > capacity) return 0;
    memcpy(out, query, end);
    out[2] = 0x84 | (query[2] & 1); // Response, authoritative, echo recursion-desired.
    out[3] = 0;
    out[6] = 0; out[7] = answer ? 1 : 0;
    out[8] = out[9] = out[10] = out[11] = 0;
    if (answer) {
        const uint8_t record[12] = {0xc0,0x0c,0,1,0,1,0,0,0,0,0,4};
        memcpy(out + end, record, sizeof(record));
        memcpy(out + end + sizeof(record), ip, 4);
    }
    return size;
}
