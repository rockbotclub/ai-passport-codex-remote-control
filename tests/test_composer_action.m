// Synthetic accessibility trees only: never reads or changes an application.
#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#include <assert.h>
#include <unistd.h>

static BOOL dictating = NO;
static NSUInteger attributeReads = 0;
static NSUInteger singleReads = 0, batchReads = 0;
static BOOL readingBatch = NO;
static AXError batchResult = kAXErrorSuccess;
static BOOL actionLabelChanged = NO;
static id focusedEditor = nil;
static BOOL focusDenied = NO;

static AXError fakeAttribute(AXUIElementRef element, CFStringRef name, CFTypeRef *value) {
    attributeReads++;
    if (!readingBatch) singleReads++;
    assert(!CFEqual(name, kAXValueAttribute)); // No prompt/transcript contents.
    NSDictionary *node = (__bridge NSDictionary *)element;
    if (CFEqual(name, kAXFocusedAttribute) && focusedEditor == (__bridge id)element) {
        *value = CFBridgingRetain(@YES);
        return kAXErrorSuccess;
    }
    if (actionLabelChanged && node[@"changedLabelOnActionRead"] &&
            (CFEqual(name, kAXTitleAttribute) || CFEqual(name, kAXDescriptionAttribute))) {
        *value = CFBridgingRetain(@"Stop dictation");
        return kAXErrorSuccess;
    }
    if (dictating && CFEqual(name, kAXChildrenAttribute) && node[@"recordingChildrenError"])
        return [node[@"recordingChildrenError"] intValue];
    if (CFEqual(name, kAXChildrenAttribute) && node[@"childrenError"])
        return [node[@"childrenError"] intValue];
    id result = (dictating && CFEqual(name, kAXChildrenAttribute) && node[@"recordingChildren"]) ?
        node[@"recordingChildren"] : node[(__bridge NSString *)name];
    if (!result) return kAXErrorNoValue;
    *value = CFBridgingRetain(result);
    return kAXErrorSuccess;
}

static AXError fakeMultipleAttributes(AXUIElementRef element, CFArrayRef names,
        AXCopyMultipleAttributeOptions options, CFArrayRef *values) {
    assert(options == 0);
    batchReads++;
    if (batchResult != kAXErrorSuccess) return batchResult;
    NSMutableArray *found = [NSMutableArray array];
    readingBatch = YES;
    for (NSString *name in (__bridge NSArray *)names) {
        CFTypeRef raw = NULL;
        AXError error = fakeAttribute(element, (__bridge CFStringRef)name, &raw);
        if (error == kAXErrorSuccess) [found addObject:CFBridgingRelease(raw)];
        else [found addObject:CFBridgingRelease(AXValueCreate(kAXValueAXErrorType, &error))];
    }
    readingBatch = NO;
    *values = CFBridgingRetain(found);
    return kAXErrorSuccess;
}

static NSUInteger presses = 0;
static AXError pressResult = kAXErrorSuccess;
static id pressed = nil;
static AXError manualEnableResult = kAXErrorSuccess;
static NSMutableArray *attributeWrites;

static AXError fakeSetAttribute(AXUIElementRef element, CFStringRef name, CFTypeRef value) {
    assert(CFEqual(value, kCFBooleanTrue));
    if (CFEqual(name, kAXFocusedAttribute)) {
        if (focusDenied) return kAXErrorCannotComplete;
        focusedEditor = (__bridge id)element;
        return kAXErrorSuccess;
    }
    [attributeWrites addObject:(__bridge NSString *)name];
    return CFEqual(name, CFSTR("AXManualAccessibility")) ? manualEnableResult : kAXErrorSuccess;
}

static AXError fakeSettable(AXUIElementRef element, CFStringRef name, Boolean *settable) {
    (void)name;
    *settable = [((__bridge NSDictionary *)element)[@"writable"] boolValue];
    return kAXErrorSuccess;
}

static AXError fakeActions(AXUIElementRef element, CFArrayRef *actions) {
    NSDictionary *node = (__bridge NSDictionary *)element;
    if (node[@"changedLabelOnActionRead"]) actionLabelChanged = YES;
    id values = node[@"actions"] ?: @[];
    *actions = (CFArrayRef)CFBridgingRetain(values);
    return kAXErrorSuccess;
}

static AXError fakePress(AXUIElementRef element, CFStringRef action) {
    assert(CFEqual(action, kAXPressAction));
    presses++;
    pressed = (__bridge id)element;
    NSString *label = pressed[@"AXDescription"];
    if (pressResult == kAXErrorSuccess) {
        if ([label isEqual:@"Dictate"]) dictating = YES;
        if ([label isEqual:@"Stop dictation"] || [label isEqual:@"Cancel dictation"]) dictating = NO;
    }
    return pressResult;
}

static int noSleep(useconds_t delay) { (void)delay; return 0; }

#define usleep noSleep
#define AXUIElementIsAttributeSettable fakeSettable
#define AXUIElementCopyActionNames fakeActions
#define AXUIElementPerformAction fakePress
#define AXUIElementCopyAttributeValue fakeAttribute
#define AXUIElementCopyMultipleAttributeValues fakeMultipleAttributes
#define AXUIElementSetAttributeValue fakeSetAttribute
#define main unusedNativeEntry
#include "../tools/codex_pet/composer_action.m"
#undef main
#undef AXUIElementCopyAttributeValue

static NSDictionary *threadLink(NSString *thread, NSString *current) {
    return @{@"AXRole": @"AXLink", @"AXURL": [@"app://-/local/" stringByAppendingString:thread],
             @"AXARIACurrent": current};
}

static NSDictionary *area(NSString *url, NSArray *nodes) {
    return @{@"AXRole": @"AXWebArea", @"AXURL": url, @"AXChildren": nodes};
}

static NSDictionary *group(NSArray *nodes) {
    return @{@"AXRole": @"AXGroup", @"AXChildren": nodes};
}

static NSDictionary *button(NSString *label, BOOL enabled) {
    return @{@"AXRole": @"AXButton", @"AXDescription": label,
             @"AXEnabled": @(enabled), @"actions": @[@"AXPress"]};
}

static id chat(NSArray *nodes) {
    return area(@"app://-/index.html", [@[threadLink(@"one", @"page")] arrayByAddingObjectsFromArray:nodes]);
}

int main(void) {
    @autoreleasepool {
        // The shell URL stays constant while the router switches the active chat.
        id shell = area(@"app://-/index.html", @[threadLink(@"one", @"page"), threadLink(@"two", @"false")]);
        assert(chatAreas(@[shell], @"one").count == 1);
        assert(chatAreas(@[shell], @"two").count == 0);
        assert(chatAreas(@[shell], @"absent").count == 0);
        id transcript = @{@"AXRole": @"AXStaticText"};
        for (NSUInteger depth = 0; depth < 1000; depth++) transcript = group(@[transcript]);
        id longChat = area(@"app://-/index.html", @[threadLink(@"one", @"page"), transcript]);
        attributeReads = 0;
        BOOL hasCurrent = NO;
        assert(currentThreadLink(longChat, @"one", &hasCurrent));
        assert(attributeReads < 30); // Chat identity must not scale with transcript depth.
        // The installed desktop now renders chat rows as aria-current buttons
        // without href. Accept only its sidebar class and a uniquely bound title.
        sidebarTitles = @{@"one": @"First chat"};
        id currentButton = @{@"AXRole": @"AXButton", @"AXARIACurrent": @"page",
            @"AXDescription": @"First chat", @"AXDOMClassList": @[@"group", @"sidebar-item"]};
        id buttonShell = area(@"app://-/index.html", @[currentButton]);
        assert(chatAreas(@[buttonShell], @"one").count == 1);
        assert(chatAreas(@[buttonShell], @"two").count == 0);
        id wrongButton = @{@"AXRole": @"AXButton", @"AXARIACurrent": @"page",
            @"AXDescription": @"Other chat", @"AXDOMClassList": @[@"sidebar-item"]};
        assert(chatAreas(@[area(@"app://-/local/one", @[wrongButton])], @"one").count == 0);
        id contentButton = @{@"AXRole": @"AXButton", @"AXARIACurrent": @"page",
            @"AXDescription": @"First chat"};
        assert(chatAreas(@[area(@"app://-/index.html", @[contentButton])], @"one").count == 0);
        id embedded = area(@"https://example.com", @[currentButton]);
        assert(chatAreas(@[area(@"app://-/index.html", @[embedded])], @"one").count == 0);
        sidebarTitles = nil;
        assert(chatAreas(@[buttonShell], @"one").count == 0);
        NSDictionary *counts = chatDiscoveryCounts(@[shell], @"one");
        assert([counts[@"webAreas"] isEqual:@1]);
        assert([counts[@"shellAreas"] isEqual:@1]);
        assert([counts[@"targetLinks"] isEqual:@1]);
        assert([counts[@"currentMarkers"] isEqual:@2]);
        assert([counts[@"visited"] isEqual:@3]);
        for (id value in counts.allValues) assert([value isKindOfClass:NSNumber.class]);
        // A current marker can belong to the sidebar row wrapping its link.
        id row = @{@"AXRole": @"AXGroup", @"AXARIACurrent": @"page",
                   @"AXChildren": @[threadLink(@"one", @"false")]};
        assert(chatAreas(@[area(@"app://-/index.html", @[row])], @"one").count == 1);
        // Merely seeing a target link or a selected row is insufficient.
        id selected = @{@"AXRole": @"AXGroup", @"AXSelected": @YES,
                        @"AXChildren": @[threadLink(@"one", @"false")]};
        assert(chatAreas(@[area(@"app://-/index.html", @[selected])], @"one").count == 0);
        // An embedded browser's current link cannot bind the host chat.
        id browser = area(@"https://example.com", @[threadLink(@"one", @"page")]);
        assert(chatAreas(@[area(@"app://-/index.html", @[browser])], @"one").count == 0);
        assert([chatDiscoveryCounts(@[browser], @"one")[@"targetLinks"] isEqual:@0]);
        // Query parameters from startup must not override the active route.
        id stale = area(@"app://-/index.html?initialRoute=/local/one", @[threadLink(@"two", @"page")]);
        assert(chatAreas(@[stale], @"one").count == 0);
        assert(chatAreas(@[stale], @"two").count == 1);
        id stalePath = area(@"app://-/local/one", @[threadLink(@"two", @"page")]);
        assert(chatAreas(@[stalePath], @"one").count == 0);
        assert(chatAreas(@[stalePath], @"two").count == 1);
        id fragmentLink = @{@"AXRole": @"AXLink", @"AXARIACurrent": @"page",
                            @"AXURL": @"app://-/index.html#/local/two"};
        id staleFragment = area(@"app://-/local/one", @[fragmentLink]);
        assert(chatAreas(@[staleFragment], @"one").count == 0);
        assert(chatAreas(@[staleFragment], @"two").count == 1);
        id fileLink = @{@"AXRole": @"AXLink", @"AXARIACurrent": @"page", @"AXURL": @"file:///local/one"};
        id fileShell = area(@"file:///Applications/ChatGPT.app/Contents/Resources/app.asar/webview/index.html",
                            @[fileLink]);
        assert(chatAreas(@[fileShell], @"one").count == 1);
        assert(chatAreas(@[area(@"file:///tmp/index.html", @[fileLink])], @"one").count == 0);
        assert(chatAreas(@[shell, shell], @"one").count == 1); // Same view via multiple roots.
        NSMutableDictionary *anotherShell = [shell mutableCopy];
        anotherShell[@"windowIdentity"] = @"two";
        assert(chatAreas(@[shell, anotherShell], @"one").count == 2);
        id window = @{@"AXRole": @"AXWindow", @"AXChildren": @[shell]};
        // An empty window list must not hide a readable focused/main window.
        id app = @{@"AXWindows": @[], @"AXMainWindow": window, @"AXFocusedWindow": window,
                   @"AXChildren": @[window]};
        NSMutableDictionary *rootCounts = [NSMutableDictionary dictionary];
        NSArray *roots = applicationRoots(app, rootCounts);
        assert(roots.count == 1 && [rootCounts[@"listedWindows"] isEqual:@0]);
        assert(chatAreas(roots, @"one").count == 1);
        id denied = @{@"AXRole": @"AXWindow", @"childrenError": @(kAXErrorAPIDisabled)};
        NSDictionary *deniedCounts = chatDiscoveryCounts(@[denied], @"one");
        assert([deniedCounts[@"childAPIDisabled"] isEqual:@1]);
        assert([deniedCounts[@"childReadErrors"] isEqual:@1]);
        attributeWrites = [NSMutableArray array];
        manualEnableResult = kAXErrorAttributeUnsupported;
        enableAccessibility(@{@"AXRole": @"AXApplication"}, rootCounts);
        assert(([attributeWrites isEqual:@[@"AXManualAccessibility", @"AXEnhancedUserInterface"]]));
        assert([rootCounts[@"enhancedAccepted"] isEqual:@YES]);
        [attributeWrites removeAllObjects];
        manualEnableResult = kAXErrorSuccess;
        enableAccessibility(@{}, rootCounts); // An accepted unknown attribute has no readback.
        assert(attributeWrites.count == 2);
        [attributeWrites removeAllObjects];
        manualEnableResult = kAXErrorAttributeUnsupported;
        enableAccessibility(@{@"AXEnhancedUserInterface": @YES}, rootCounts);
        assert([attributeWrites isEqual:@[@"AXManualAccessibility"]]);
        for (NSNumber *result in @[@(kAXErrorSuccess), @(kAXErrorAPIDisabled), @(kAXErrorCannotComplete)]) {
            [attributeWrites removeAllObjects];
            manualEnableResult = result.intValue;
            enableAccessibility(@{@"AXManualAccessibility": @YES}, rootCounts);
            assert([attributeWrites isEqual:@[@"AXManualAccessibility"]]);
        }
        assert(threadURL([NSURL URLWithString:@"app://-/local/one"], @"one"));
        assert(threadURL([NSURL URLWithString:@"app://-/index.html#/local/one"], @"one"));
        assert(threadURL([NSURL URLWithString:@"codex://threads/one"], @"one"));
        // Current desktop versions route Codex chats through /dots and /o.
        for (NSString *prefix in @[@"/dots/", @"/o/"]) {
            NSString *route = [prefix stringByAppendingString:@"one"];
            assert(threadURL([NSURL URLWithString:[@"app://-" stringByAppendingString:route]], @"one"));
            assert(threadURL([NSURL URLWithString:[@"app://-/index.html#" stringByAppendingString:route]], @"one"));
            id link = @{@"AXRole": @"AXLink", @"AXARIACurrent": @"page",
                        @"AXURL": [@"file://" stringByAppendingString:route]};
            id routed = area(@"file:///Applications/ChatGPT.app/Contents/Resources/app.asar/webview/index.html", @[link]);
            assert(chatAreas(@[routed], @"one").count == 1);
            assert(chatAreas(@[routed], @"two").count == 0);
            assert(!threadURL([NSURL URLWithString:[@"https://example.com" stringByAppendingString:route]], @"one"));
        }
        assert(!threadURL([NSURL URLWithString:@"https://example.com/local/one"], @"one"));
        assert(!threadURL([NSURL URLWithString:@"app://other/local/one"], @"one"));
        id editor = @{@"AXRole": @"AXTextArea", @"writable": @YES};
        // Distinguish a missing submit control from a submit outside the
        // editor's group, without exposing labels or any input contents.
        controlCounts = [NSMutableDictionary dictionary];
        recordControlCounts(controlIndex(chat(@[group(@[editor, button(@"Dictate", YES),
            button(@"Start voice chat", YES)]), button(@"Send", YES), button(@"Stop", YES),
            button(@"Resume", YES)])));
        assert([controlCounts[@"submit_buttons"] isEqual:@1]);
        assert([controlCounts[@"dictate_buttons"] isEqual:@1]);
        assert([controlCounts[@"voice_buttons"] isEqual:@1]);
        assert([controlCounts[@"stop_buttons"] isEqual:@1]);
        assert([controlCounts[@"resume_buttons"] isEqual:@1]);
        for (id value in controlCounts.allValues) assert([value isKindOfClass:NSNumber.class]);
        assert(pressComposer(chat(@[group(@[editor]), button(@"Send", YES)]), @"one") == 22);
        assert([controlCounts[@"submit_buttons"] isEqual:@1]);
        assert([controlCounts[@"candidates"] isEqual:@0]);
        assert(presses == 0);
        controlCounts = nil;
        // No text is read: rich input and attachment-only input belong to Codex.
        for (NSString *label in @[@"Send", @"发送", @"傳送", @"Queue", @"排队", @"加入佇列",
                                  @"Steer", @"引导", @"引導"]) {
            id submit = button(label, YES);
            id target = chat(@[group(@[group(@[editor]), group(@[submit])])]);
            presses = 0;
            assert(pressComposer(target, @"one") == 0);
            assert(presses == 1 && pressed == submit);
        }
        presses = 0;
        for (NSString *label in @[@"Send", @"Queue", @"Steer"])
            assert(pressComposer(chat(@[group(@[editor, button(label, NO)])]), @"one") == 28);
        for (NSString *label in @[@"Stop", @"停止", @"Transcribe and send", @"转录并发送"])
            assert(pressComposer(chat(@[group(@[editor, button(label, YES)])]), @"one") == 22);
        for (NSString *label in @[@"Start voice chat", @"开启语音聊天", @"開始語音對話",
                                  @"Resume", @"继续", @"繼續", @"恢復"]) {
            assert(pressComposer(chat(@[group(@[editor, button(label, YES)])]), @"one") == 29);
            // An unrelated control outside the editor's group is not evidence
            // of an empty main composer.
            assert(pressComposer(chat(@[group(@[editor]), button(label, YES)]), @"one") == 22);
        }
        assert(presses == 0);
        // A Voice control near the editor does not mean empty when the same
        // single-editor ancestor still owns a submit button.
        id nestedSubmit = button(@"Send", YES);
        assert(pressComposer(chat(@[group(@[group(@[editor, button(@"Start voice chat", YES)]),
            nestedSubmit])]), @"one") == 0);
        assert(presses == 1 && pressed == nestedSubmit);
        presses = 0;
        assert(pressComposer(chat(@[group(@[editor, button(@"Send", YES), button(@"Send", YES)])]), @"one") == 23);
        assert(pressComposer(chat(@[group(@[editor, button(@"Send", YES), button(@"Queue", YES)])]), @"one") == 23);
        assert(pressComposer(chat(@[group(@[editor, editor, button(@"Send", YES)])]), @"one") == 16);
        assert(pressComposer(chat(@[group(@[button(@"Send", YES)])]), @"one") == 15);
        // A sidebar or separate panel's Send cannot satisfy composer discovery.
        assert(pressComposer(chat(@[group(@[editor]), button(@"Send", YES)]), @"one") == 22);
        id browserControls = area(@"https://example.com", @[editor, button(@"Send", YES)]);
        assert(pressComposer(chat(@[browserControls]), @"one") == 15);
        id dialog = @{@"AXRole": @"AXGroup", @"AXSubrole": @"AXDialog",
                      @"AXChildren": @[editor, button(@"Send", YES)]};
        assert(pressComposer(chat(@[dialog]), @"one") == 15);
        id noAction = @{@"AXRole": @"AXButton", @"AXDescription": @"Send", @"AXEnabled": @YES};
        assert(pressComposer(chat(@[group(@[editor, noAction])]), @"one") == 18);
        // A route switch before pressing must fail even if controls still exist.
        id wrong = area(@"app://-/index.html", @[threadLink(@"two", @"page"), group(@[editor, button(@"Send", YES)])]);
        assert(pressComposer(wrong, @"one") == 24);
        assert(presses == 0);
        // Unknown press outcomes are returned after exactly one attempt.
        pressResult = kAXErrorCannotComplete;
        assert(pressComposer(chat(@[group(@[editor, button(@"Send", YES)])]), @"one") == 19);
        assert(presses == 1);
        pressResult = kAXErrorSuccess;
        presses = 0;
        id stop = button(@"Stop dictation", YES);
        id cancel = button(@"Cancel dictation", YES);
        id sendDictation = button(@"Transcribe and send", YES);
        id controls = @{@"AXRole": @"AXGroup", @"AXChildren": @[editor, button(@"Dictate", YES)],
                        @"recordingChildren": @[stop, cancel, sendDictation]};
        id dictationArea = chat(@[controls]);
        assert(pressAction(dictationArea, @"one", @"focus") == 0);
        assert(focusedEditor == editor && presses == 0 && !dictating);
        focusedEditor = nil;
        focusDenied = YES;
        assert(pressAction(dictationArea, @"one", @"focus") == 30);
        assert(focusedEditor == nil && presses == 0);
        focusDenied = NO;
        assert(pressAction(chat(@[controls, controls]), @"one", @"focus") == 16);
        assert(focusedEditor == nil && presses == 0);
        assert(pressAction(dictationArea, @"one", @"dictate-start") == 0);
        assert(presses == 1 && dictating);
        assert(pressAction(dictationArea, @"one", @"dictate-start") == 25);
        assert(presses == 1); // Never adopt or cancel a preexisting manual recording.
        assert(pressAction(dictationArea, @"one", @"dictate-stop") == 0);
        assert(presses == 2 && pressed == stop && !dictating);
        assert(pressed != sendDictation); // Release inserts, never submits.
        assert(pressAction(dictationArea, @"one", @"dictate-stop") == 0);
        assert(presses == 2); // Already idle: no toggle or duplicate action.
        assert(pressAction(dictationArea, @"one", @"dictate-start") == 0);
        assert(pressAction(dictationArea, @"one", @"dictate-cancel") == 0);
        assert(presses == 4 && pressed == cancel && !dictating);
        assert(pressAction(chat(@[group(@[sendDictation])]), @"one", @"dictate-stop") == 22);
        assert(presses == 4);
        assert(pressAction(chat(@[group(@[editor, button(@"Start voice chat", YES)])]), @"one", @"dictate-start") == 22);
        assert(pressAction(dictationArea, @"one", @"unknown") == 21);
        // One control scan, with one structural batch per node: transcript
        // length must not multiply work for manual-recording/editor/button checks.
        NSMutableArray *manyMessages = [NSMutableArray array];
        for (NSUInteger n = 0; n < 200; n++)
            [manyMessages addObject:group(@[@{@"AXRole": @"AXStaticText", @"messageIdentity": @(n)}])];
        [manyMessages addObject:controls];
        singleReads = batchReads = 0;
        assert(pressAction(chat(manyMessages), @"one", @"dictate-start") == 0);
        assert(singleReads + batchReads < 500);
        assert(pressAction(chat(manyMessages), @"one", @"dictate-stop") == 0);
        // A provider without batching still works through individual reads.
        batchResult = kAXErrorNotImplemented;
        assert(pressComposer(chat(@[group(@[editor, button(@"Send", YES)])]), @"one") == 0);
        batchResult = kAXErrorSuccess;
        NSUInteger before = presses;
        id unreadable = @{@"AXRole": @"AXGroup", @"childrenError": @(kAXErrorCannotComplete)};
        assert(pressAction(chat(@[unreadable, controls]), @"one", @"dictate-start") == 20);
        assert(presses == before);
        id unreliableIdentity = area(@"app://-/local/one", @[unreadable]);
        assert(chatAreas(@[unreliableIdentity], @"one").count == 0);
        // A control-group replacement after Start must use a fresh area scan.
        id oldGroup = @{@"AXRole": @"AXGroup", @"AXChildren": @[editor, button(@"Dictate", YES)],
            @"recordingChildrenError": @(kAXErrorCannotComplete)};
        id replaced = @{@"AXRole": @"AXWebArea", @"AXURL": @"app://-/index.html",
            @"AXChildren": @[threadLink(@"one", @"page"), oldGroup],
            @"recordingChildren": @[threadLink(@"one", @"page"), group(@[stop, cancel])]};
        assert(pressAction(replaced, @"one", @"dictate-start") == 0);
        assert(pressAction(replaced, @"one", @"dictate-stop") == 0);
        // Do not press a snapshot candidate that became a different action.
        NSMutableDictionary *changed = [button(@"Dictate", YES) mutableCopy];
        changed[@"changedLabelOnActionRead"] = @YES;
        before = presses;
        assert(pressAction(chat(@[group(@[editor, changed])]), @"one", @"dictate-start") == 22);
        assert(presses == before && !dictating);

        actionLabelChanged = NO;
        // An unrelated editable panel must not make one actual composer
        // ambiguous, and must not acquire its button through a shared ancestor.
        id auxiliaryEditor = @{@"AXRole": @"AXTextArea", @"writable": @YES, @"identity": @"auxiliary"};
        id auxiliary = group(@[group(@[auxiliaryEditor])]);
        id withPanel = chat(@[group(@[auxiliary, controls])]);
        assert(pressAction(withPanel, @"one", @"dictate-start") == 0);
        assert(pressAction(withPanel, @"one", @"dictate-stop") == 0);
        assert(pressComposer(chat(@[group(@[auxiliary, group(@[editor, button(@"Send", YES)])])]), @"one") == 0);
        before = presses;
        id anotherComposer = group(@[auxiliaryEditor, button(@"Dictate", YES)]);
        assert(pressAction(chat(@[group(@[controls, anotherComposer])]), @"one", @"dictate-start") == 16);
        assert(pressAction(chat(@[group(@[editor, auxiliaryEditor, button(@"Dictate", YES)])]),
                           @"one", @"dictate-start") == 16);
        assert(pressAction(chat(@[group(@[auxiliary, editor]), button(@"Dictate", YES)]),
                           @"one", @"dictate-start") == 16);
        assert(presses == before && !dictating);
        // A question input also offers Dictate. Bind the message composer's
        // Dictate through its own Send control, including an empty draft.
        id questionDictate = button(@"Dictate", YES);
        id question = group(@[auxiliaryEditor, questionDictate]);
        id messageDictate = button(@"Dictate", YES);
        id message = @{@"AXRole": @"AXGroup", @"AXChildren": @[
            group(@[editor]), group(@[messageDictate]), button(@"Send", NO)],
            @"recordingChildren": @[stop, cancel]};
        assert(pressAction(chat(@[group(@[question, message])]), @"one", @"dictate-start") == 0);
        assert(pressed == messageDictate && pressed != questionDictate);
        assert(pressAction(chat(@[group(@[question, message])]), @"one", @"dictate-stop") == 0);
        before = presses;
        id anotherMessage = group(@[auxiliaryEditor, button(@"Dictate", YES), button(@"Send", NO)]);
        assert(pressAction(chat(@[message, anotherMessage]), @"one", @"dictate-start") == 16);
        assert(presses == before && !dictating);
        // An active run replaces Send with Queue/Steer. Dictation must still
        // choose the main composer rather than a pending question's Dictate.
        for (NSString *label in @[@"Queue", @"Steer"]) {
            id activeMessage = @{@"AXRole": @"AXGroup", @"AXChildren": @[
                group(@[editor]), messageDictate, button(label, NO)],
                @"recordingChildren": @[stop, cancel]};
            id activeChat = chat(@[question, activeMessage]);
            assert(pressAction(activeChat, @"one", @"dictate-start") == 0);
            assert(pressed == messageDictate);
            assert(pressAction(activeChat, @"one", @"dictate-stop") == 0);
        }
        // Empty main chats show Voice/Resume instead of Send. A question's
        // separate Send/Dictate must not become the target for short/long OK.
        for (NSString *label in @[@"Start voice chat", @"Resume"]) {
            id questionSubmit = group(@[auxiliaryEditor, questionDictate, button(@"Send", YES)]);
            id emptyMessage = @{@"AXRole": @"AXGroup", @"AXChildren": @[
                group(@[editor]), group(@[messageDictate]), button(label, YES)],
                @"recordingChildren": @[stop, cancel]};
            id emptyChat = chat(@[group(@[questionSubmit, emptyMessage])]);
            before = presses;
            assert(pressComposer(emptyChat, @"one") == 29);
            assert(presses == before);
            assert(pressAction(emptyChat, @"one", @"dictate-start") == 0);
            assert(pressed == messageDictate && pressed != questionDictate);
            assert(pressAction(emptyChat, @"one", @"dictate-stop") == 0);
            assert(presses == before + 2 && !dictating);
        }
        before = presses;
        id emptyOne = group(@[editor, button(@"Dictate", YES), button(@"Start voice chat", YES)]);
        id emptyTwo = group(@[auxiliaryEditor, button(@"Dictate", YES), button(@"Resume", YES)]);
        assert(pressComposer(chat(@[emptyOne, emptyTwo]), @"one") == 16);
        assert(pressAction(chat(@[emptyOne, emptyTwo]), @"one", @"dictate-start") == 16);
        id wrongEmpty = area(@"app://-/index.html", @[threadLink(@"two", @"page"), emptyOne]);
        assert(pressComposer(wrongEmpty, @"one") == 24);
        assert(presses == before && !dictating);
        // An unsent native composer is bound to one uniquely named project,
        // with no selected saved-chat row. Recheck before every action.
        draftProject = @"Alpha";
        id project = button(@"Change project: Alpha", YES);
        id draftControls = @{@"AXRole": @"AXGroup", @"AXChildren": @[
            editor, button(@"Dictate", YES), button(@"Send", YES)],
            @"recordingChildren": @[stop, cancel]};
        id draft = area(@"app://-/index.html", @[project, draftControls]);
        assert(chatAreas(@[draft], @"@new:one").count == 1);
        assert(pressAction(draft, @"@new:one", @"focus") == 0);
        assert(pressAction(draft, @"@new:one", @"dictate-start") == 0);
        assert(pressAction(draft, @"@new:one", @"dictate-stop") == 0);
        assert(pressComposer(draft, @"@new:one") == 0);
        for (NSString *label in @[@"切换项目：Alpha", @"更改项目：Alpha"]) {
            id localizedDraft = area(@"app://-/index.html", @[button(label, YES), draftControls]);
            assert(pressAction(localizedDraft, @"@new:one", @"focus") == 0);
        }
        before = presses;
        assert(chatAreas(@[draft, draft], @"@new:one").count == 2);
        assert(chatAreas(@[area(@"app://-/index.html", @[draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/index.html", @[project, project, draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/local/one", @[project, draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/index.html#/local/one", @[project, draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"https://example.com/", @[project, draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/index.html", @[threadLink(@"one", @"page"), project, draftControls])],
                         @"@new:one").count == 0);
        // The actual home picker is a heading button bearing only the project
        // name. Sidebar current markers can survive navigation to a new draft.
        id hero = @{@"AXRole": @"AXButton", @"AXDescription": @"Alpha",
            @"AXDOMClassList": @[@"heading-xl", @"text-tertiary", @"select-none"]};
        id heroHome = area(@"app://-/index.html", @[currentButton, hero, draftControls]);
        assert(chatAreas(@[heroHome], @"@new:one").count == 1);
        assert(pressAction(heroHome, @"@new:one", @"focus") == 0);
        NSMutableDictionary *popupHero = [hero mutableCopy];
        popupHero[@"AXRole"] = @"AXPopUpButton";
        id popupHome = area(@"app://-/index.html", @[currentButton, popupHero, draftControls]);
        assert(chatAreas(@[popupHome], @"@new:one").count == 1);
        assert(pressAction(popupHome, @"@new:one", @"focus") == 0);
        assert(chatAreas(@[area(@"app://-/index.html", @[currentButton, hero, project, draftControls])],
                         @"@new:one").count == 1);
        assert(chatAreas(@[area(@"app://-/index.html", @[hero, button(@"Change project: Beta", YES), draftControls])],
                         @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/index.html", @[hero, hero, draftControls])], @"@new:one").count == 0);
        // A name alone, content heading, dialog, browser or saved route cannot
        // supply native-home evidence and must never focus or press controls.
        assert(chatAreas(@[area(@"app://-/index.html", @[button(@"Alpha", YES), draftControls])], @"@new:one").count == 0);
        id partialHero = @{@"AXRole": @"AXButton", @"AXDescription": @"Alpha",
            @"AXDOMClassList": @[@"heading-xl"]};
        assert(chatAreas(@[area(@"app://-/index.html", @[partialHero, draftControls])], @"@new:one").count == 0);
        id dialogHero = @{@"AXRole": @"AXDialog", @"AXChildren": @[hero]};
        assert(chatAreas(@[area(@"app://-/index.html", @[dialogHero, draftControls])], @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/index.html", @[area(@"https://example.com/", @[hero]), draftControls])],
                         @"@new:one").count == 0);
        assert(chatAreas(@[area(@"app://-/local/one", @[hero, draftControls])], @"@new:one").count == 0);
        draftProject = @"Beta";
        assert(chatAreas(@[heroHome], @"@new:one").count == 0);
        assert(pressComposer(draft, @"@new:one") == 24);
        assert(presses == before);
        draftProject = nil;
        assert(chatAreas(@[draft], @"@new:one").count == 0);
        puts("Composer target selection, Send and insert-only dictation: PASS");
    }
    return 0;
}
