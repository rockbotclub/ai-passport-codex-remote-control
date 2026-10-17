// One bounded left-Control hold. Reuses the selected-chat/composer checks; never reads text.
#define main unusedComposerEntry
#include "composer_action.m"
#undef main
#import <Carbon/Carbon.h>
#include <poll.h>
#include <signal.h>

static volatile sig_atomic_t interrupted;
static void interruptHold(int signalNumber) { (void)signalNumber; interrupted = 1; }

static BOOL doubaoInputSelected(void) {
    TISInputSourceRef source = TISCopyCurrentKeyboardInputSource();
    if (!source) return NO;
    NSString *identity = (__bridge NSString *)TISGetInputSourceProperty(source, kTISPropertyInputSourceID);
    BOOL selected = [identity isEqual:@"com.bytedance.inputmethod.doubaoime.pinyin"];
    CFRelease(source);
    return selected;
}

static BOOL postHoldKey(CGEventSourceRef source, BOOL held) {
    CGEventRef event = CGEventCreateKeyboardEvent(source, 59, held);
    if (!event) return NO;
    CGEventSetType(event, kCGEventFlagsChanged);
    CGEventSetFlags(event, held ? kCGEventFlagMaskControl : 0);
    CGEventPost(kCGHIDEventTap, event);
    CFRelease(event);
    return YES;
}

static BOOL candidateWindow(id window) {
    NSMutableArray *pending = [NSMutableArray arrayWithObject:window];
    BOOL candidate = NO;
    for (NSUInteger visited = 0; pending.count && visited < 2000; visited++) {
        id node = pending.lastObject;
        [pending removeLastObject];
        NSString *identifier = attribute(node, kAXIdentifierAttribute);
        if ([identifier hasPrefix:@"CandidatesPanelView."]) candidate = YES;
        if ([attribute(node, kAXDescriptionAttribute) isEqual:@"候选词面板"] ||
                [attribute(node, kAXTitleAttribute) isEqual:@"候选词面板"]) candidate = YES;
        id children = attribute(node, kAXChildrenAttribute);
        if ([children isKindOfClass:NSArray.class]) [pending addObjectsFromArray:children];
    }
    return candidate && !pending.count;
}

static int doubaoIdleStatus(void) {
    NSArray *apps = [NSRunningApplication runningApplicationsWithBundleIdentifier:@"com.bytedance.inputmethod.doubaoime"];
    if (apps.count != 1) return 40;
    id app = CFBridgingRelease(AXUIElementCreateApplication([apps[0] processIdentifier]));
    AXUIElementSetMessagingTimeout((__bridge AXUIElementRef)app, 0.3);
    id windows = attribute(app, kAXWindowsAttribute);
    if (![windows isKindOfClass:NSArray.class]) return 48;
    // Known candidate panels are harmless. Any other existing panel may own a
    // manual voice capture; refuse to start or later release that user's session.
    for (id window in windows)
        if (![attribute(window, kAXHiddenAttribute) isEqual:@YES] && !candidateWindow(window)) return 25;
    return 0;
}

static BOOL sameFocus(id app, id editor, pid_t pid) {
    if (NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier != pid) return NO;
    id current = attribute(app, kAXFocusedUIElementAttribute);
    return current && CFEqual((__bridge CFTypeRef)current, (__bridge CFTypeRef)editor);
}

static int holdDoubao(NSString *thread) {
    if (!AXIsProcessTrusted()) return 10;
    if ([NSRunningApplication runningApplicationsWithBundleIdentifier:@"com.bytedance.inputmethod.doubaoime"].count != 1)
        return 40;
    if (!doubaoInputSelected()) return 41;
    int idleStatus = doubaoIdleStatus();
    if (idleStatus) return idleStatus;
    CGEventFlags modifiers = kCGEventFlagMaskShift | kCGEventFlagMaskControl |
        kCGEventFlagMaskAlternate | kCGEventFlagMaskCommand | kCGEventFlagMaskSecondaryFn;
    if (CGEventSourceFlagsState(kCGEventSourceStateCombinedSessionState) & modifiers) return 42;
    NSArray *apps = [NSRunningApplication runningApplicationsWithBundleIdentifier:@"com.openai.codex"];
    if (apps.count != 1) return 11;
    pid_t pid = [apps[0] processIdentifier];
    if (NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier != pid) return 43;
    int result = composerAction(thread, @"focus");
    if (result) return result;
    id app = CFBridgingRelease(AXUIElementCreateApplication(pid));
    AXUIElementSetMessagingTimeout((__bridge AXUIElementRef)app, 0.3);
    id editor = attribute(app, kAXFocusedUIElementAttribute);
    if (!editor || !sameFocus(app, editor, pid)) return 30;
    NSArray *areas = chatAreas(applicationRoots(app, [NSMutableDictionary dictionary]), thread);
    if (areas.count != 1) return 24;
    CGEventSourceRef source = CGEventSourceCreate(kCGEventSourceStatePrivate);
    if (!source) return 44;
    // Every normal/EOF/signal/timeout path releases exactly this helper's hold.
    BOOL held = postHoldKey(source, YES);
    result = held ? 0 : 44;
    if (held) {
        // Wait for a new Doubao panel after our own key-down. Do not report a
        // successful start merely because the OS accepted a synthetic key.
        CFAbsoluteTime readyDeadline = CFAbsoluteTimeGetCurrent() + 2.5;
        BOOL panelOpened = NO;
        while (!interrupted && CFAbsoluteTimeGetCurrent() < readyDeadline) {
            int status = doubaoIdleStatus();
            if (status == 25) { panelOpened = YES; break; }
            if (status || !sameFocus(app, editor, pid)) break;
            usleep(100000);
        }
        if (!panelOpened) result = 49;
        else { fputs("held\n", stdout); fflush(stdout); }
        CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 33;
        CFAbsoluteTime nextCheck = 0;
        while (panelOpened && !interrupted) {
            struct pollfd input = {.fd = STDIN_FILENO, .events = POLLIN};
            int available = poll(&input, 1, 100);
            if (available > 0 && input.revents) {
                char command[16] = {0};
                ssize_t size = read(STDIN_FILENO, command, sizeof(command));
                result = size == 5 && !memcmp(command, "stop\n", 5) ? 0 : 45;
                break;
            }
            if (available < 0 && !interrupted) { result = 45; break; }
            CFAbsoluteTime now = CFAbsoluteTimeGetCurrent();
            if (now >= deadline) { result = 46; break; }
            if (now >= nextCheck) {
                if (!sameFocus(app, editor, pid) || !doubaoInputSelected() ||
                        chatAreas(@[areas[0]], thread).count != 1) { result = 47; break; }
                nextCheck = now + 0.5;
            }
        }
        if (interrupted) result = 45;
        if (!postHoldKey(source, NO)) result = 44;
        // A normal release waits for the voice panel to close before enabling
        // card Send. Never inspect the transcript or click the panel's buttons.
        if (!result) {
            CFAbsoluteTime insertDeadline = CFAbsoluteTimeGetCurrent() + 2;
            int status;
            do {
                usleep(100000);
                status = doubaoIdleStatus();
            } while (status == 25 && CFAbsoluteTimeGetCurrent() < insertDeadline);
            if (status) result = 50;
        }
        fputs("released\n", stdout); fflush(stdout);
    }
    CFRelease(source);
    return result;
}

#ifndef DOUBAO_TEST
int main(void) {
    @autoreleasepool {
        signal(SIGTERM, interruptHold);
        signal(SIGINT, interruptHold);
        signal(SIGPIPE, SIG_IGN); // A closed bridge pipe must still release Control.
        // Read a bounded first line without buffering the later release command.
        NSMutableData *data = [NSMutableData data];
        char byte;
        while (data.length < 8192 && read(STDIN_FILENO, &byte, 1) == 1 && byte != '\n')
            [data appendBytes:&byte length:1];
        id request = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        if (![request isKindOfClass:NSDictionary.class] ||
                ![request[@"thread"] isKindOfClass:NSString.class] || ![request[@"thread"] length]) return 21;
        id title = request[@"title"];
        if (title && (![title isKindOfClass:NSString.class] || ![title length])) return 21;
        id project = request[@"draftProject"];
        if (project && (![project isKindOfClass:NSString.class] || ![project length] ||
                ![request[@"thread"] hasPrefix:@"@new:"])) return 21;
        draftProject = project;
        sidebarTitles = title ? @{request[@"thread"]: title} : nil;
        return holdDoubao(request[@"thread"]);
    }
}
#endif
