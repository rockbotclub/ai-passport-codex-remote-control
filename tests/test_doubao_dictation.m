// Synthetic controls/key events only; never touches a real app or keyboard.
#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#include <assert.h>

static NSMutableArray *posted;
static BOOL allocationFails;
static CGEventRef fakeCreate(CGEventSourceRef source, CGKeyCode key, bool down) {
    (void)source;
    if (allocationFails) return NULL;
    return (CGEventRef)CFBridgingRetain([@{@"key": @(key), @"down": @(down)} mutableCopy]);
}
static void fakeType(CGEventRef event, CGEventType type) {
    ((__bridge NSMutableDictionary *)event)[@"type"] = @(type);
}
static void fakeFlags(CGEventRef event, CGEventFlags flags) {
    ((__bridge NSMutableDictionary *)event)[@"flags"] = @(flags);
}
static void fakePost(CGEventTapLocation location, CGEventRef event) {
    assert(location == kCGHIDEventTap);
    [posted addObject:[(__bridge NSDictionary *)event copy]];
}
static AXError fakeRead(AXUIElementRef element, CFStringRef name, CFTypeRef *value) {
    assert(!CFEqual(name, kAXValueAttribute));
    id found = ((__bridge NSDictionary *)element)[(__bridge NSString *)name];
    if (!found) return kAXErrorNoValue;
    *value = CFBridgingRetain(found);
    return kAXErrorSuccess;
}

#define DOUBAO_TEST
#define CGEventCreateKeyboardEvent fakeCreate
#define CGEventSetType fakeType
#define CGEventSetFlags fakeFlags
#define CGEventPost fakePost
#define AXUIElementCopyAttributeValue fakeRead
#include "../tools/codex_pet/doubao_dictation.m"

int main(void) {
    @autoreleasepool {
        (void)holdDoubao;
        (void)interruptHold;
        posted = [NSMutableArray array];
        assert(postHoldKey(NULL, YES));
        assert(postHoldKey(NULL, NO));
        assert(posted.count == 2);
        assert([posted[0][@"key"] isEqual:@59] && [posted[1][@"key"] isEqual:@59]);
        assert([posted[0][@"type"] unsignedIntValue] == kCGEventFlagsChanged);
        assert([posted[1][@"type"] unsignedIntValue] == kCGEventFlagsChanged);
        assert([posted[0][@"flags"] unsignedLongLongValue] == kCGEventFlagMaskControl);
        assert([posted[1][@"flags"] unsignedLongLongValue] == 0);
        allocationFails = YES;
        assert(!postHoldKey(NULL, YES));
        assert(posted.count == 2);
        id candidates = @{@"AXChildren": @[@{@"AXIdentifier": @"CandidatesPanelView.candidate.0"}]};
        assert(candidateWindow(candidates));
        assert(candidateWindow(@{@"AXDescription": @"候选词面板"}));
        assert(!candidateWindow(@{@"AXChildren": @[@{@"AXRole": @"AXButton", @"AXDescription": @"结束"}]}));
        puts("Doubao left-Control dispatch and manual-panel isolation: PASS");
    }
}
