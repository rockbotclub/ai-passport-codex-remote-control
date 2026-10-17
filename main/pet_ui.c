#include "pet_button_policy.h"
#include "pet_ui.h"
#include "pet_provision.h"
#include "lvgl.h"
#include "src/misc/lv_text_private.h"
#include "src/misc/cache/instance/lv_image_cache.h"
#include "src/misc/cache/instance/lv_image_header_cache.h"
#include "bsp_pins.h"
#include <stdio.h>
#include <string.h>
#include "esp_timer.h"
#include "esp_log.h"

LV_FONT_DECLARE(passport_font_12);
LV_FONT_DECLARE(passport_font_14);
LV_FONT_DECLARE(passport_font_20);

// Validate the actual descriptors before any label can display Chinese.
static bool fonts_ready(void) {
    extern const char inventory[] asm("_binary_passport_ui_glyphs_txt_start");
    const lv_font_t *fonts[] = {&passport_font_12, &passport_font_14, &passport_font_20};
    for (unsigned f = 0; f < sizeof(fonts) / sizeof(fonts[0]); ++f) {
        uint32_t offset = 0;
        while (inventory[offset]) {
            uint32_t codepoint = lv_text_encoded_next(inventory, &offset);
            if (codepoint == '\n') continue;
            lv_font_glyph_dsc_t glyph = {0};
            if (!lv_font_get_glyph_dsc(fonts[f], &glyph, codepoint, 0) || glyph.is_placeholder) {
                ESP_LOGE("pet_ui", "字体 %u 缺少字符 U+%04lX", f, (unsigned long)codepoint);
                return false;
            }
        }
        lv_font_glyph_dsc_t missing = {0};
        if (lv_font_get_glyph_dsc(fonts[f], &missing, 0x10ffff, 0) && !missing.is_placeholder)
            return false;
    }
    return true;
}

#include "../assets/images/codex-pet/frames.inc"
#include "../assets/images/codex-pet/offline.inc"
#include "../assets/images/codex-pet/syncing.inc"
_Static_assert(sizeof(pet_syncing_pixels) == PET_HOME_LIST_BYTES, "同步提示位图大小无效");
_Static_assert(sizeof(pet_offline_pixels) == PET_HOME_LIST_BYTES, "离线提示位图大小无效");

#define BACKGROUND 0x101826
static lv_obj_t *s_pet, *s_status, *s_detail, *s_battery, *s_link;
static lv_timer_t *s_timer;
static lv_obj_t *s_panel, *s_footer, *s_sync_dots[3];
static lv_obj_t *s_setup_card, *s_qr;
static char s_setup_qr[PET_SETUP_QR_CAPACITY], s_setup_help[64];
static bool s_setup, s_control_visible;
static bool s_home_visible, s_control_seen, s_control_online;
static pet_status_t s_heartbeat_state = PET_OFFLINE;
static lv_obj_t *s_home_summary, *s_home_title, *s_home_list, *s_home_footer, *s_highlight[3];
static lv_obj_t *s_home_rule[3];
static uint8_t s_summary_data[8 + PET_HOME_SUMMARY_BYTES];
static uint8_t s_title_data[8 + 13 * 26];
static uint8_t s_list_data[8 + PET_HOME_LIST_BYTES];
static uint8_t s_home_footer_data[8 + PET_HOME_FOOTER_BYTES];
static lv_image_dsc_t s_summary_image, s_title_image, s_list_image, s_home_footer_image;
static unsigned s_setup_step;
static uint8_t s_panel_data[8 + PET_CONTROL_PIXELS];
static lv_image_dsc_t s_panel_image;
static pet_status_t s_state = PET_OFFLINE;
static unsigned s_frame, s_play_frames, s_active, s_waiting;
static char s_network_help[112];
static const char *const labels[] = {"电脑已断开", "暂无任务", "正在工作", "需要你处理", "本轮已结束", "请查看 Codex", "正在同步任务"};
static const uint32_t colors[] = {0x7D8A9E, 0x9EAFCA, 0x75B8FF, 0xFFC56D, 0x91DEBE, 0xFF9191, 0xA6A1FF};

static lv_obj_t *label(lv_obj_t *parent, const char *text, int y, const lv_font_t *font, uint32_t color) {
    lv_obj_t *obj = lv_label_create(parent);
    lv_obj_set_style_text_font(obj, font, 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(color), 0);
    lv_label_set_text(obj, text);
    lv_obj_align(obj, LV_ALIGN_TOP_MID, 0, y);
    return obj;
}

static void hidden(lv_obj_t *object, bool hide) {
    if (hide) lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
}

static lv_obj_t *bitmap(lv_obj_t *screen, lv_image_dsc_t *image, uint8_t *data,
                       unsigned width, unsigned height, int x, int y, bool transparent) {
    const uint8_t palette[8] = {0x26,0x18,0x10,transparent ? 0 : 0xff,0xfc,0xe8,0xdc,0xff};
    memcpy(data, palette, sizeof(palette));
    image->header.magic = LV_IMAGE_HEADER_MAGIC;
    image->header.cf = LV_COLOR_FORMAT_I1;
    image->header.w = width; image->header.h = height; image->header.stride = width / 8;
    image->data = data; image->data_size = 8 + width * height / 8;
    lv_obj_t *object = lv_image_create(screen);
    lv_image_set_src(object, image); lv_obj_set_pos(object, x, y); hidden(object, true);
    return object;
}

static void bitmap_update(lv_obj_t *object, lv_image_dsc_t *image, uint8_t *data,
                          const uint8_t *pixels, size_t count) {
    if (memcmp(data + 8, pixels, count)) {
        memcpy(data + 8, pixels, count);
        lv_image_cache_drop(image);
        lv_image_header_cache_drop(image);
        lv_image_set_src(object, image);
        lv_obj_invalidate(object);
    }
    hidden(object, false);
}

static void home_hide(void) {
    s_home_visible = false;
    lv_obj_t *objects[] = {s_home_summary, s_home_title, s_home_list, s_home_footer};
    for (unsigned i = 0; i < 4; ++i) hidden(objects[i], true);
    for (unsigned i = 0; i < 3; ++i) hidden(s_highlight[i], true);
    for (unsigned i = 0; i < 3; ++i) hidden(s_home_rule[i], true);
}

static const lv_image_dsc_t *animation_frame(pet_animation_t animation, unsigned frame) {
    static const lv_image_dsc_t *const *const rows[] = {
        [0] = row_0, [4] = row_4, [5] = row_5, [6] = row_6, [7] = row_7
    };
    return rows[animation.row][animation.first + frame % animation.count];
}

static void sync_dots(unsigned frame) {
    for (unsigned i = 0; i < 3; ++i) {
        bool visible = s_state == PET_SYNCING && !s_setup && !s_control_visible;
        hidden(s_sync_dots[i], !visible);
        lv_obj_set_pos(s_sync_dots[i], 99 + i * 18, i == frame % 3 ? 211 : 215);
        lv_obj_set_style_bg_opa(s_sync_dots[i], i == frame % 3 ? LV_OPA_COVER : LV_OPA_40, 0);
    }
}

static void state_set(pet_status_t status) {
    if (status == s_state) return;
    s_state = status; s_frame = 0; s_play_frames = 0;
    sync_dots(0);
    pet_animation_t animation = pet_animation(status);
    lv_timer_set_period(s_timer, animation.period_ms);
    lv_image_set_src(s_pet, animation_frame(animation, 0));
}

static void home_show(const pet_home_view_t *home) {
    s_home_visible = true;
    state_set(home->status);
    hidden(s_pet, false); hidden(s_status, true); hidden(s_detail, true); hidden(s_footer, true);
    hidden(s_panel, true);
    lv_image_set_scale(s_pet, home->rows ? 171 : 256);
    lv_obj_set_pos(s_pet, home->rows ? 8 : 48, home->rows ? 37 : 54);
    const uint8_t *pixels = home->pixels;
    bitmap_update(s_home_summary, &s_summary_image, s_summary_data, pixels, PET_HOME_SUMMARY_BYTES);
    hidden(s_home_summary, !home->rows);
    // A small overlay colors only the status heading, leaving counts readable.
    uint32_t color = colors[home->status];
    uint8_t r = color >> 16, g = color >> 8, b = color;
    bool tint_changed = s_title_data[4] != b || s_title_data[5] != g || s_title_data[6] != r;
    s_title_data[4] = b; s_title_data[5] = g; s_title_data[6] = r;
    if (tint_changed) { lv_image_cache_drop(&s_title_image); lv_obj_invalidate(s_home_title); }
    bitmap_update(s_home_title, &s_title_image, s_title_data, pixels, 13 * 26);
    hidden(s_home_title, !home->rows);
    pixels += PET_HOME_SUMMARY_BYTES;
    bitmap_update(s_home_list, &s_list_image, s_list_data, pixels, PET_HOME_LIST_BYTES);
    pixels += PET_HOME_LIST_BYTES;
    bitmap_update(s_home_footer, &s_home_footer_image, s_home_footer_data, pixels, PET_HOME_FOOTER_BYTES);
    for (unsigned i = 0; i < 3; ++i) {
        bool waiting = home->waiting_mask & (1u << i);
        bool single = home->rows == 1 && i == 0;
        lv_obj_set_style_bg_color(s_highlight[i], lv_color_hex(waiting ? 0xFFC56D : 0x75B8FF), 0);
        lv_obj_set_style_border_width(s_highlight[i], waiting ? 2 : 0, 0);
        lv_obj_set_height(s_highlight[i], single ? 112 : 45);
        hidden(s_highlight[i], !waiting && !single);
        hidden(s_home_rule[i], home->rows <= 1 || i >= home->rows || waiting);
    }
}

static void animate(lv_timer_t *timer) {
    (void)timer;
    sync_dots(s_frame);
    if (s_setup || s_control_visible) return;
    pet_animation_t animation = pet_animation(s_state);
    if (s_play_frames) {
        --s_play_frames;
        if (!s_play_frames) lv_timer_set_period(s_timer, animation.period_ms);
        animation = pet_animation(PET_DONE);
    }
    lv_image_set_src(s_pet, animation_frame(animation, s_frame++));
}

static void details_refresh(void) {
    if (s_state == PET_OFFLINE) lv_label_set_text(s_detail, s_network_help);
    else if (s_state == PET_SYNCING) lv_label_set_text(s_detail, "正在读取电脑任务状态");
    else if (s_state == PET_IDLE) lv_label_set_text(s_detail, "随时开始下一件事");
    else lv_label_set_text_fmt(s_detail, "%u 个活跃 / %u 个待处理", s_active, s_waiting);
    lv_obj_align(s_detail, LV_ALIGN_TOP_MID, 0, 248);
}

static void fallback_show(pet_status_t status) {
    home_hide();
    state_set(status);
    hidden(s_pet, false); hidden(s_panel, true); hidden(s_footer, false);
    bool local_text = status == PET_OFFLINE || status == PET_SYNCING;
    hidden(s_status, local_text); hidden(s_detail, local_text);
    lv_image_set_scale(s_pet, 256); lv_obj_set_pos(s_pet, 48, 54);
    if (local_text) {
        // Available even after the computer stops sending text or bitmaps.
        bitmap_update(s_home_list, &s_list_image, s_list_data,
                      status == PET_SYNCING ? pet_syncing_pixels : pet_offline_pixels, PET_HOME_LIST_BYTES);
    } else {
        lv_label_set_text(s_status, labels[status]);
        lv_obj_set_style_text_color(s_status, lv_color_hex(colors[status]), 0);
        lv_obj_align(s_status, LV_ALIGN_TOP_MID, 0, 218);
        details_refresh();
    }
}

bool pet_ui_create(void) {
    if (!fonts_ready()) return false;
    lv_obj_t *screen = lv_obj_create(NULL);
    if (!screen) return false;
    lv_obj_set_style_bg_color(screen, lv_color_hex(BACKGROUND), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *title = label(screen, "CodeX", 10, &passport_font_14, 0xDCE8FC);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 12, 10);
    s_battery = label(screen, "--%", 11, &passport_font_12, 0x9EAFCA);
    lv_obj_align(s_battery, LV_ALIGN_TOP_RIGHT, -12, 11);
    s_link = label(screen, "连接中", 11, &passport_font_12, 0x7D8A9E);
    lv_obj_align(s_link, LV_ALIGN_TOP_LEFT, 85, 11);
    lv_obj_t *rule = lv_obj_create(screen);
    lv_obj_remove_style_all(rule);
    lv_obj_set_style_bg_color(rule, lv_color_hex(0x263248), 0);
    lv_obj_set_style_bg_opa(rule, LV_OPA_COVER, 0);
    lv_obj_set_size(rule, BSP_LCD_W, 1); lv_obj_set_pos(rule, 0, 33);
    s_pet = lv_image_create(screen);
    lv_image_set_src(s_pet, animation_frame(pet_animation(PET_OFFLINE), 0));
    lv_image_set_pivot(s_pet, 0, 0);
    lv_obj_set_align(s_pet, LV_ALIGN_TOP_LEFT);
    lv_obj_set_pos(s_pet, 48, 54);
    s_status = label(screen, labels[PET_OFFLINE], 218, &passport_font_20, colors[PET_OFFLINE]);
    s_detail = label(screen, "", 248, &passport_font_14, 0x9EAFCA);
    lv_obj_set_style_text_align(s_detail, LV_TEXT_ALIGN_CENTER, 0);
    s_footer = label(screen, "长按下键：配网", 296, &passport_font_14, 0x7D8A9E);
    s_panel = lv_image_create(screen);
    lv_obj_add_flag(s_panel, LV_OBJ_FLAG_HIDDEN);
    s_panel_image.header.magic = LV_IMAGE_HEADER_MAGIC;
    s_panel_image.header.cf = LV_COLOR_FORMAT_I1;
    s_panel_image.header.w = PET_CONTROL_WIDTH;
    s_panel_image.header.stride = PET_CONTROL_WIDTH / 8;
    s_panel_image.data = s_panel_data;
    // Native little-endian BGRA palette: background, white foreground.
    const uint8_t palette[8] = {0x26,0x18,0x10,0xff,0xfc,0xe8,0xdc,0xff};
    memcpy(s_panel_data, palette, sizeof(palette));
    for (unsigned i = 0; i < 3; ++i) {
        s_highlight[i] = lv_obj_create(screen);
        lv_obj_remove_style_all(s_highlight[i]);
        lv_obj_set_style_bg_color(s_highlight[i], lv_color_hex(0xFFC56D), 0);
        lv_obj_set_style_bg_opa(s_highlight[i], LV_OPA_10, 0);
        lv_obj_set_style_border_color(s_highlight[i], lv_color_hex(0xFFC56D), 0);
        lv_obj_set_style_border_side(s_highlight[i], LV_BORDER_SIDE_LEFT, 0);
        lv_obj_set_style_border_width(s_highlight[i], 2, 0);
        lv_obj_set_style_radius(s_highlight[i], 3, 0);
        lv_obj_set_size(s_highlight[i], 216, 45); lv_obj_set_pos(s_highlight[i], 12, 144 + 45 * i);
        hidden(s_highlight[i], true);
        s_home_rule[i] = lv_obj_create(screen);
        lv_obj_remove_style_all(s_home_rule[i]);
        lv_obj_set_style_bg_color(s_home_rule[i], lv_color_hex(0x263248), 0);
        lv_obj_set_style_bg_opa(s_home_rule[i], LV_OPA_COVER, 0);
        lv_obj_set_size(s_home_rule[i], 216, 1); lv_obj_set_pos(s_home_rule[i], 12, 188 + 45 * i);
        hidden(s_home_rule[i], true);
    }
    s_home_summary = bitmap(screen, &s_summary_image, s_summary_data, 104, 84, 114, 49, false);
    s_home_title = bitmap(screen, &s_title_image, s_title_data, 104, 26, 114, 49, false);
    s_home_list = bitmap(screen, &s_list_image, s_list_data, 216, 144, 12, 144, true);
    s_home_footer = bitmap(screen, &s_home_footer_image, s_home_footer_data, 216, 24, 12, 294, false);
    for (unsigned i = 0; i < 3; ++i) {
        s_sync_dots[i] = lv_obj_create(screen);
        lv_obj_remove_style_all(s_sync_dots[i]);
        lv_obj_set_size(s_sync_dots[i], 6, 6);
        lv_obj_set_style_radius(s_sync_dots[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(s_sync_dots[i], lv_color_hex(colors[PET_SYNCING]), 0);
        hidden(s_sync_dots[i], true);
    }
    details_refresh();
    s_timer = lv_timer_create(animate, 700, NULL);
    if (!s_timer) { lv_obj_delete(screen); return false; }
    fallback_show(PET_OFFLINE);
    lv_screen_load(screen);
    return true;
}

void pet_ui_update(pet_status_t status, unsigned active, unsigned waiting, int battery) {
    s_heartbeat_state = status;
    s_active = active;
    s_waiting = waiting;
    if (!s_setup && !s_home_visible && !s_control_visible)
        fallback_show(pet_fallback_status(status, s_control_seen, s_control_online));
    if (battery >= 0) lv_label_set_text_fmt(s_battery, "%d%%", battery);
    else lv_label_set_text(s_battery, "--%");
    lv_obj_align(s_battery, LV_ALIGN_TOP_RIGHT, -12, 11);
}

void pet_ui_play(void) { s_play_frames = 10; s_frame = 0; lv_timer_set_period(s_timer, 140); }
void pet_ui_network(const char *link, const char *help) {
    if (s_setup) {
        lv_label_set_text(s_link, s_setup_step ? "2. 打开配网页面" : "1. 连接设备热点");
        lv_obj_align(s_link, LV_ALIGN_TOP_MID, 0, 48);
    } else {
        lv_label_set_text(s_link, !strcmp(link, "Wi-Fi / 不可用") ? "Wi-Fi 不可用" : "连接中");
        lv_obj_align(s_link, LV_ALIGN_TOP_LEFT, 85, 11);
    }
    snprintf(s_network_help, sizeof(s_network_help), "%s", help);
}

static void setup_refresh(void) {
    lv_label_set_text(s_link, s_setup_step ? "2. 打开配网页面" : "1. 连接设备热点");
    lv_obj_align(s_link, LV_ALIGN_TOP_MID, 0, 48);
    const char *payload = s_setup_step ? PET_SETUP_URL : s_setup_qr;
    bool ok = lv_qrcode_update(s_qr, payload, strlen(payload)) == LV_RESULT_OK;
    if (ok) lv_obj_remove_flag(s_setup_card, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(s_setup_card, LV_OBJ_FLAG_HIDDEN);
    lv_label_set_text(s_status, ok ? "" : "请手动配网");
    lv_obj_align(s_status, LV_ALIGN_TOP_MID, 0, 145);
    lv_label_set_text(s_detail, s_setup_step ? "已连接热点？扫码打开\n192.168.4.1" : s_setup_help);
    lv_obj_set_style_text_font(s_detail, &passport_font_12, 0);
    lv_obj_align(s_detail, LV_ALIGN_TOP_MID, 0, 268);
    lv_label_set_text(s_footer, s_setup_step ? "确认键：热点二维码" : "确认键：网页二维码");
    lv_obj_set_style_text_font(s_footer, &passport_font_12, 0);
    lv_obj_align(s_footer, LV_ALIGN_TOP_MID, 0, 302);
}

void pet_ui_setup(const char *wifi_qr, const char *ap_help) {
    if (s_setup) return;
    s_setup = true;
    sync_dots(0);
    home_hide();
    snprintf(s_setup_qr, sizeof(s_setup_qr), "%s", wifi_qr);
    snprintf(s_setup_help, sizeof(s_setup_help), "%s", ap_help);
    lv_timer_pause(s_timer);
    lv_obj_add_flag(s_pet, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(s_panel, LV_OBJ_FLAG_HIDDEN);
    s_setup_card = lv_obj_create(lv_obj_get_parent(s_pet));
    lv_obj_remove_style_all(s_setup_card);
    lv_obj_remove_flag(s_setup_card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(s_setup_card, 200, 200);
    lv_obj_set_style_bg_color(s_setup_card, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(s_setup_card, LV_OPA_COVER, 0);
    lv_obj_align(s_setup_card, LV_ALIGN_TOP_MID, 0, 66);
    s_qr = lv_qrcode_create(s_setup_card);
    lv_qrcode_set_size(s_qr, 176);
    lv_qrcode_set_quiet_zone(s_qr, true);
    lv_obj_center(s_qr);
    setup_refresh();
}

void pet_ui_setup_next(void) {
    if (!s_setup) return;
    s_setup_step ^= 1;
    setup_refresh();
}

void pet_ui_control(const pet_control_view_t *view, bool visible) {
    if (s_setup) return;
    uint64_t now = (uint64_t)esp_timer_get_time()/1000;
    bool online = pet_control_online(view->mode, view->received_ms, now);
    s_control_seen |= view->mode != 0;
    s_control_online = online;
    lv_label_set_text(s_link, online ? "已连接" : "已断开");
    lv_obj_set_style_text_color(s_link, lv_color_hex(online ? 0x91DEBE : 0x7D8A9E), 0);
    lv_obj_align(s_link, LV_ALIGN_TOP_LEFT, 85, 11);
    bool expanded = online && visible;
    s_control_visible = expanded;
    sync_dots(s_frame);
    if (online && !expanded && view->has_home) { home_show(&view->home); return; }
    home_hide();
    lv_image_set_scale(s_pet, 256);
    lv_obj_set_pos(s_pet, 48, 54);
    hidden(s_footer, false);
    lv_obj_t *objects[] = {s_pet, s_status, s_detail};
    for (unsigned i = 0; i < 3; ++i) {
        if (expanded) lv_obj_add_flag(objects[i], LV_OBJ_FLAG_HIDDEN);
        else lv_obj_remove_flag(objects[i], LV_OBJ_FLAG_HIDDEN);
    }
    if (!expanded) {
        fallback_show(pet_fallback_status(s_heartbeat_state, s_control_seen, online));
        lv_obj_set_style_text_font(s_footer, &passport_font_12, 0);
        lv_obj_align(s_footer, LV_ALIGN_TOP_MID, 0, PET_CONTROL_FOOTER_TOP);
        lv_label_set_text(s_footer, online ? "按键查看会话\n长按下键：配网" : "长按下键：配网");
        return;
    }
    if (pet_control_busy(view->mode)) {
        lv_obj_add_flag(s_panel, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(s_status, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_status, view->mode == PET_CONTROL_SENDING ? "正在发送" :
                                  view->mode == PET_CONTROL_STARTING ? "正在启动语音输入" :
                                  view->mode == 10 ? "电脑语音输入" : "正在结束");
        lv_obj_align(s_status, LV_ALIGN_TOP_MID, 0, 160);
    } else {
        s_panel_image.header.h = pet_control_panel_height(view->mode);
        unsigned pixel_bytes = PET_CONTROL_WIDTH * s_panel_image.header.h / 8;
        memcpy(s_panel_data+8, view->pixels, pixel_bytes);
        s_panel_image.data_size = 8 + pixel_bytes;
        lv_image_cache_drop(&s_panel_image);
        lv_image_header_cache_drop(&s_panel_image);
        lv_image_set_src(s_panel, &s_panel_image);
        lv_obj_remove_flag(s_panel, LV_OBJ_FLAG_HIDDEN);
        lv_obj_align(s_panel, LV_ALIGN_TOP_MID, 0, pet_control_panel_top(view->mode));
        if (!expanded) lv_obj_add_flag(s_detail, LV_OBJ_FLAG_HIDDEN);
    }
    const char *footers[13] = {
        [1] = "确认键：发送；长按：语音\n长按上键：项目；下键：宠物",
        [3] = "确认键：允许；上键：翻页\n下键：拒绝；长按确认键：语音",
        [4] = "按任意键关闭提示", [6] = "正在结束电脑语音输入",
        [7] = "确认键：会话\n长按下键：宠物",
        [10] = "电脑麦克风正在录音\n松开确认键插入文字",
        [PET_CONTROL_STARTING] = "正在启动电脑语音输入\n请等待麦克风就绪",
        [PET_CONTROL_SENDING] = "正在通过 Codex 发送\n请稍候",
    };
    lv_obj_set_style_text_font(s_footer, &passport_font_12, 0);
    lv_obj_set_style_text_align(s_footer, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(s_footer, LV_ALIGN_TOP_MID, 0, PET_CONTROL_FOOTER_TOP);
    lv_label_set_text(s_footer, view->mode <= PET_CONTROL_SENDING && footers[view->mode] ? footers[view->mode] : "");
}
