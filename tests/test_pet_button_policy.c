#include "pet_button_policy.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    pet_navigation_t nav = {0};
    pet_navigation_update(&nav, 7, true, 0, 100);
    assert(!nav.visible); // Heartbeats never open the list.
    pet_navigation_open(&nav, 0, 200);
    pet_navigation_update(&nav, 1, true, 0, 300);
    assert(nav.visible && nav.opening); // Sync is not a wake acknowledgement.
    pet_navigation_update(&nav, 1, true, 1, 400);
    assert(nav.visible && !nav.opening);
    pet_navigation_update(&nav, 3, true, 1, 10199);
    assert(nav.visible);
    pet_navigation_update(&nav, 3, true, 1, 10200);
    assert(!nav.visible); // Approval/status updates do not reset inactivity.
    pet_navigation_open(&nav, 1, 11000);
    pet_navigation_update(&nav, 1, true, 2, 11001);
    pet_navigation_activity(&nav, 20000);
    pet_navigation_update(&nav, 7, true, 2, 29999);
    assert(nav.visible);
    pet_navigation_update(&nav, 7, true, 2, 30000);
    assert(!nav.visible);
    pet_navigation_update(&nav, 5, false, 2, 31000);
    pet_navigation_update(&nav, 6, false, 2, 61000);
    assert(nav.visible); // A long capture/transcription stays on screen.
    pet_navigation_update(&nav, 2, true, 2, 70999);
    assert(nav.visible);
    pet_navigation_update(&nav, 2, true, 2, 71000);
    assert(!nav.visible);
    pet_navigation_open(&nav, 2, 72000);
    pet_navigation_update(&nav, 0, false, 2, 72001);
    assert(!nav.visible && !nav.opening);
    pet_navigation_open(&nav, 2, 73000);
    pet_navigation_update(&nav, 1, false, 2, 73001);
    assert(!nav.visible && !nav.opening);
    assert(pet_button_action(1,true,0,1)==PET_ACTION_UP);
    assert(pet_button_action(1,true,1,1)==PET_ACTION_DOWN);
    assert(pet_button_action(1,true,2,3)==PET_ACTION_RECORD);
    assert(pet_button_action(1,true,0,3)==PET_ACTION_BACK);
    assert(pet_button_action(7,true,0,1)==PET_ACTION_UP);
    assert(pet_button_action(7,true,1,1)==PET_ACTION_DOWN);
    assert(pet_button_action(7,true,2,1)==PET_ACTION_OK);
    assert(pet_button_action(7,true,0,3)==PET_ACTION_NEW);
    assert(pet_button_action(7,true,2,3)==PET_ACTION_CONSUME);
    assert(pet_button_action(7,false,0,3)==PET_ACTION_CONSUME);
    assert(pet_button_action(7,false,2,1)==PET_ACTION_CONSUME);
    assert(pet_button_action(7,true,0,2)==PET_ACTION_NONE);
    for (unsigned mode=2;mode<=3;++mode) {
        assert(pet_button_action(mode,true,2,1)==PET_ACTION_OK);
        assert(pet_button_action(mode,true,2,3)==PET_ACTION_RECORD);
        assert(pet_button_action(mode,false,2,1)==PET_ACTION_CONSUME);
        assert(pet_button_action(mode,true,1,3)==PET_ACTION_CANCEL);
        assert(pet_button_action(mode,true,0,3)==PET_ACTION_BACK);
    }
    for (unsigned mode=5;mode<=6;++mode)
        for (unsigned key=0;key<3;++key)
            for (unsigned event=0;event<5;++event)
                assert(pet_button_action(mode,true,key,event)==PET_ACTION_CONSUME);
    assert(pet_button_action(0,true,1,3)==PET_ACTION_SETUP);
    assert(pet_button_action(1,true,1,3)==PET_ACTION_HOME);
    assert(pet_button_action(7,true,1,3)==PET_ACTION_HOME);
    for (unsigned mode = 1; mode <= 7; mode += 6) {
        pet_navigation_open(&nav, 9, 74000);
        assert(!pet_navigation_input(&nav, mode, true, 1, 0)); // Press alone cannot return.
        assert(!pet_navigation_input(&nav, mode, true, 1, 1)); // Click still selects.
        assert(nav.visible && nav.opening);
        assert(pet_navigation_input(&nav, mode, false, 1, 3)); // Local exit also works while opening/stale.
        assert(!nav.visible && !nav.opening && nav.opened == 9);
        pet_navigation_update(&nav, mode, true, 10, 74001);
        assert(!nav.visible); // A late wake reply or heartbeat cannot reopen it.
        assert(!pet_navigation_input(&nav, mode, true, 1, 4));
        assert(!pet_navigation_input(&nav, mode, true, 1, 3));
        pet_navigation_open(&nav, 10, 75000);
        pet_navigation_update(&nav, mode, true, 11, 75001);
        assert(nav.visible && !nav.opening); // A later explicit wake still works.
        assert(pet_navigation_input(&nav, mode, true, 1, 3));
    }
    for (unsigned mode=4;mode<=8;mode+=4) {
        assert(pet_button_action(mode,true,0,3)==PET_ACTION_BACK);
        assert(pet_button_action(mode,false,0,3)==PET_ACTION_CONSUME);
        assert(pet_button_action(mode,true,2,1)==(mode==4 ? PET_ACTION_CANCEL : PET_ACTION_CONSUME));
        assert(pet_button_action(mode,true,1,3)==PET_ACTION_CANCEL);
    }
    // Empty speech/transcription errors must not trap ordinary button clicks.
    for (unsigned key=0;key<3;++key) {
        assert(pet_button_action(4,true,key,1)==PET_ACTION_CANCEL);
        assert(pet_button_action(4,false,key,1)==PET_ACTION_CONSUME);
    }
    assert(pet_button_action(4,true,2,3)==PET_ACTION_CONSUME);
    assert(pet_button_action(0,true,2,1)==PET_ACTION_PLAY);
    assert(pet_button_action(9,true,2,1)==PET_ACTION_NONE);
    puts("Pet button policy: PASS");
}
