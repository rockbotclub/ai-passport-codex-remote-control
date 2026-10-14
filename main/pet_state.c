#include "pet_state.h"
#include <string.h>

static bool number(const char **cursor, unsigned *value, char separator) {
    const char *p = *cursor;
    unsigned n = 0;
    if (*p < '0' || *p > '9') return false;
    do {
        n = n * 10 + (unsigned)(*p++ - '0');
        if (n > 999) return false;
    } while (*p >= '0' && *p <= '9');
    if (*p != separator) return false;
    *cursor = p + (separator != '\0');
    *value = n;
    return true;
}

static bool parse(const char *line, pet_state_t *state, uint64_t now_ms) {
    static const char *names[] = {"offline", "idle", "working", "waiting", "done", "error"};
    if (strncmp(line, "CP1 ", 4)) return false;
    const char *p = line + 4;
    size_t status;
    for (status = 0; status < sizeof(names) / sizeof(names[0]); ++status) {
        size_t n = strlen(names[status]);
        if (!strncmp(p, names[status], n) && p[n] == ' ') { p += n + 1; break; }
    }
    if (status == sizeof(names) / sizeof(names[0])) return false;
    unsigned active, waiting;
    if (!number(&p, &active, ' ') || !number(&p, &waiting, '\0') || waiting > active) return false;
    if ((status == PET_WORKING && (!active || waiting)) ||
        (status == PET_WAITING && !waiting) ||
        ((status == PET_IDLE || status == PET_DONE || status == PET_OFFLINE) && active)) return false;
    *state = (pet_state_t){ .status = (pet_status_t)status, .active = active,
        .waiting = waiting, .received_ms = now_ms, .connected = true };
    return true;
}

bool pet_feed(pet_parser_t *parser, pet_state_t *state, char byte, uint64_t now_ms) {
    if (byte == '\n') {
        if (parser->length && parser->line[parser->length - 1] == '\r') --parser->length;
        parser->line[parser->length] = '\0';
        bool accepted = !parser->overflow && parse(parser->line, state, now_ms);
        *parser = (pet_parser_t){0};
        return accepted;
    }
    if (byte == '\0' || ((unsigned char)byte < 32 && byte != '\r')) parser->overflow = true;
    if (parser->length + 1 < sizeof(parser->line)) parser->line[parser->length++] = byte;
    else parser->overflow = true;
    return false;
}

pet_status_t pet_visible_status(const pet_state_t *state, uint64_t now_ms) {
    if (!state->connected || now_ms < state->received_ms || now_ms - state->received_ms >= 5000) return PET_OFFLINE;
    return state->status;
}

pet_status_t pet_fallback_status(pet_status_t heartbeat, bool control_seen, bool control_online) {
    return control_seen && !control_online ? PET_OFFLINE : heartbeat;
}

pet_animation_t pet_animation(pet_status_t status) {
    switch (status) {
        case PET_OFFLINE: return (pet_animation_t){5, 3, 1, 700}; // Still, downcast face.
        case PET_WORKING: return (pet_animation_t){7, 0, 6, 150};
        case PET_WAITING: return (pet_animation_t){6, 0, 6, 150};
        case PET_DONE: return (pet_animation_t){4, 0, 5, 150};
        case PET_ERROR: return (pet_animation_t){5, 0, 8, 150};
        default: return (pet_animation_t){0, 0, 6, 700}; // Relaxed blinking.
    }
}
