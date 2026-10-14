// Independent Codex companion. The USB/application worker owns protocol state;
// LVGL owns animation. Button callbacks only enqueue bounded events.
#include "bsp_i2c.h"
#include "bsp_pins.h"
#include "bsp_display.h"
#include "bsp_button.h"
#include "bsp_battery.h"
#include "key_guard.h"
#include "pet_state.h"
#include "pet_ui.h"
#include "pet_network.h"
#include "pet_control.h"
#include "pet_button_policy.h"
#include <stdatomic.h>
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

static const char *TAG = "codex_pet";
typedef struct { bsp_btn_t btn; bsp_btn_ev_t event; } input_event_t;
static QueueHandle_t s_input_queue;
static atomic_bool s_input_ready;
static portMUX_TYPE s_key_lock = portMUX_INITIALIZER_UNLOCKED;
static key_guard_t s_key_guard;
static pet_control_view_t s_presented;
static pet_navigation_t s_navigation;

static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    (void)user;
    portENTER_CRITICAL(&s_key_lock);
    bool consumed = key_guard_consume(&s_key_guard, ev == BSP_BTN_RELEASE, esp_timer_get_time());
    portEXIT_CRITICAL(&s_key_lock);
    if (consumed) return;
    pet_control_key_edge(btn, ev);
    if (!s_input_ready || !s_input_queue) return;
    const input_event_t input = {.btn = btn, .event = ev};
    (void)xQueueSend(s_input_queue, &input, 0);
}

void app_main(void) {
    ESP_LOGI(TAG, "Codex pet companion starting");
    if (esp_sleep_get_wakeup_causes() & (1u << ESP_SLEEP_WAKEUP_GPIO))
        key_guard_arm(&s_key_guard, esp_timer_get_time(), 10LL * 1000 * 1000);
    esp_err_t i2c = bsp_i2c_init();
    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
        ESP_LOGE(TAG, "Display initialization failed");
        return;
    }
    int brightness = 80;
    bsp_display_backlight(brightness);
    bool battery_ok = i2c == ESP_OK && bsp_battery_init() == ESP_OK;
    int battery = battery_ok ? bsp_battery_soc() : -1;
    if (!bsp_lvgl_lock(1000)) return;
    bool created = pet_ui_create();
    bsp_lvgl_unlock();
    if (!created) { ESP_LOGE(TAG, "Pet UI allocation failed"); return; }
    bool network_ok = pet_network_init() == ESP_OK;
    if (!network_ok) ESP_LOGE(TAG, "Wi-Fi setup failed; USB remains available");
    bool setup = network_ok && pet_network_is_setup();
    bool control_ok = network_ok && !setup && pet_control_start();
    if (setup && bsp_lvgl_lock(1000)) {
        char qr[PET_SETUP_QR_CAPACITY], link[48], help[112];
        pet_network_info(link, sizeof(link), help, sizeof(help));
        (void)pet_network_setup_qr(qr);
        pet_ui_setup(qr, help);
        bsp_lvgl_unlock();
    }
    s_input_queue = xQueueCreate(8, sizeof(input_event_t));
    if (s_input_queue) {
        if (bsp_button_init(on_key, NULL) == ESP_OK) {
            bool released = bsp_button_read_mv() >= BSP_BTN_MV_RELEASED_MIN;
            portENTER_CRITICAL(&s_key_lock);
            key_guard_sync_released(&s_key_guard, released);
            portEXIT_CRITICAL(&s_key_lock);
            s_input_ready = true;
        } else ESP_LOGW(TAG, "Buttons unavailable; USB pet remains active");
    }
    int flags = fcntl(STDIN_FILENO, F_GETFL);
    bool usb_ok = flags >= 0 && fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) >= 0;
    if (!usb_ok) ESP_LOGW(TAG, "USB input unavailable; Wi-Fi remains active");
    ESP_LOGI(TAG, "Free heap: %u; largest block: %u", (unsigned)esp_get_free_heap_size(),
             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    pet_parser_t parser = {0};
    pet_state_t state = {0};
    uint64_t last_ui = 0, last_battery = 0;
    bool home_reported = false;
    for (;;) {
        uint64_t now = (uint64_t)esp_timer_get_time() / 1000;
        char bytes[64];
        ssize_t n = usb_ok ? read(STDIN_FILENO, bytes, sizeof(bytes)) : 0;
        if (network_ok) pet_network_poll(&state, now);
        for (ssize_t i = 0; i < n; ++i) (void)pet_feed(&parser, &state, bytes[i], now);
        if (now - last_battery >= 30000) {
            battery = battery_ok ? bsp_battery_soc() : -1;
            last_battery = now;
        }
        input_event_t input;
        // Bound queue draining so noisy input cannot starve USB/timeout updates.
        for (unsigned i = 0; s_input_queue && i < 8 && xQueueReceive(s_input_queue, &input, 0) == pdTRUE; ++i) {
            if (setup) {
                if (input.btn == BSP_BTN_OK && input.event == BSP_BTN_CLICK && bsp_lvgl_lock(50)) {
                    pet_ui_setup_next();
                    bsp_lvgl_unlock();
                }
                continue;
            }
            if (control_ok) {
                bool fresh = s_presented.mode && now >= s_presented.received_ms &&
                             now - s_presented.received_ms <= 2500;
                pet_navigation_update(&s_navigation, s_presented.mode, fresh, s_presented.opened, now);
                pet_navigation_activity(&s_navigation, now);
                if (pet_navigation_input(&s_navigation, s_presented.mode, fresh,
                                         input.btn, input.event)) continue;
                if (!s_navigation.visible && fresh && input.event == BSP_BTN_CLICK) {
                    if (pet_control_open(&s_presented))
                        pet_navigation_open(&s_navigation, s_presented.opened, now);
                    continue; // Wake never also moves selection, sends, or approves.
                }
                if (s_navigation.opening) continue;
                if (s_navigation.visible && pet_control_input(input.btn, input.event, &s_presented)) continue;
                if (!s_navigation.visible && s_presented.mode &&
                    !(input.btn == BSP_BTN_DOWN && input.event == BSP_BTN_LONG)) continue;
            }
            if (input.btn == BSP_BTN_DOWN && input.event == BSP_BTN_LONG && !s_navigation.visible) {
                pet_network_setup();
            } else if (input.btn == BSP_BTN_OK && input.event == BSP_BTN_CLICK && !s_presented.mode) {
                if (bsp_lvgl_lock(50)) { pet_ui_play(); bsp_lvgl_unlock(); }
            }
        }
        if (now - last_ui >= 200 && bsp_lvgl_lock(50)) {
            pet_status_t visible = pet_visible_status(&state, now);
            char link[48], help[112];
            if (network_ok) pet_network_info(link, sizeof(link), help, sizeof(help));
            else { snprintf(link, sizeof(link), "Wi-Fi / UNAVAILABLE"); snprintf(help, sizeof(help), "Restart to retry Wi-Fi"); }
            pet_ui_network(link, help);
            pet_ui_update(visible, visible == PET_OFFLINE ? 0 : state.active,
                          visible == PET_OFFLINE ? 0 : state.waiting, battery);
            if (control_ok) {
                pet_control_snapshot(&s_presented);
                // The network task can receive a frame during this loop's I/O.
                // Sample time after the snapshot so a new frame is never stale.
                uint64_t control_now = (uint64_t)esp_timer_get_time() / 1000;
                bool fresh = control_now >= s_presented.received_ms &&
                             control_now - s_presented.received_ms <= 2500;
                pet_navigation_update(&s_navigation, s_presented.mode, fresh, s_presented.opened, control_now);
                pet_ui_control(&s_presented, s_navigation.visible && !s_navigation.opening);
                if (!home_reported && s_presented.has_home && control_now >= 10000) {
                    ESP_LOGI(TAG, "Overview received: %u running, %u waiting, %u rows; heap %u; largest %u",
                             s_presented.home.active - s_presented.home.waiting, s_presented.home.waiting,
                             s_presented.home.rows, (unsigned)esp_get_free_heap_size(),
                             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                    home_reported = true;
                }
            }
            bsp_lvgl_unlock();
            last_ui = now;
        }
        vTaskDelay(pdMS_TO_TICKS(25));
    }
}
