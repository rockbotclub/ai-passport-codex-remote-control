#include "pet_packet.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static bool decode(const char *body, uint64_t last, pet_packet_t *result) {
    char packet[200];
    int length = snprintf(packet, sizeof(packet), "CPW1 %064d %s", 0, body);
    return pet_packet_decode(packet, (size_t)length, last, 10, result);
}
int main(void) {
    pet_packet_t result;
    assert(decode("123 CP1 working 2 0\n", 122, &result));
    assert(result.sequence == 123 && result.next_state.active == 2);
    assert(!decode("123 CP1 working 2 0\n", 123, &result));
    assert(!decode("122 CP1 working 2 0\n", 123, &result));
    assert(!decode("0 CP1 idle 0 0\n", 0, &result));
    assert(!decode("-1 CP1 idle 0 0\n", 0, &result));
    assert(!decode("18446744073709551616 CP1 idle 0 0\n", 0, &result));
    assert(decode("18446744073709551615 CP1 idle 0 0\n", 0, &result));
    assert(!decode("1 CP1 waiting 1 2\n", 0, &result));
    assert(!decode("1 CP1 idle 0 0\nCP1 done 0 0\n", 0, &result));
    assert(!decode("1 CP1 idle 0 0", 0, &result));
    char malformed[100]; memset(malformed, 'x', sizeof(malformed));
    assert(!pet_packet_decode(malformed, sizeof(malformed), 0, 0, &result));
    puts("Codex pet wireless envelope/replay tests: PASS");
}
