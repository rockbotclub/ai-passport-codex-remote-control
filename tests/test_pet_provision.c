#include "pet_provision.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    assert(pet_provision_can_request(PET_SETUP_IDLE));
    assert(pet_provision_can_request(PET_SETUP_FAILED));
    assert(!pet_provision_can_request(PET_SETUP_CONNECTING));
    assert(!pet_provision_can_request(PET_SETUP_SAVED));
    assert(pet_provision_decide(2000, 0, true, true) == PET_SETUP_WAIT); // Queued, not started.
    assert(pet_provision_decide(24999, 25000, false, false) == PET_SETUP_WAIT);
    assert(pet_provision_decide(25000, 25000, false, false) == PET_SETUP_RETRY);
    assert(pet_provision_decide(25001, 25000, false, false) == PET_SETUP_RETRY);
    assert(pet_provision_decide(1, 25000, false, true) == PET_SETUP_RETRY);
    assert(pet_provision_decide(25000, 25000, true, false) == PET_SETUP_SAVE);
    assert(pet_provision_decide(25000, 25000, true, true) == PET_SETUP_SAVE);
    char qr[PET_SETUP_QR_CAPACITY];
    assert(pet_provision_qr(qr, sizeof(qr), "Test-AP", "test-only-password"));
    assert(strcmp(qr, "WIFI:T:WPA;S:Test-AP;P:test-only-password;;") == 0);
    assert(pet_provision_qr(qr, sizeof(qr), "a;,:\\\"", "12345678"));
    assert(strcmp(qr, "WIFI:T:WPA;S:a\\;\\,\\:\\\\\\\";P:12345678;;") == 0);
    assert(pet_provision_qr(qr, sizeof(qr), "测试", "12345678"));
    assert(!pet_provision_qr(qr, 10, "Test-AP", "12345678") && !qr[0]);
    assert(!pet_provision_qr(qr, sizeof(qr), "bad\nname", "12345678") && !qr[0]);
    assert(!pet_provision_qr(qr, sizeof(qr), "", "12345678"));
    assert(!pet_provision_qr(qr, sizeof(qr), "Test-AP", "short"));
    char ssid[33], password[64];
    memset(ssid, ';', 32); ssid[32] = 0;
    memset(password, '\\', 63); password[63] = 0;
    assert(pet_provision_qr(qr, sizeof(qr), ssid, password));

    uint8_t query[] = {0x12,0x34,1,0,0,1,0,0,0,0,0,0,3,'w','w','w',4,'t','e','s','t',0,0,1,0,1};
    uint8_t reply[512], ip[] = {192,168,4,1};
    size_t n = pet_provision_dns(query, sizeof(query), reply, sizeof(reply), ip);
    assert(n == sizeof(query) + 16 && reply[0] == 0x12 && reply[1] == 0x34);
    assert(reply[2] == 0x85 && reply[7] == 1 && reply[11] == 0);
    assert(memcmp(reply + n - 4, ip, 4) == 0);
    assert(memcmp(reply + 12, query + 12, sizeof(query) - 12) == 0);
    assert(!pet_provision_dns(query, sizeof(query), reply, n-1, ip));
    for (size_t size = 0; size < sizeof(query); ++size)
        assert(!pet_provision_dns(query, size, reply, sizeof(reply), ip));
    query[23] = 28; // AAAA: valid empty response, never forge an IPv6 answer.
    assert(pet_provision_dns(query, sizeof(query), reply, sizeof(reply), ip) == sizeof(query));
    assert(reply[7] == 0);
    query[12] = 0xc0; // Compression/pointer loops are rejected.
    assert(!pet_provision_dns(query, sizeof(query), reply, sizeof(reply), ip));
    query[12] = 3; query[5] = 2;
    assert(!pet_provision_dns(query, sizeof(query), reply, sizeof(reply), ip));
    query[5] = 1; query[2] = 0x81;
    assert(!pet_provision_dns(query, sizeof(query), reply, sizeof(reply), ip));
    puts("Pet provisioning QR/DNS: PASS");
}
