if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assets/images/codex-pet/frames.inc" OR
   NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assets/images/codex-pet/offline.inc" OR
   NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assets/images/codex-pet/syncing.inc")
    message(FATAL_ERROR "请先使用 tools/codex_pet/prepare_sprites.py 导入本地 Codex 宠物；详见 docs/codex-pet.zh_CN.md")
endif()
idf_component_register(
    SRCS "main.c" "pet_state.c" "pet_ui.c" "pet_network.c" "pet_provision.c" "pet_packet.c" "pet_control.c" "pet_button_policy.c" "pet_home.c"
    EMBED_TXTFILES "pet_setup_page.html" "../assets/fonts/passport-ui-glyphs.txt"
    INCLUDE_DIRS "."
    REQUIRES bsp esp_timer esp_hw_support vfs esp_wifi esp_event esp_netif esp_http_server nvs_flash json mbedtls bootloader_support
)
target_sources(${COMPONENT_LIB} PRIVATE
    "../assets/fonts/passport_font_12.c"
    "../assets/fonts/passport_font_14.c"
    "../assets/fonts/passport_font_20.c"
)
