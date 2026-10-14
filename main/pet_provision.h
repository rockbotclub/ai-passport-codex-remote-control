#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PET_SETUP_URL "http://192.168.4.1/"
#define PET_SETUP_CAPTIVE_URL "http://192.168.4.1/captive"
#define PET_SETUP_QR_CAPACITY 224

typedef enum { PET_SETUP_IDLE, PET_SETUP_CONNECTING, PET_SETUP_FAILED, PET_SETUP_SAVED } pet_setup_phase_t;
typedef enum { PET_SETUP_WAIT, PET_SETUP_SAVE, PET_SETUP_RETRY } pet_setup_decision_t;
// Connection policy is independent of platform events and NVS. A request is
// queued before the worker starts the bounded attempt (e.g. while scanning).
bool pet_provision_can_request(pet_setup_phase_t phase);
pet_setup_decision_t pet_provision_decide(uint64_t now_ms, uint64_t deadline_ms,
                                         bool connected, bool disconnected);

// Standard Wi-Fi QR payload; rejects invalid lengths/control bytes and truncation.
bool pet_provision_qr(char *out, size_t capacity, const char *ssid, const char *password);
// Bounded single-question DNS responder. A -> AP IPv4; other types -> no answers.
// Input and output must not overlap. Invalid packets produce no response.
size_t pet_provision_dns(const uint8_t *query, size_t length, uint8_t *out,
                         size_t capacity, const uint8_t ip[4]);
