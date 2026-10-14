if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assets/images/codex-pet/frames.inc" OR
   NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assets/images/codex-pet/offline.inc")
    message(FATAL_ERROR "Import your local Codex pet first with tools/codex_pet/prepare_sprites.py; see docs/codex-pet.md")
endif()
idf_component_register(
    SRCS "main.c" "pet_state.c" "pet_ui.c" "pet_network.c" "pet_provision.c" "pet_packet.c" "pet_control.c" "pet_button_policy.c" "pet_home.c"
    EMBED_TXTFILES "pet_setup_page.html"
    INCLUDE_DIRS "."
    REQUIRES bsp esp_timer esp_hw_support vfs esp_wifi esp_event esp_netif esp_http_server nvs_flash json mbedtls bootloader_support
)
