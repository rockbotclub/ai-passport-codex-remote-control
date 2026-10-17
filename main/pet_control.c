#include "pet_control.h"
#include "pet_network.h"
#include "pet_button_policy.h"
_Static_assert(BSP_BTN_UP == 0 && BSP_BTN_DOWN == 1 && BSP_BTN_OK == 2, "按键映射已变化");
_Static_assert(BSP_BTN_CLICK == 1 && BSP_BTN_LONG == 3 && BSP_BTN_RELEASE == 4, "按键事件映射已变化");
#include "esp_random.h"
#include "esp_timer.h"
#include "mbedtls/gcm.h"
#include "mbedtls/md.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>

#define CONTROL_PORT 19285
#define MAX_FRAME 6144
_Static_assert(17 + PET_CONTROL_PIXELS + 16 <= MAX_FRAME, "控制位图超出加密数据包大小限制");
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static pet_control_view_t s_view;
typedef struct { const char *command; uint8_t token[16], pending_mode; } action_t;
static QueueHandle_t s_actions;
static atomic_bool s_held, s_dictating, s_physical_ok;
static bool s_swallow_click;
static unsigned char s_cipher[MAX_FRAME], s_plain[MAX_FRAME], s_tx[256];
static unsigned char s_control_plain[17 + PET_CONTROL_PIXELS];
static mbedtls_gcm_context s_encrypt, s_decrypt;
static uint64_t s_sent, s_received;

static uint64_t now_ms(void) { return (uint64_t)esp_timer_get_time() / 1000; }
static void mode_set(uint8_t mode) {
    portENTER_CRITICAL(&s_lock);
    s_view.mode = mode;
    if (!mode) s_view.has_home = false;
    s_view.received_ms = now_ms();
    portEXIT_CRITICAL(&s_lock);
}
void pet_control_key_edge(bsp_btn_t btn, bsp_btn_ev_t event) {
    if (btn != BSP_BTN_OK) return;
    if (event == BSP_BTN_PRESS) s_physical_ok = true;
    if (event == BSP_BTN_RELEASE) { s_physical_ok = false; s_held = false; }
}
void pet_control_snapshot(pet_control_view_t *view) {
    portENTER_CRITICAL(&s_lock);
    *view = s_view;
    portEXIT_CRITICAL(&s_lock);
}

static bool transfer(int fd, void *buffer, size_t size, bool write_data) {
    unsigned char *p = buffer;
    while (size) {
        int n = write_data ? send(fd, p, size, 0) : recv(fd, p, size, 0);
        if (n <= 0) return false;
        p += n;
        size -= n;
    }
    return true;
}
static bool mac(const char key[33], const unsigned char *data, size_t n, unsigned char output[32]) {
    const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    return md && mbedtls_md_hmac(md, (const unsigned char *)key, 32, data, n, output) == 0;
}
static void nonce(uint64_t counter, unsigned char iv[12]) {
    memset(iv, 0, 12);
    for (unsigned i = 0; i < 8; ++i) iv[11-i] = (unsigned char)(counter >> (i*8));
}
static bool handshake(int fd, const char key[33]) {
    unsigned char hello[20], response[48], data[39], digest[32];
    memcpy(hello, "CPG1", 4);
    // Wi-Fi RF is running: hardware RNG supplies entropy without touching button ADC.
    esp_fill_random(hello+4, 16);
    if (!transfer(fd, hello, sizeof(hello), true) || !transfer(fd, response, sizeof(response), false)) return false;
    memcpy(data, "server", 6); memcpy(data+6, hello+4, 16); memcpy(data+22, response, 16);
    if (!mac(key, data, 38, digest)) return false;
    unsigned difference = 0;
    for (unsigned i = 0; i < 32; ++i) difference |= digest[i] ^ response[16+i];
    if (difference) return false;
    memcpy(data, "client", 6);
    if (!mac(key, data, 38, digest) || !transfer(fd, digest, 32, true)) return false;
    // ESP-IDF's AES-GCM port caches GHASH per context. A new connection
    // derives new keys, so discard the previous connection's cached tables.
    mbedtls_gcm_free(&s_encrypt); mbedtls_gcm_init(&s_encrypt);
    mbedtls_gcm_free(&s_decrypt); mbedtls_gcm_init(&s_decrypt);
    memcpy(data, "CPG1", 4); memcpy(data+4, hello+4, 16); memcpy(data+20, response, 16);
    data[36] = 'C';
    if (!mac(key, data, 37, digest) || mbedtls_gcm_setkey(&s_encrypt, MBEDTLS_CIPHER_ID_AES, digest, 256)) return false;
    data[36] = 'S';
    if (!mac(key, data, 37, digest) || mbedtls_gcm_setkey(&s_decrypt, MBEDTLS_CIPHER_ID_AES, digest, 256)) return false;
    memset(digest, 0, sizeof(digest));
    s_sent = s_received = 0;
    return true;
}
static bool secure_send(int fd, const unsigned char *plain, size_t length) {
    if (!length || length+16 > MAX_FRAME || s_sent == UINT64_MAX) return false;
    unsigned char iv[12], header[2]; nonce(++s_sent, iv);
    if (mbedtls_gcm_crypt_and_tag(&s_encrypt, MBEDTLS_GCM_ENCRYPT, length, iv, 12,
                                (const unsigned char *)"CPG1", 4, plain, s_cipher, 16, s_cipher+length)) return false;
    header[0] = (unsigned char)((length+16) >> 8); header[1] = (unsigned char)(length+16);
    return transfer(fd, header, 2, true) && transfer(fd, s_cipher, length+16, true);
}
static bool secure_receive(int fd, size_t expected) {
    unsigned char header[2], iv[12];
    if (!transfer(fd, header, 2, false)) return false;
    size_t length = (size_t)header[0]*256 + header[1];
    if (length != expected+16 || length > MAX_FRAME || s_received == UINT64_MAX) return false;
    if (!transfer(fd, s_cipher, length, false)) return false;
    nonce(++s_received, iv);
    if (mbedtls_gcm_auth_decrypt(&s_decrypt, length-16, iv, 12, (const unsigned char *)"CPG1", 4,
                               s_cipher+length-16, 16, s_cipher, s_plain)) return false;
    return true;
}
static bool receive_view(int fd) {
    if (!secure_receive(fd, sizeof(s_control_plain)) || !pet_control_mode_valid(s_plain[0]))
        return false;
    memcpy(s_control_plain, s_plain, sizeof(s_control_plain));
    if (!secure_receive(fd, PET_HOME_FRAME_BYTES)) return false;
    portENTER_CRITICAL(&s_lock);
    bool valid = pet_home_decode(s_plain, PET_HOME_FRAME_BYTES, &s_view.home);
    if (valid) {
        s_view.mode = s_control_plain[0];
        memcpy(s_view.token, s_control_plain+1, 16);
        memcpy(s_view.pixels, s_control_plain+17, PET_CONTROL_PIXELS);
        s_view.has_home = true;
        s_view.received_ms = now_ms();
    }
    portEXIT_CRITICAL(&s_lock);
    return valid;
}
static bool command(int fd, const char *name, const uint8_t token[16]) {
    char hex[33];
    for (unsigned i = 0; i < 16; ++i) snprintf(hex+i*2, 3, "%02x", token[i]);
    s_tx[0] = 1;
    int n = snprintf((char *)s_tx+1, sizeof(s_tx)-1, "{\"cmd\":\"%s\",\"token\":\"%s\",\"home\":true,\"pc_dictation\":true}", name, hex);
    return n > 0 && (size_t)n < sizeof(s_tx)-1 && secure_send(fd, s_tx, (size_t)n+1) && receive_view(fd);
}
static bool wait_dictation_release(int fd) {
    uint8_t token[16];
    portENTER_CRITICAL(&s_lock);
    uint8_t mode = s_view.mode;
    memcpy(token, s_view.token, sizeof(token));
    portEXIT_CRITICAL(&s_lock);
    if (mode != 10) return true;
    s_dictating = true;
    uint64_t end = now_ms() + 30000;
    while (s_held && now_ms() < end) vTaskDelay(pdMS_TO_TICKS(20));
    s_held = false;
    s_dictating = false;
    mode_set(6);
    return command(fd, "stop", token);
}
static void worker(void *unused) {
    (void)unused;
    mbedtls_gcm_init(&s_encrypt); mbedtls_gcm_init(&s_decrypt);
    for (;;) {
        uint32_t peer; char key[33];
        if (!pet_network_peer(&peer, key)) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        struct timeval timeout = {.tv_sec = 4};
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons(CONTROL_PORT), .sin_addr.s_addr = peer};
        bool connected = connect(fd, (struct sockaddr *)&address, sizeof(address)) == 0 && handshake(fd, key);
        memset(key, 0, sizeof(key));
        xQueueReset(s_actions);
        s_held = false;
        uint64_t next_sync = 0;
        while (connected) {
            action_t action;
            if (xQueueReceive(s_actions, &action, pdMS_TO_TICKS(30)) == pdTRUE) {
                // Only this connection may own a dictation. Release is atomic, so
                // queue saturation cannot leave PC dictation running indefinitely.
                if (!strcmp(action.command, "record") && !s_held) continue;
                // Explicit UI actions may navigate or wait for desktop dictation.
                // Normal one-second syncs keep their short disconnect timeout.
                timeout.tv_sec = !strcmp(action.command, "ok") || !strcmp(action.command, "new") ||
                                 !strcmp(action.command, "record") ? PET_CONTROL_ACTION_TIMEOUT_MS / 1000 : 4;
                setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
                // Keep the pending state visible while the native UI action runs.
                // The authenticated reply, or transport failure, replaces it.
                if (action.pending_mode) mode_set(action.pending_mode);
                connected = command(fd, action.command, action.token);
                if (connected && !strcmp(action.command, "sessions")) {
                    portENTER_CRITICAL(&s_lock);
                    ++s_view.opened;
                    portEXIT_CRITICAL(&s_lock);
                }
                if (connected && !strcmp(action.command, "record")) {
                    // Native Stop/Cancel action (8 s) plus a bounded transport margin.
                    timeout.tv_sec = 16;
                    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
                    connected = wait_dictation_release(fd);
                }
                timeout.tv_sec = 4;
                setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
                next_sync = now_ms() + 800;
            } else if (now_ms() >= next_sync) {
                uint8_t empty[16] = {0};
                connected = command(fd, "sync", empty);
                next_sync = now_ms() + 800;
            }
        }
        s_held = false; s_dictating = false;
        close(fd); mode_set(0);
        vTaskDelay(pdMS_TO_TICKS(1500));
    }
}
bool pet_control_start(void) {
    s_actions = xQueueCreate(8, sizeof(action_t));
    if (!s_actions) return false;
    if (xTaskCreate(worker, "pet_control", 8192, NULL, 5, NULL) != pdPASS) {
        vQueueDelete(s_actions); s_actions = NULL; return false;
    }
    return true;
}
bool pet_control_open(const pet_control_view_t *view) {
    if (!s_actions) return false;
    action_t action = {.command = "sessions"};
    memcpy(action.token, view->token, sizeof(action.token));
    return xQueueSend(s_actions, &action, 0) == pdTRUE;
}
bool pet_control_input(bsp_btn_t btn, bsp_btn_ev_t event, const pet_control_view_t *view) {
    if (btn == BSP_BTN_OK && event == BSP_BTN_RELEASE) { s_held = false; return true; }
    if (btn == BSP_BTN_OK && event == BSP_BTN_PRESS) { s_swallow_click = false; return true; }
    if (btn == BSP_BTN_OK && event == BSP_BTN_CLICK && s_swallow_click) return true;
    if (!s_actions) return false;
    pet_action_t choice = pet_button_action(view->mode, now_ms() - view->received_ms <= 2500, btn, event);
    if (choice == PET_ACTION_NONE || choice == PET_ACTION_SETUP || choice == PET_ACTION_PLAY) return false;
    if (choice == PET_ACTION_CONSUME || choice == PET_ACTION_HOME || s_dictating) return true;
    action_t action = {.pending_mode = pet_control_pending_mode(view->mode, choice)};
    memcpy(action.token, view->token, 16);
    if (choice == PET_ACTION_DICTATE) {
        s_swallow_click = true;
        action.command = "record";
        s_held = s_physical_ok;
    } else {
        action.command = choice == PET_ACTION_OK ? "ok" : choice == PET_ACTION_UP ? "up" :
                         choice == PET_ACTION_DOWN ? "down" : choice == PET_ACTION_BACK ? "back" :
                         choice == PET_ACTION_NEW ? "new" : "cancel";
    }
    bool queued = xQueueSend(s_actions, &action, 0) == pdTRUE;
    if (!queued && choice == PET_ACTION_DICTATE) s_held = false;
    return true;
}
