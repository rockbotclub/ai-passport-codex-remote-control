#include "pet_control_layout.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    assert(PET_CONTROL_WIDTH % 8 == 0);
    assert(17 + PET_CONTROL_PIXELS + 16 <= 6144);
    const uint8_t modes[] = {1, 3, 4, 6, 7, 10};
    for (unsigned i = 0; i < sizeof(modes); ++i) {
        uint8_t mode = modes[i];
        unsigned top = pet_control_panel_top(mode);
        unsigned height = pet_control_panel_height(mode);
        assert(top > 33);
        assert(top + height <= PET_CONTROL_FOOTER_TOP);
        assert(height <= PET_CONTROL_HEIGHT);
        if (mode == 1 || mode == 7) {
            // Five title/metadata pairs plus one wrapped title line.
            assert(height >= (5 * 2 + 1) * 20);
            assert(PET_CONTROL_FOOTER_TOP - top - height >= 8);
        } else {
            // The larger wire bitmap must not move or enlarge review pages.
            assert(top == 85 && height == 192);
        }
    }
    assert(PET_CONTROL_FOOTER_TOP + 28 <= 320);
    puts("Pet control layout tests: PASS");
    return 0;
}
