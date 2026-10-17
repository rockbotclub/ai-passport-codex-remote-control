#!/usr/bin/env bash
set -euo pipefail

mode="${1:---all}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    echo "Usage: $0 [--all|--static|--firmware]" >&2
}

run_static_checks() {
    local actionlint_bin
    local test_dir
    local gc_sections_flag="-Wl,--gc-sections"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        gc_sections_flag="-Wl,-dead_strip"
    fi

    python3 tools/check_repo.py

    actionlint_bin="${ACTIONLINT_BIN:-}"
    if [[ -z "${actionlint_bin}" ]]; then
        actionlint_bin="$(command -v actionlint || true)"
    fi
    if [[ -z "${actionlint_bin}" || ! -x "${actionlint_bin}" ]]; then
        actionlint_bin="$(./tools/install-actionlint.sh)"
    fi
    "${actionlint_bin}" -color .github/workflows/*.yml

    test_dir="$(mktemp -d /tmp/ai-passport-host-tests.XXXXXX)"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_pet_state.c main/pet_state.c -o "${test_dir}/test_pet_state"
    "${test_dir}/test_pet_state"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_pet_packet.c main/pet_packet.c main/pet_state.c -o "${test_dir}/test_pet_packet"
    "${test_dir}/test_pet_packet"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_pet_provision.c main/pet_provision.c -o "${test_dir}/test_pet_provision"
    "${test_dir}/test_pet_provision"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I main tests/test_pet_button_policy.c main/pet_button_policy.c -o "${test_dir}/test_pet_button_policy"
    "${test_dir}/test_pet_button_policy"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_pet_home.c main/pet_home.c -o "${test_dir}/test_pet_home"
    "${test_dir}/test_pet_home"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_pet_control_layout.c -o "${test_dir}/test_pet_control_layout"
    "${test_dir}/test_pet_control_layout"
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_status_sync.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_bridge.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_interaction.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_native_dictation.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_doubao_dictation.py
    if [[ "$(uname -s)" == "Darwin" ]]; then
        /usr/bin/clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
            -framework ApplicationServices tools/codex_pet/composer_action.m \
            -o "${test_dir}/composer-action"
        /usr/bin/clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
            -framework ApplicationServices tests/test_composer_action.m \
            -o "${test_dir}/test-composer-action"
        "${test_dir}/test-composer-action"
        /usr/bin/clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
            -framework ApplicationServices -framework Carbon tools/codex_pet/doubao_dictation.m \
            -o "${test_dir}/doubao-dictation"
        /usr/bin/clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
            -framework ApplicationServices -framework Carbon tests/test_doubao_dictation.m \
            -o "${test_dir}/test-doubao-dictation"
        "${test_dir}/test-doubao-dictation"
    fi
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_dashboard.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_codex_pet_chinese.py
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_ui_pixel_math.c main/ui_pixel_math.c \
        -o "${test_dir}/test_ui_pixel_math"
    "${test_dir}/test_ui_pixel_math"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_demo_navigation.c main/demo_navigation.c \
        -o "${test_dir}/test_demo_navigation"
    "${test_dir}/test_demo_navigation"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Imain \
        tests/test_key_guard.c -o "${test_dir}/test_key_guard"
    "${test_dir}/test_key_guard"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Icomponents/bsp/src \
        tests/test_bsp_display_rounding.c components/bsp/src/bsp_display_rounding.c \
        -o "${test_dir}/test_bsp_display_rounding"
    "${test_dir}/test_bsp_display_rounding"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Icomponents/bsp/src \
        tests/test_bsp_es8311_sleep_check.c components/bsp/src/bsp_es8311_sleep_check.c \
        -o "${test_dir}/test_bsp_es8311_sleep_check"
    "${test_dir}/test_bsp_es8311_sleep_check"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
        -Itests/bsp_stubs -Icomponents/bsp/include \
        tests/test_bsp_button.c -o "${test_dir}/test_bsp_button"
    "${test_dir}/test_bsp_button"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
        -Itests/bsp_stubs -Icomponents/bsp/include \
        tests/test_bsp_lvgl_init.c components/bsp/src/bsp_display_rounding.c \
        -o "${test_dir}/test_bsp_lvgl_init"
    "${test_dir}/test_bsp_lvgl_init"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
        -Itests/audio_stubs -Icomponents/bsp/include -Icomponents/bsp/src \
        tests/test_bsp_audio_recovery.c components/bsp/src/bsp_es8311_sleep_check.c \
        -o "${test_dir}/test_bsp_audio_recovery"
    "${test_dir}/test_bsp_audio_recovery"
    for demo in audio low_power ble wifi; do
        "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
            -ffunction-sections -fdata-sections -Itests/demo_stubs -Imain \
            "tests/test_demo_${demo}_runtime.c" "${gc_sections_flag}" \
            -o "${test_dir}/test_demo_${demo}_runtime"
        "${test_dir}/test_demo_${demo}_runtime"
    done
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_deep_sleep_contract.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_key_wake_contract.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_check_repo.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_verify_firmware.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_archive_firmware.py
    PYTHONDONTWRITEBYTECODE=1 python3 tests/test_install_passport_skills.py
    rm -rf "${test_dir}"
    echo "Host tests: PASS"
}

run_firmware_checks() (
    local validation_build_dir

    if ! command -v idf.py >/dev/null 2>&1; then
        echo "ERROR: idf.py is not available; activate ESP-IDF 5.5.3 first." >&2
        return 1
    fi

    validation_build_dir="$(mktemp -d /tmp/ai-passport-firmware.XXXXXX)"
    trap 'case "${validation_build_dir}" in /tmp/ai-passport-firmware.*) rm -rf -- "${validation_build_dir}" ;; esac' EXIT

    SDKCONFIG_DEFAULTS="${repo_root}/sdkconfig.defaults" \
        idf.py -B "${validation_build_dir}" \
        -D "SDKCONFIG=${validation_build_dir}/sdkconfig" build
    idf.py -B "${validation_build_dir}" merge-bin \
        -o "${validation_build_dir}/FoloToy-AI-Passport-full.bin"
    python3 tools/verify_firmware.py "${validation_build_dir}"
    PYTHONDONTWRITEBYTECODE=1 python3 tools/archive_firmware.py create \
        "${validation_build_dir}" --archive-root "${repo_root}/build/firmware"
    mkdir -p "${repo_root}/build"
    install -m 0644 \
        "${validation_build_dir}/FoloToy-AI-Passport-full.bin" \
        "${repo_root}/build/FoloToy-AI-Passport-full.bin"
    echo "Firmware build: PASS"
)

cd "${repo_root}"
case "${mode}" in
    --all)
        run_static_checks
        run_firmware_checks
        ;;
    --static)
        run_static_checks
        ;;
    --firmware)
        run_firmware_checks
        ;;
    *)
        usage
        exit 2
        ;;
esac
