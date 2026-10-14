#pragma once
#include "esp_err.h"
#include "pet_state.h"
#include "pet_provision.h"
// Network setup and UDP run outside the LVGL lock, in the application worker.
esp_err_t pet_network_init(void);
void pet_network_poll(pet_state_t *state, uint64_t now_ms);
void pet_network_info(char *link, size_t link_size, char *help, size_t help_size);
// Setup mode lasts until reboot; QR contains only the temporary AP credentials.
bool pet_network_is_setup(void);
bool pet_network_setup_qr(char out[PET_SETUP_QR_CAPACITY]);
// Reboot into password-protected setup AP, retaining saved credentials until replaced.
void pet_network_setup(void);

// Authenticated status sender identifies the paired desktop; no arbitrary discovery.
bool pet_network_peer(uint32_t *address, char key[33]);
