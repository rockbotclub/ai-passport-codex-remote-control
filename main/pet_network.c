#include "pet_network.h"
#include "pet_packet.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "bootloader_random.h"
#include <unistd.h>
#include "esp_system.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "mbedtls/md.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define UDP_PORT 19284
#define CONNECTED BIT0
#define RETRY BIT1
#define REBOOT BIT2
#define CONFIGURE BIT3
#define SCAN BIT4
#define SCAN_DONE BIT5
#define SCAN_LIMIT 16
static EventGroupHandle_t s_events;
static esp_netif_t *s_netif;
static httpd_handle_t s_http;
static nvs_handle_t s_nvs;
static int s_socket = -1;
static int s_dns_socket = -1;
static char s_key[33], s_ap_password[13], s_ap_name[33];
static bool s_setup;
static uint64_t s_last_sequence, s_retry_at, s_reboot_at;
static portMUX_TYPE s_info_lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t s_peer;
static char s_link[48] = "Wi-Fi / STARTING";
static pet_setup_phase_t s_setup_state;
static const char *s_setup_message = "Choose your Wi-Fi network.";
static wifi_config_t s_candidate;
static bool s_attempt_pending, s_scanning;
static uint64_t s_connect_deadline, s_scan_deadline;
static unsigned s_reboot_delay = 1500;
typedef struct { char ssid[33]; int rssi; bool secure; } setup_ap_t;
static setup_ap_t s_scan_records[SCAN_LIMIT];
static uint16_t s_scan_count;

static void link_set(const char *value) {
    portENTER_CRITICAL(&s_info_lock);
    snprintf(s_link, sizeof(s_link), "%s", value);
    portEXIT_CRITICAL(&s_info_lock);
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, CONNECTED);
        xEventGroupSetBits(s_events, RETRY);
        if (!s_setup) link_set("Wi-Fi / RECONNECTING");
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_SCAN_DONE) {
        xEventGroupSetBits(s_events, SCAN_DONE);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = data;
        char text[48];
        snprintf(text, sizeof(text), "Wi-Fi / " IPSTR, IP2STR(&event->ip_info.ip));
        if (!s_setup) link_set(text);
        xEventGroupSetBits(s_events, CONNECTED);
        xEventGroupClearBits(s_events, RETRY);
    }
}

static esp_err_t send_json(httpd_req_t *request, cJSON *json) {
    if (!json) return httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR, "Allocation failed");
    char *text = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    if (!text) return httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR, "Allocation failed");
    httpd_resp_set_type(request, "application/json");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    esp_err_t result = httpd_resp_sendstr(request, text);
    free(text);
    return result;
}

static esp_err_t json_error(httpd_req_t *request, const char *status, const char *message) {
    httpd_resp_set_status(request, status);
    cJSON *json = cJSON_CreateObject();
    if (json) cJSON_AddStringToObject(json, "message", message);
    return send_json(request, json);
}

static esp_err_t setup_page(httpd_req_t *request) {
    extern const char page_start[] asm("_binary_pet_setup_page_html_start");
    extern const char page_end[] asm("_binary_pet_setup_page_html_end");
    httpd_resp_set_type(request, "text/html; charset=utf-8");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    return httpd_resp_send(request, page_start, page_end - page_start - 1);
}

static esp_err_t captive_page(httpd_req_t *request) {
    httpd_resp_set_type(request, "application/captive+json");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    return httpd_resp_sendstr(request, "{\"captive\":true,\"user-portal-url\":\"" PET_SETUP_URL "\"}");
}

static esp_err_t portal_redirect(httpd_req_t *request, httpd_err_code_t error) {
    (void)error;
    // Redirect connectivity probes as well as unknown HTTP host/path requests.
    httpd_resp_set_status(request, "302 Found");
    httpd_resp_set_hdr(request, "Location", PET_SETUP_URL);
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    return httpd_resp_sendstr(request, "Open " PET_SETUP_URL);
}

static esp_err_t setup_status(httpd_req_t *request) {
    static const char *const names[] = {"idle", "connecting", "failed", "saved"};
    portENTER_CRITICAL(&s_info_lock);
    pet_setup_phase_t state = s_setup_state;
    const char *message = s_setup_message;
    portEXIT_CRITICAL(&s_info_lock);
    cJSON *json = cJSON_CreateObject();
    if (json) {
        cJSON_AddStringToObject(json, "state", names[state]);
        cJSON_AddStringToObject(json, "message", message);
        cJSON_AddStringToObject(json, "key", s_key);
    }
    return send_json(request, json);
}

static esp_err_t setup_networks(httpd_req_t *request) {
    char query[32], refresh[4];
    if (httpd_req_get_url_query_str(request, query, sizeof(query)) == ESP_OK &&
        httpd_query_key_value(query, "refresh", refresh, sizeof(refresh)) == ESP_OK && !strcmp(refresh, "1"))
        xEventGroupSetBits(s_events, SCAN);
    setup_ap_t records[SCAN_LIMIT];
    portENTER_CRITICAL(&s_info_lock);
    uint16_t count = s_scan_count;
    bool scanning = s_scanning;
    memcpy(records, s_scan_records, sizeof(records));
    portEXIT_CRITICAL(&s_info_lock);
    scanning |= (xEventGroupGetBits(s_events) & SCAN) != 0;
    cJSON *json = cJSON_CreateObject();
    if (json) {
        cJSON_AddBoolToObject(json, "scanning", scanning);
        cJSON *list = cJSON_AddArrayToObject(json, "networks");
        for (unsigned i = 0; list && i < count; ++i) {
            cJSON *ap = cJSON_CreateObject();
            if (!ap) break;
            cJSON_AddStringToObject(ap, "ssid", records[i].ssid);
            cJSON_AddBoolToObject(ap, "secure", records[i].secure);
            cJSON_AddNumberToObject(ap, "rssi", records[i].rssi);
            cJSON_AddItemToArray(list, ap);
        }
    }
    return send_json(request, json);
}

static esp_err_t configure(httpd_req_t *request) {
    char body[512];
    if (request->content_len <= 0 || request->content_len >= sizeof(body))
        return json_error(request, "400 Bad Request", "Invalid configuration size.");
    size_t used = 0;
    while (used < request->content_len) {
        int n = httpd_req_recv(request, body + used, request->content_len - used);
        if (n <= 0) return json_error(request, "408 Request Timeout", "Retry configuration.");
        used += (size_t)n;
    }
    body[used] = 0;
    cJSON *json = cJSON_ParseWithOpts(body, NULL, true);
    cJSON *ssid = cJSON_GetObjectItemCaseSensitive(json, "ssid");
    cJSON *password = cJSON_GetObjectItemCaseSensitive(json, "password");
    bool valid = cJSON_IsString(ssid) && cJSON_IsString(password) && strlen(ssid->valuestring) > 0 &&
                 strlen(ssid->valuestring) <= 32 && strlen(password->valuestring) <= 63 &&
                 (!password->valuestring[0] || strlen(password->valuestring) >= 8);
    if (!valid) {
        cJSON_Delete(json);
        return json_error(request, "400 Bad Request", "SSID: 1-32 bytes; password: empty or 8-63 bytes.");
    }
    wifi_config_t wifi = {0};
    memcpy(wifi.sta.ssid, ssid->valuestring, strlen(ssid->valuestring));
    memcpy(wifi.sta.password, password->valuestring, strlen(password->valuestring));
    cJSON_Delete(json);
    portENTER_CRITICAL(&s_info_lock);
    bool busy = s_attempt_pending || !pet_provision_can_request(s_setup_state);
    if (!busy) {
        s_candidate = wifi;
        s_attempt_pending = true;
        s_setup_state = PET_SETUP_CONNECTING;
        s_setup_message = "Connecting. Keep the setup hotspot connected.";
    }
    portEXIT_CRITICAL(&s_info_lock);
    if (busy) return json_error(request, "409 Conflict", "A connection attempt is already in progress.");
    xEventGroupSetBits(s_events, CONFIGURE);
    httpd_resp_set_type(request, "application/json");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    return httpd_resp_sendstr(request, "{\"state\":\"connecting\"}");
}

esp_err_t pet_network_init(void) {
    esp_err_t result = nvs_flash_init();
    if (result != ESP_OK) return result; // Never erase existing data to hide an error.
    result = nvs_open("codex_pet", NVS_READWRITE, &s_nvs);
    if (result != ESP_OK) return result;
    size_t key_size = sizeof(s_key);
    result = nvs_get_str(s_nvs, "key", s_key, &key_size);
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        uint8_t random[16];
        bootloader_random_enable();
        esp_fill_random(random, sizeof(random));
        bootloader_random_disable();
        for (size_t i = 0; i < sizeof(random); ++i) snprintf(s_key + 2*i, 3, "%02x", random[i]);
        result = nvs_set_str(s_nvs, "key", s_key);
        if (result == ESP_OK) result = nvs_commit(s_nvs);
    }
    if (result != ESP_OK || strlen(s_key) != 32) return ESP_FAIL;
    wifi_config_t wifi = {0};
    size_t wifi_size = sizeof(wifi.sta);
    uint8_t setup = 0;
    result = nvs_get_blob(s_nvs, "wifi", &wifi.sta, &wifi_size);
    (void)nvs_get_u8(s_nvs, "setup", &setup);
    s_setup = setup || result == ESP_ERR_NVS_NOT_FOUND;
    if (result != ESP_OK && result != ESP_ERR_NVS_NOT_FOUND) return result;
    // Generate AP credentials before the Wi-Fi/ADC subsystems own the RNG
    // entropy source; both bootloader_random calls are early-startup only.
    if (s_setup) {
        bootloader_random_enable();
        uint32_t random = esp_random();
        snprintf(s_ap_name, sizeof(s_ap_name), "CodexPet-%04" PRIx32, random & 0xffff);
        snprintf(s_ap_password, sizeof(s_ap_password), "%08" PRIx32 "%04" PRIx32, random, esp_random() & 0xffff);
        bootloader_random_disable();
    }
    s_events = xEventGroupCreate();
    if (!s_events) return ESP_ERR_NO_MEM;
    result = esp_netif_init(); if (result != ESP_OK) return result;
    result = esp_event_loop_create_default(); if (result != ESP_OK) return result;
    s_netif = s_setup ? esp_netif_create_default_wifi_ap() : esp_netif_create_default_wifi_sta();
    if (!s_netif) return ESP_ERR_NO_MEM;
    if (s_setup && !esp_netif_create_default_wifi_sta()) return ESP_ERR_NO_MEM;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    result = esp_wifi_init(&init); if (result != ESP_OK) return result;
    result = esp_wifi_set_storage(WIFI_STORAGE_RAM); if (result != ESP_OK) return result;
    result = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL); if (result != ESP_OK) return result;
    result = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL); if (result != ESP_OK) return result;
    if (s_setup) {
        // The union may still contain saved STA fields. Clear it before building
        // the AP config so a shorter temporary password cannot retain a suffix.
        memset(&wifi, 0, sizeof(wifi));
        memcpy(wifi.ap.ssid, s_ap_name, strlen(s_ap_name)); wifi.ap.ssid_len = strlen(s_ap_name);
        memcpy(wifi.ap.password, s_ap_password, strlen(s_ap_password));
        wifi.ap.authmode = WIFI_AUTH_WPA2_PSK; wifi.ap.max_connection = 1;
        // Keep the portal reachable while scanning/validating the target network.
        result = esp_wifi_set_mode(WIFI_MODE_APSTA); if (result != ESP_OK) return result;
        result = esp_wifi_set_config(WIFI_IF_AP, &wifi); if (result != ESP_OK) return result;
        result = esp_netif_dhcps_stop(s_netif);
        if (result != ESP_OK && result != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED) return result;
        esp_netif_ip_info_t ap_ip = {
            .ip.addr = ESP_IP4TOADDR(192,168,4,1), .gw.addr = ESP_IP4TOADDR(192,168,4,1),
            .netmask.addr = ESP_IP4TOADDR(255,255,255,0)
        };
        result = esp_netif_set_ip_info(s_netif, &ap_ip); if (result != ESP_OK) return result;
        esp_netif_dns_info_t dns = {.ip.type = ESP_IPADDR_TYPE_V4, .ip.u_addr.ip4.addr = ap_ip.ip.addr};
        result = esp_netif_set_dns_info(s_netif, ESP_NETIF_DNS_MAIN, &dns); if (result != ESP_OK) return result;
        // IDF retains this pointer; the constant has application lifetime.
        result = esp_netif_dhcps_option(s_netif, ESP_NETIF_OP_SET, ESP_NETIF_CAPTIVEPORTAL_URI,
                                       (void *)PET_SETUP_CAPTIVE_URL, strlen(PET_SETUP_CAPTIVE_URL));
        if (result != ESP_OK) return result;
        result = esp_netif_dhcps_start(s_netif); if (result != ESP_OK) return result;
        result = esp_wifi_start(); if (result != ESP_OK) return result;
        s_dns_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        struct sockaddr_in dns_address = {.sin_family=AF_INET, .sin_port=htons(53), .sin_addr.s_addr=ap_ip.ip.addr};
        if (s_dns_socket < 0) return ESP_FAIL;
        if (bind(s_dns_socket, (struct sockaddr *)&dns_address, sizeof(dns_address)) < 0 ||
            fcntl(s_dns_socket, F_SETFL, O_NONBLOCK) < 0) {
            close(s_dns_socket); s_dns_socket = -1; return ESP_FAIL;
        }
        httpd_config_t config = HTTPD_DEFAULT_CONFIG();
        config.max_uri_handlers = 5; config.stack_size = 6144; config.max_open_sockets = 3;
        config.lru_purge_enable = true; config.recv_wait_timeout = 5; config.send_wait_timeout = 5;
        result = httpd_start(&s_http, &config);
        if (result != ESP_OK) { close(s_dns_socket); s_dns_socket = -1; return result; }
        httpd_uri_t get = {.uri="/", .method=HTTP_GET, .handler=setup_page};
        httpd_uri_t post = {.uri="/configure", .method=HTTP_POST, .handler=configure};
        httpd_uri_t status = {.uri="/status", .method=HTTP_GET, .handler=setup_status};
        httpd_uri_t networks = {.uri="/networks", .method=HTTP_GET, .handler=setup_networks};
        httpd_uri_t captive = {.uri="/captive", .method=HTTP_GET, .handler=captive_page};
        const httpd_uri_t *routes[] = {&get, &post, &status, &networks, &captive};
        for (unsigned i = 0; i < sizeof(routes)/sizeof(routes[0]); ++i) {
            result = httpd_register_uri_handler(s_http, routes[i]);
            if (result != ESP_OK) break;
        }
        if (result == ESP_OK) result = httpd_register_err_handler(s_http, HTTPD_404_NOT_FOUND, portal_redirect);
        if (result != ESP_OK) {
            httpd_stop(s_http); s_http = NULL;
            close(s_dns_socket); s_dns_socket = -1;
            return result;
        }
        xEventGroupSetBits(s_events, SCAN);
        link_set("Wi-Fi / SETUP");
    } else {
        result = esp_wifi_set_mode(WIFI_MODE_STA); if (result != ESP_OK) return result;
        result = esp_wifi_set_config(WIFI_IF_STA, &wifi); if (result != ESP_OK) return result;
        result = esp_wifi_start(); if (result != ESP_OK) return result;
        link_set("Wi-Fi / CONNECTING");
        result = esp_wifi_connect(); if (result != ESP_OK) return result;
        s_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (s_socket < 0) return ESP_FAIL;
        struct sockaddr_in address = {.sin_family=AF_INET, .sin_port=htons(UDP_PORT), .sin_addr.s_addr=htonl(INADDR_ANY)};
        if (bind(s_socket, (struct sockaddr *)&address, sizeof(address)) < 0 ||
            fcntl(s_socket, F_SETFL, O_NONBLOCK) < 0) {
            close(s_socket); s_socket = -1; return ESP_FAIL;
        }
    }
    return ESP_OK;
}

static bool authenticated(const pet_packet_t *packet) {
    const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    unsigned char digest[32];
    if (!md || mbedtls_md_hmac(md, (const unsigned char *)s_key, 32,
                             (const unsigned char *)packet->payload, packet->payload_length, digest)) return false;
    char expected[65];
    for (unsigned i = 0; i < 32; ++i) snprintf(expected + i*2, 3, "%02x", digest[i]);
    unsigned mismatch = 0;
    for (unsigned i = 0; i < 64; ++i) mismatch |= (unsigned char)packet->signature[i] ^ (unsigned char)expected[i];
    return mismatch == 0;
}

static void setup_finish(pet_setup_phase_t state, const char *message) {
    portENTER_CRITICAL(&s_info_lock);
    s_setup_state = state;
    s_setup_message = message;
    s_attempt_pending = false;
    portEXIT_CRITICAL(&s_info_lock);
    s_connect_deadline = 0;
}

static void setup_poll(uint64_t now_ms) {
    // The application worker owns sockets, scans, connection attempts and NVS.
    // No new task is needed on the no-PSRAM board; bound DNS work per iteration.
    for (unsigned i = 0; s_dns_socket >= 0 && i < 4; ++i) {
        uint8_t query[513], reply[512], ip[4] = {192,168,4,1};
        struct sockaddr_in client;
        socklen_t size = sizeof(client);
        int n = recvfrom(s_dns_socket, query, sizeof(query), 0, (struct sockaddr *)&client, &size);
        if (n <= 0) break;
        size_t length = pet_provision_dns(query, (size_t)n, reply, sizeof(reply), ip);
        if (length) (void)sendto(s_dns_socket, reply, length, MSG_DONTWAIT, (struct sockaddr *)&client, size);
    }
    EventBits_t events = xEventGroupGetBits(s_events);
    if ((events & SCAN_DONE) || (s_scan_deadline && now_ms >= s_scan_deadline)) {
        xEventGroupClearBits(s_events, SCAN_DONE);
        uint16_t count = SCAN_LIMIT;
        wifi_ap_record_t *records = calloc(SCAN_LIMIT, sizeof(*records));
        if (!(events & SCAN_DONE)) (void)esp_wifi_scan_stop();
        if (!records || esp_wifi_scan_get_ap_records(&count, records) != ESP_OK) count = 0;
        // Always release driver scan results, even on allocation/API failure.
        (void)esp_wifi_clear_ap_list();
        setup_ap_t aps[SCAN_LIMIT] = {0};
        uint16_t used = 0;
        for (unsigned i = 0; i < count; ++i) {
            if (!records[i].ssid[0]) continue;
            bool duplicate = false;
            for (unsigned j = 0; j < used; ++j)
                if (!strcmp(aps[j].ssid, (char *)records[i].ssid)) duplicate = true;
            if (duplicate) continue;
            memcpy(aps[used].ssid, records[i].ssid, 32);
            aps[used].rssi = records[i].rssi;
            aps[used++].secure = records[i].authmode != WIFI_AUTH_OPEN;
        }
        free(records);
        portENTER_CRITICAL(&s_info_lock);
        memcpy(s_scan_records, aps, sizeof(aps));
        s_scan_count = used;
        s_scanning = false;
        portEXIT_CRITICAL(&s_info_lock);
        s_scan_deadline = 0;
    }
    if ((events & CONFIGURE) && !s_scan_deadline) {
        xEventGroupClearBits(s_events, CONFIGURE | CONNECTED | RETRY | SCAN);
        portENTER_CRITICAL(&s_info_lock);
        wifi_config_t candidate = s_candidate;
        portEXIT_CRITICAL(&s_info_lock);
        esp_err_t result = esp_wifi_set_config(WIFI_IF_STA, &candidate);
        if (result == ESP_OK) result = esp_wifi_connect();
        if (result == ESP_OK) { s_connect_deadline = now_ms + 25000; link_set("Wi-Fi / CONNECTING"); }
        else setup_finish(PET_SETUP_FAILED, "Cannot start connection. Please retry.");
        return;
    }
    if (s_connect_deadline) {
        pet_setup_decision_t decision = pet_provision_decide(now_ms, s_connect_deadline,
                                                           events & CONNECTED, events & RETRY);
        if (decision == PET_SETUP_SAVE) {
            // Only persist credentials after obtaining an IP, as one NVS blob.
            esp_err_t result = nvs_set_blob(s_nvs, "wifi", &s_candidate.sta, sizeof(s_candidate.sta));
            if (result == ESP_OK) result = nvs_set_u8(s_nvs, "setup", 0);
            if (result == ESP_OK) result = nvs_commit(s_nvs);
            if (result == ESP_OK) {
                setup_finish(PET_SETUP_SAVED, "Connected. Saved. Restarting.");
                link_set("Wi-Fi / CONNECTED");
                s_reboot_delay = 8000;
                xEventGroupSetBits(s_events, REBOOT);
            } else {
                (void)esp_wifi_disconnect();
                setup_finish(PET_SETUP_FAILED, "Connected, but cannot save settings. Please retry.");
                link_set("Wi-Fi / SAVE FAILED");
            }
        } else if (decision == PET_SETUP_RETRY) {
            (void)esp_wifi_disconnect();
            xEventGroupClearBits(s_events, RETRY | CONNECTED);
            setup_finish(PET_SETUP_FAILED, "Cannot connect. Check the password, 2.4 GHz network and signal, then retry.");
            link_set("Wi-Fi / TRY AGAIN");
        }
        return;
    }
    portENTER_CRITICAL(&s_info_lock);
    bool idle = !s_attempt_pending && pet_provision_can_request(s_setup_state);
    portEXIT_CRITICAL(&s_info_lock);
    if ((events & SCAN) && idle && !s_scan_deadline) {
        xEventGroupClearBits(s_events, SCAN | SCAN_DONE);
        wifi_scan_config_t scan = {.show_hidden = false};
        if (esp_wifi_scan_start(&scan, false) == ESP_OK) {
            portENTER_CRITICAL(&s_info_lock);
            s_scanning = true;
            portEXIT_CRITICAL(&s_info_lock);
            s_scan_deadline = now_ms + 15000;
        }
    }
}

void pet_network_poll(pet_state_t *state, uint64_t now_ms) {
    if (!s_events) return;
    if (s_setup) setup_poll(now_ms);
    EventBits_t events = xEventGroupGetBits(s_events);
    if (events & REBOOT) {
        if (!s_reboot_at) s_reboot_at = now_ms + s_reboot_delay;
        if (now_ms >= s_reboot_at) esp_restart();
    }
    if (!s_setup && (events & RETRY) && now_ms >= s_retry_at) {
        s_retry_at = now_ms + 5000;
        (void)esp_wifi_connect();
    }
    if (s_socket < 0 || !(events & CONNECTED)) return;
    // Bound packets per tick so a LAN flood cannot starve display/input.
    for (unsigned i = 0; i < 4; ++i) {
        char packet[192];
        struct sockaddr_in sender = {0};
        socklen_t sender_size = sizeof(sender);
        int n = recvfrom(s_socket, packet, sizeof(packet)-1, 0, (struct sockaddr *)&sender, &sender_size);
        if (n <= 0) break;
        if (n >= sizeof(packet)-1) continue;
        packet[n] = 0;
        pet_packet_t decoded;
        if (!pet_packet_decode(packet, (size_t)n, s_last_sequence, now_ms, &decoded) || !authenticated(&decoded)) continue;
        portENTER_CRITICAL(&s_info_lock);
        s_peer = sender.sin_addr.s_addr;
        portEXIT_CRITICAL(&s_info_lock);
        *state = decoded.next_state;
        s_last_sequence = decoded.sequence;
    }
}

void pet_network_info(char *link, size_t link_size, char *help, size_t help_size) {
    portENTER_CRITICAL(&s_info_lock);
    snprintf(link, link_size, "%s", s_link);
    portEXIT_CRITICAL(&s_info_lock);
    if (s_setup) snprintf(help, help_size, "%s\n%s", s_ap_name, s_ap_password);
    else snprintf(help, help_size, "Same Wi-Fi as your PC\nHold DOWN to configure");
}

bool pet_network_is_setup(void) { return s_setup; }
bool pet_network_setup_qr(char out[PET_SETUP_QR_CAPACITY]) {
    return pet_provision_qr(out, PET_SETUP_QR_CAPACITY, s_ap_name, s_ap_password);
}

void pet_network_setup(void) {
    if (!s_events || s_setup) return;
    if (nvs_set_u8(s_nvs, "setup", 1) == ESP_OK && nvs_commit(s_nvs) == ESP_OK)
        xEventGroupSetBits(s_events, REBOOT);
}

bool pet_network_peer(uint32_t *address, char key[33]) {
    if (!s_events || !(xEventGroupGetBits(s_events) & CONNECTED) || s_setup) return false;
    portENTER_CRITICAL(&s_info_lock);
    *address = s_peer;
    portEXIT_CRITICAL(&s_info_lock);
    memcpy(key, s_key, 33);
    return *address != 0;
}
