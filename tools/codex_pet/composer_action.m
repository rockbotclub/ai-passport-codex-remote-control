// Operate Send or non-sending Dictate controls in one selected chat. No key synthesis.
#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#include <unistd.h>

// Only the bridge may supply a title after checking uniqueness in its catalog.
// Current desktop sidebar rows are buttons, so they expose no destination URL.
static NSDictionary<NSString *, NSString *> *sidebarTitles;
static NSString *draftProject;
static NSMutableDictionary *draftDiscovery;
static NSMutableDictionary *nativeTiming;
static NSMutableDictionary *controlCounts;
static NSString *timingStage;
static NSTimeInterval stageStarted;

static void beginStage(NSString *stage) {
    if (!nativeTiming) return;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    if (timingStage)
        nativeTiming[timingStage] = @([nativeTiming[timingStage] doubleValue] + (now - stageStarted) * 1000);
    timingStage = stage;
    stageStarted = now;
}

static id checkedAttribute(id element, CFStringRef name, AXError *result) {
    CFTypeRef value = NULL;
    *result = AXUIElementCopyAttributeValue((__bridge AXUIElementRef)element, name, &value);
    if (*result != kAXErrorSuccess) return nil;
    return CFBridgingRelease(value);
}

static id attribute(id element, CFStringRef name) {
    AXError result;
    return checkedAttribute(element, name, &result);
}

// One cross-process call per node. Never request AXValue or text contents.
// Keep individual-attribute fallback for providers that reject a batch.
static NSDictionary *attributes(id element, NSArray<NSString *> *names) {
    CFArrayRef raw = NULL;
    AXError result = AXUIElementCopyMultipleAttributeValues((__bridge AXUIElementRef)element,
        (__bridge CFArrayRef)names, 0, &raw);
    NSArray *values = CFBridgingRelease(raw);
    NSMutableDictionary *found = [NSMutableDictionary dictionary];
    BOOL batched = result == kAXErrorSuccess && values.count == names.count;
    for (NSUInteger index = 0; index < names.count; index++) {
        AXError error = kAXErrorSuccess;
        id value = batched ? values[index] : checkedAttribute(element, (__bridge CFStringRef)names[index], &error);
        if (value && CFGetTypeID((__bridge CFTypeRef)value) == AXValueGetTypeID() &&
                AXValueGetType((__bridge AXValueRef)value) == kAXValueAXErrorType) {
            AXValueGetValue((__bridge AXValueRef)value, kAXValueAXErrorType, &error);
            value = nil;
        }
        if (error != kAXErrorSuccess && error != kAXErrorNoValue && error != kAXErrorAttributeUnsupported)
            return nil; // An incomplete tree must not hide another editor/button.
        if (value && value != NSNull.null) found[names[index]] = value;
    }
    return found;
}

static NSArray *children(id element) {
    id value = attribute(element, kAXChildrenAttribute);
    return [value isKindOfClass:NSArray.class] ? value : @[];
}

static BOOL webArea(id element) {
    return [attribute(element, kAXRoleAttribute) isEqual:@"AXWebArea"];
}

static NSArray *applicationRoots(id app, NSMutableDictionary *diagnostic) {
    AXError windowResult, childResult;
    id windows = checkedAttribute(app, kAXWindowsAttribute, &windowResult);
    NSArray *listed = [windows isKindOfClass:NSArray.class] ? windows : @[];
    NSMutableArray *roots = [listed mutableCopy];
    id main = attribute(app, kAXMainWindowAttribute);
    id focused = attribute(app, kAXFocusedWindowAttribute);
    id rawChildren = checkedAttribute(app, kAXChildrenAttribute, &childResult);
    NSArray *appChildren = [rawChildren isKindOfClass:NSArray.class] ? rawChildren : @[];
    if (main && ![roots containsObject:main]) [roots addObject:main];
    if (focused && ![roots containsObject:focused]) [roots addObject:focused];
    for (id child in appChildren) if (![roots containsObject:child]) [roots addObject:child];
    diagnostic[@"listedWindows"] = @(listed.count);
    diagnostic[@"mainWindow"] = @(main != nil);
    diagnostic[@"focusedWindow"] = @(focused != nil);
    diagnostic[@"appChildren"] = @(appChildren.count);
    diagnostic[@"windowAttributeAvailable"] = @(windowResult == kAXErrorSuccess);
    diagnostic[@"windowAPIDisabled"] = @(windowResult == kAXErrorAPIDisabled);
    diagnostic[@"windowCannotComplete"] = @(windowResult == kAXErrorCannotComplete);
    diagnostic[@"appChildAttributeAvailable"] = @(childResult == kAXErrorSuccess);
    diagnostic[@"appChildAPIDisabled"] = @(childResult == kAXErrorAPIDisabled);
    diagnostic[@"appChildCannotComplete"] = @(childResult == kAXErrorCannotComplete);
    return roots;
}

static void enableAccessibility(id app, NSMutableDictionary *diagnostic) {
    // Chromium's application-role getter activates its native AX interface.
    attribute(app, kAXRoleAttribute);
    AXError result = AXUIElementSetAttributeValue((__bridge AXUIElementRef)app,
        CFSTR("AXManualAccessibility"), kCFBooleanTrue);
    diagnostic[@"enableAccepted"] = @(result == kAXErrorSuccess);
    diagnostic[@"enableUnsupported"] = @(result == kAXErrorAttributeUnsupported);
    diagnostic[@"enableAPIDisabled"] = @(result == kAXErrorAPIDisabled);
    diagnostic[@"enableCannotComplete"] = @(result == kAXErrorCannotComplete);
    AXError enhanced = kAXErrorSuccess;
    id manualStatus = attribute(app, CFSTR("AXManualAccessibility"));
    id alreadyEnhanced = attribute(app, CFSTR("AXEnhancedUserInterface"));
    BOOL manualUnavailable = result == kAXErrorAttributeUnsupported ||
        (result == kAXErrorSuccess && manualStatus == nil);
    BOOL requestEnhanced = manualUnavailable && ![alreadyEnhanced isEqual:@YES];
    if (requestEnhanced) {
        // The installed Chromium shell lacks Electron's manual attribute.
        // Request its app-local AX interface once, never toggle it off or touch
        // the system VoiceOver setting. Chromium may debounce this for 2 s.
        enhanced = AXUIElementSetAttributeValue((__bridge AXUIElementRef)app,
            CFSTR("AXEnhancedUserInterface"), kCFBooleanTrue);
    }
    diagnostic[@"enhancedRequested"] = @(requestEnhanced);
    diagnostic[@"enhancedAccepted"] = @(requestEnhanced && enhanced == kAXErrorSuccess);
    diagnostic[@"enhancedUnsupported"] = @(requestEnhanced && enhanced == kAXErrorAttributeUnsupported);
    diagnostic[@"enhancedAPIDisabled"] = @(requestEnhanced && enhanced == kAXErrorAPIDisabled);
    diagnostic[@"enhancedCannotComplete"] = @(requestEnhanced && enhanced == kAXErrorCannotComplete);
}

static NSURL *elementURL(id element) {
    id raw = attribute(element, kAXURLAttribute);
    return [raw isKindOfClass:NSURL.class] ? raw :
        ([raw isKindOfClass:NSString.class] ? [NSURL URLWithString:raw] : nil);
}

static BOOL threadURL(NSURL *url, NSString *thread) {
    if (!url || !thread.length) return NO;
    if (![@[@"app", @"codex"] containsObject:url.scheme]) return NO;
    if ([url.scheme isEqual:@"app"] && url.host.length && ![url.host isEqual:@"-"]) return NO;
    NSArray *paths = @[[ @"/local/" stringByAppendingString:thread],
                      [@"/dots/" stringByAppendingString:thread],
                      [@"/o/" stringByAppendingString:thread],
                      [@"/hotkey-window/thread/" stringByAppendingString:thread]];
    NSString *fragment = [[url.fragment componentsSeparatedByString:@"?"] firstObject];
    return [paths containsObject:url.path] || (fragment && [paths containsObject:fragment]) ||
        ([url.scheme isEqual:@"codex"] && [url.host isEqual:@"threads"] &&
         [url.path isEqual:[@"/" stringByAppendingString:thread]]);
}

static BOOL currentThreadLink(id area, NSString *thread, BOOL *hasCurrentChat) {
    NSMutableArray *pending = [NSMutableArray array];
    for (id child in children(area)) [pending addObject:@[child, @NO]];
    NSUInteger visited = 0;
    for (NSUInteger cursor = 0; cursor < pending.count; cursor++) {
        if (++visited > 20000) { *hasCurrentChat = YES; return NO; }
        // Sidebar rows are shallow. Breadth-first traversal avoids walking a
        // long transcript before reaching the current chat's navigation row.
        NSArray *entry = pending[cursor];
        id element = entry[0];
        NSDictionary *node = attributes(element, @[@"AXRole", @"AXARIACurrent", @"AXChildren"]);
        if (!node || !node[@"AXRole"]) { *hasCurrentChat = YES; return NO; }
        id role = node[@"AXRole"];
        if ([role isEqual:@"AXWebArea"]) continue; // Never trust browser navigation.
        id current = node[@"AXARIACurrent"];
        BOOL active = [entry[1] boolValue] || [current isEqual:@"page"] || [current isEqual:@"true"];
        BOOL currentRow = NO;
        if ([current isEqual:@"page"] && [role isEqual:@"AXButton"]) {
            id classes = attribute(element, CFSTR("AXDOMClassList"));
            currentRow = [classes isKindOfClass:NSArray.class] && [classes containsObject:@"sidebar-item"];
        }
        if (currentRow) {
            *hasCurrentChat = YES;
            NSString *title = sidebarTitles[thread];
            if (title.length && ([attribute(element, kAXTitleAttribute) isEqual:title] ||
                                 [attribute(element, kAXDescriptionAttribute) isEqual:title])) return YES;
        }
        if (active && [role isEqual:@"AXLink"]) {
            NSURL *url = elementURL(element);
            // Relative links in a packaged file renderer resolve to file:///local/...
            // They are considered only inside the trusted application shell.
            if ([url.scheme isEqual:@"file"]) {
                NSURLComponents *route = [NSURLComponents componentsWithString:@"app://-"];
                route.path = url.path;
                route.fragment = url.fragment;
                url = route.URL;
            }
            NSString *fragmentPath = [[url.fragment componentsSeparatedByString:@"?"] firstObject];
            if (threadURL(url, url.lastPathComponent) || threadURL(url, fragmentPath.lastPathComponent))
                *hasCurrentChat = YES;
            if (threadURL(url, thread)) return YES;
        }
        if (![role isEqual:@"AXStaticText"] && ![role isEqual:@"AXTextArea"] &&
                ![role isEqual:@"AXTextField"])
            for (id child in node[@"AXChildren"]) [pending addObject:@[child, @(active)]];
    }
    return NO;
}

static BOOL draftArea(id area, NSURL *url) {
    if (!draftProject.length) return NO;
    draftDiscovery = [@{@"draft_route_ok": @0, @"draft_current_chat": @0,
        @"draft_project_matches": @0, @"draft_hero_matches": @0,
        @"draft_project_conflicts": @0, @"draft_scan_complete": @0} mutableCopy];
    NSString *route = [[url.fragment componentsSeparatedByString:@"?"] firstObject];
    if (route.length && ![route isEqual:@"/"]) return NO;
    if (![url.path isEqual:@"/"] && ![url.path isEqual:@"/index.html"] &&
            ![url.path hasSuffix:@"/Contents/Resources/app.asar/webview/index.html"]) return NO;
    draftDiscovery[@"draft_route_ok"] = @1;
    BOOL hasCurrentChat = NO;
    currentThreadLink(area, @"", &hasCurrentChat);
    draftDiscovery[@"draft_current_chat"] = @(hasCurrentChat);
    // Exact messages from the installed English and Simplified Chinese assets.
    NSArray *labels = @[[ @"Change project: " stringByAppendingString:draftProject],
                       [@"切换项目：" stringByAppendingString:draftProject],
                       [@"更改项目：" stringByAppendingString:draftProject]];
    NSMutableArray *pending = [children(area) mutableCopy];
    NSUInteger matches = 0, heroes = 0, conflicts = 0, visited = 0;
    while (pending.count) {
        if (++visited > 20000) return NO;
        id element = pending.lastObject;
        [pending removeLastObject];
        NSDictionary *node = attributes(element, @[@"AXRole", @"AXSubrole", @"AXChildren"]);
        if (!node || !node[@"AXRole"]) return NO;
        NSString *role = node[@"AXRole"];
        if ([role isEqual:@"AXWebArea"] || [role isEqual:@"AXDialog"] ||
                [role isEqual:@"AXSheet"] || [node[@"AXSubrole"] isEqual:@"AXDialog"]) continue;
        if ([role isEqual:@"AXButton"] || [role isEqual:@"AXPopUpButton"]) {
            NSDictionary *names = attributes(element, @[@"AXTitle", @"AXDescription"]);
            if (!names) return NO;
            BOOL matching = [labels containsObject:names[@"AXTitle"] ?: NSNull.null] ||
                            [labels containsObject:names[@"AXDescription"] ?: NSNull.null];
            if (matching) matches++;
            else for (NSString *name in names.allValues) {
                if (![name isKindOfClass:NSString.class]) continue;
                if ([name hasPrefix:@"Change project: "] || [name hasPrefix:@"切换项目："] ||
                        [name hasPrefix:@"更改项目："]) { conflicts++; break; }
            }
            // The native home composer uses a hero project picker whose label
            // is just the project name, not "Change project: ...". Its exact
            // button classes come from localCwdDropdown's installed renderer.
            // Saved-chat sidebars can retain current markers on that home view.
            id classes = attribute(element, CFSTR("AXDOMClassList"));
            BOOL hero = [classes isKindOfClass:NSArray.class] &&
                [classes containsObject:@"heading-xl"] &&
                [classes containsObject:@"text-tertiary"] &&
                [classes containsObject:@"select-none"];
            if (hero && ([names[@"AXTitle"] isEqual:draftProject] ||
                         [names[@"AXDescription"] isEqual:draftProject])) heroes++;
        }
        if (![role isEqual:@"AXStaticText"] && ![role isEqual:@"AXTextArea"] &&
                ![role isEqual:@"AXTextField"])
            [pending addObjectsFromArray:node[@"AXChildren"] ?: @[]];
    }
    draftDiscovery[@"draft_project_matches"] = @(matches);
    draftDiscovery[@"draft_hero_matches"] = @(heroes);
    draftDiscovery[@"draft_project_conflicts"] = @(conflicts);
    draftDiscovery[@"draft_scan_complete"] = @1;
    // A current saved-chat marker requires positive native-home evidence.
    // Never relax an ordinary saved-chat lookup or accept a name by itself.
    return !conflicts && matches <= 1 && heroes <= 1 &&
        (heroes == 1 || (!hasCurrentChat && matches == 1));
}

static void reportDraftDiscovery(void) {
    if (!draftDiscovery) return;
    NSData *data = [NSJSONSerialization dataWithJSONObject:draftDiscovery options:0 error:NULL];
    if (data) {
        [[NSFileHandle fileHandleWithStandardError] writeData:data];
        fputc('\n', stderr);
    }
}

static NSArray *chatAreas(NSArray *windows, NSString *thread) {
    NSMutableArray *pending = [windows mutableCopy], *found = [NSMutableArray array];
    NSUInteger visited = 0;
    while (pending.count) {
        if (++visited > 20000) return nil;
        id element = pending.lastObject;
        [pending removeLastObject];
        if (webArea(element)) {
            NSURL *url = elementURL(element);
            // Electron may keep a shell URL while its internal router switches
            // chats. Bind that view through its current sidebar link instead.
            BOOL shell = [url.scheme isEqual:@"app"] &&
                (!url.host.length || [url.host isEqual:@"-"]);
            shell = shell || ([url.scheme isEqual:@"file"] &&
                [url.path hasSuffix:@"/Contents/Resources/app.asar/webview/index.html"]);
            if ([thread hasPrefix:@"@new:"]) {
                if (shell && draftArea(element, url)) [found addObject:element];
                continue;
            }
            BOOL hasCurrentChat = NO;
            BOOL current = shell && currentThreadLink(element, thread, &hasCurrentChat);
            if (current || (!hasCurrentChat && threadURL(url, thread))) {
                if (![found containsObject:element]) [found addObject:element];
                continue;
            }
        }
        [pending addObjectsFromArray:children(element)];
    }
    return found;
}

// Emit counts only after a physical action fails discovery. No labels, text,
// URLs or chat identifiers leave the helper. This never weakens target binding.
static NSDictionary *chatDiscoveryCounts(NSArray *windows, NSString *thread) {
    NSMutableDictionary *counts = [@{@"webAreas": @0, @"shellAreas": @0,
        @"missingURLs": @0, @"otherURLs": @0, @"links": @0, @"targetLinks": @0,
        @"currentMarkers": @0, @"numericCurrentMarkers": @0, @"selectedLinks": @0,
        @"roots": @(windows.count), @"roleReadErrors": @0, @"childReadErrors": @0,
        @"childAPIDisabled": @0, @"childCannotComplete": @0} mutableCopy];
    NSMutableArray *pending = [windows mutableCopy];
    NSUInteger visited = 0;
    while (pending.count && ++visited <= 20000) {
        id element = pending.lastObject;
        [pending removeLastObject];
        AXError roleResult;
        checkedAttribute(element, kAXRoleAttribute, &roleResult);
        if (roleResult != kAXErrorSuccess)
            counts[@"roleReadErrors"] = @([counts[@"roleReadErrors"] unsignedIntegerValue] + 1);
        if (webArea(element)) {
            counts[@"webAreas"] = @([counts[@"webAreas"] unsignedIntegerValue] + 1);
            NSURL *url = elementURL(element);
            BOOL shell = ([url.scheme isEqual:@"app"] && (!url.host.length || [url.host isEqual:@"-"])) ||
                ([url.scheme isEqual:@"file"] && [url.path hasSuffix:@"/Contents/Resources/app.asar/webview/index.html"]);
            NSString *key = shell ? @"shellAreas" : (!url ? @"missingURLs" : @"otherURLs");
            counts[key] = @([counts[key] unsignedIntegerValue] + 1);
            if (!shell) continue; // Browser panels supply no identity evidence.
        }
        id current = attribute(element, CFSTR("AXARIACurrent"));
        if (current) {
            counts[@"currentMarkers"] = @([counts[@"currentMarkers"] unsignedIntegerValue] + 1);
            if ([current isKindOfClass:NSNumber.class])
                counts[@"numericCurrentMarkers"] = @([counts[@"numericCurrentMarkers"] unsignedIntegerValue] + 1);
        }
        if ([attribute(element, kAXRoleAttribute) isEqual:@"AXLink"]) {
            counts[@"links"] = @([counts[@"links"] unsignedIntegerValue] + 1);
            NSURL *url = elementURL(element);
            if ([url.scheme isEqual:@"file"]) {
                NSURLComponents *route = [NSURLComponents componentsWithString:@"app://-"];
                route.path = url.path; route.fragment = url.fragment; url = route.URL;
            }
            if (threadURL(url, thread))
                counts[@"targetLinks"] = @([counts[@"targetLinks"] unsignedIntegerValue] + 1);
            if ([attribute(element, kAXSelectedAttribute) isEqual:@YES])
                counts[@"selectedLinks"] = @([counts[@"selectedLinks"] unsignedIntegerValue] + 1);
        }
        AXError childResult;
        id nodes = checkedAttribute(element, kAXChildrenAttribute, &childResult);
        if (childResult != kAXErrorSuccess && childResult != kAXErrorNoValue &&
                childResult != kAXErrorAttributeUnsupported) {
            counts[@"childReadErrors"] = @([counts[@"childReadErrors"] unsignedIntegerValue] + 1);
            NSString *key = childResult == kAXErrorAPIDisabled ? @"childAPIDisabled" :
                (childResult == kAXErrorCannotComplete ? @"childCannotComplete" : nil);
            if (key) counts[key] = @([counts[key] unsignedIntegerValue] + 1);
        }
        if ([nodes isKindOfClass:NSArray.class]) [pending addObjectsFromArray:nodes];
    }
    counts[@"treeLimit"] = @(pending.count > 0);
    counts[@"visited"] = @(MIN(visited, 20000));
    return counts;
}

// Gather paths so button discovery stays inside the editor's own control group.
// Browser panels and dialogs must never supply either an editor or a Send button.
static BOOL blockedSubtree(NSDictionary *node) {
    id role = node[@"AXRole"];
    return [role isEqual:@"AXWebArea"] || [role isEqual:@"AXDialog"] || [role isEqual:@"AXSheet"] ||
        [node[@"AXSubrole"] isEqual:@"AXDialog"];
}

// A single bounded scan supplies editors, active dictation controls and action
// candidates. Ancestor matching below uses these paths without another AX walk.
static NSDictionary *controlIndex(id root) {
    NSMutableArray *pending = [NSMutableArray array], *editors = [NSMutableArray array],
        *buttons = [NSMutableArray array];
    if (webArea(root)) {
        for (id child in children(root)) [pending addObject:@[child]];
    } else {
        [pending addObject:@[root]];
    }
    NSUInteger visited = 0;
    while (pending.count) {
        if (++visited > 20000) return nil;
        NSArray *path = pending.lastObject;
        [pending removeLastObject];
        id element = path.lastObject;
        NSDictionary *node = attributes(element, @[@"AXRole", @"AXSubrole", @"AXChildren"]);
        if (!node || !node[@"AXRole"]) return nil;
        id role = node[@"AXRole"];
        if ([role isEqual:@"AXStaticText"] || blockedSubtree(node)) continue;
        if ([role isEqual:@"AXTextArea"]) {
            Boolean settable = false;
            if (AXUIElementIsAttributeSettable((__bridge AXUIElementRef)element, kAXValueAttribute,
                                               &settable) == kAXErrorSuccess && settable)
                [editors addObject:path];
        }
        if ([role isEqual:@"AXButton"]) {
            NSDictionary *labels = attributes(element, @[@"AXTitle", @"AXDescription"]);
            if (!labels) return nil;
            [buttons addObject:@{@"path": path, @"labels": labels.allValues}];
        }
        for (id child in node[@"AXChildren"]) [pending addObject:[path arrayByAddingObject:child]];
    }
    return @{@"editors": editors, @"buttons": buttons};
}

static NSArray *actionLabels(NSString *action) {
    // Labels from the installed desktop's composer.dictation.* messages.
    // The native submit control becomes Queue/Steer during an active run.
    // Preserve Codex's chosen submission mode; Stop and Resume are separate.
    // Voice chat is a separate UI.
    if ([action isEqual:@"send"]) return @[@"Send", @"发送", @"傳送",
        @"Queue", @"排队", @"加入佇列", @"Steer", @"引导", @"引導"];
    if ([action isEqual:@"dictate-start"] || [action isEqual:@"focus"])
        return @[@"Dictate", @"听写", @"聽寫"];
    if ([action isEqual:@"dictate-stop"]) return @[@"Stop dictation", @"停止听写", @"停止聽寫"];
    if ([action isEqual:@"dictate-cancel"]) return @[@"Cancel dictation", @"取消听写", @"取消聽寫",
        @"Cancel transcription", @"取消转录", @"取消轉錄", @"Starting dictation; click to cancel",
        @"正在启动听写；点击可取消", @"正在開始聽寫；按一下即可取消"];
    return nil;
}

static BOOL insidePath(NSArray *path, NSArray *scope) {
    return !scope.count || (path.count >= scope.count &&
        [[path subarrayWithRange:NSMakeRange(0, scope.count)] isEqual:scope]);
}

static NSArray *voiceLabels(void) {
    return @[@"Start voice chat", @"开启语音聊天", @"開始語音對話"];
}

static NSArray *resumeLabels(void) {
    return @[@"Resume", @"继续", @"繼續", @"恢復"];
}

static NSArray *indexedButtons(NSDictionary *index, NSArray *labels, NSArray *scope) {
    NSMutableArray *found = [NSMutableArray array];
    for (NSDictionary *button in index[@"buttons"]) {
        NSArray *path = button[@"path"];
        if (!insidePath(path, scope)) continue;
        for (id value in button[@"labels"]) {
            if ([labels containsObject:value]) { [found addObject:path.lastObject]; break; }
        }
    }
    return found;
}

static void recordControlCounts(NSDictionary *index) {
    // Fixed numeric categories only: never log control labels, text or paths.
    controlCounts[@"scan_complete"] = @1;
    controlCounts[@"editors"] = @([index[@"editors"] count]);
    controlCounts[@"buttons"] = @([index[@"buttons"] count]);
    controlCounts[@"submit_buttons"] = @(indexedButtons(index, actionLabels(@"send"), nil).count);
    controlCounts[@"dictate_buttons"] = @(indexedButtons(index, actionLabels(@"dictate-start"), nil).count);
    controlCounts[@"stop_buttons"] = @(indexedButtons(index, @[@"Stop", @"停止"], nil).count);
    controlCounts[@"resume_buttons"] = @(indexedButtons(index, resumeLabels(), nil).count);
    controlCounts[@"voice_buttons"] = @(indexedButtons(index, voiceLabels(), nil).count);
}

static int pressButton(id button, id area, NSString *thread, NSArray *labels) {
    beginStage(@"press_ms");
    CFArrayRef rawActions = NULL;
    AXError result = AXUIElementCopyActionNames((__bridge AXUIElementRef)button, &rawActions);
    NSArray *actions = CFBridgingRelease(rawActions);
    if (result != kAXErrorSuccess || ![actions containsObject:(__bridge NSString *)kAXPressAction]) return 18;
    if (chatAreas(@[area], thread).count != 1) return 24;
    // A collected button may have changed from Dictate to Stop while scanning.
    // Re-read its live action label and enabled state immediately before Press.
    NSDictionary *live = attributes(button, @[@"AXEnabled", @"AXTitle", @"AXDescription"]);
    if (!live) return 20;
    if (![labels containsObject:live[@"AXTitle"] ?: NSNull.null] &&
            ![labels containsObject:live[@"AXDescription"] ?: NSNull.null]) return 22;
    if (![live[@"AXEnabled"] isEqual:@YES])
        return [labels isEqual:actionLabels(@"send")] ? 28 : 22;
    // Dispatch once. Never retry, synthesize keys, write text or use coordinates.
    return AXUIElementPerformAction((__bridge AXUIElementRef)button, kAXPressAction) == kAXErrorSuccess ? 0 : 19;
}

static int pressAction(id area, NSString *thread, NSString *action) {
    NSArray *labels = actionLabels(action);
    if (!labels) return 21;
    BOOL focusing = [action isEqual:@"focus"];
    BOOL starting = focusing || [action isEqual:@"dictate-start"];
    BOOL finishing = [action isEqual:@"dictate-stop"] || [action isEqual:@"dictate-cancel"];
    NSDictionary *index = controlIndex(area);
    if (!index) return 20;
    recordControlCounts(index);
    if (finishing) {
        // The waveform can replace the editor while recording. Only a recording
        // started by this bridge can reach these actions; never use Send here.
        NSArray *buttons = indexedButtons(index, labels, nil);
        if (buttons.count > 1) return 23;
        if (buttons.count == 1) return pressButton(buttons[0], area, thread, labels);
        // Dictation may have ended automatically. An idle Dictate control is
        // evidence that no Stop/Cancel needs to be pressed, not a toggle target.
        NSArray *idle = indexedButtons(index, actionLabels(@"dictate-start"), nil);
        if (chatAreas(@[area], thread).count != 1) return 24;
        return idle.count == 1 ? 0 : 22;
    }
    if (starting) {
        NSArray *activeLabels = [actionLabels(@"dictate-stop") arrayByAddingObjectsFromArray:actionLabels(@"dictate-cancel")];
        NSArray *active = indexedButtons(index, activeLabels, nil);
        if (active.count) return 25; // Never take over manual dictation.
    }
    NSArray *paths = index[@"editors"];
    if (paths.count == 0) return 15;
    NSMutableArray *candidates = [NSMutableArray array];
    NSMutableArray *messageComposers = [NSMutableArray array];
    NSMutableArray *idleComposers = [NSMutableArray array];
    NSArray *idleLabels = [voiceLabels() arrayByAddingObjectsFromArray:resumeLabels()];
    for (NSArray *path in paths) {
        NSDictionary *candidate = nil;
        id idleCandidate = nil;
        BOOL hasSubmit = NO;
        for (NSInteger ancestor = (NSInteger)path.count - 2; ancestor >= 0; ancestor--) {
            NSArray *scope = [path subarrayWithRange:NSMakeRange(0, (NSUInteger)ancestor + 1)];
            NSUInteger editorCount = 0;
            for (NSArray *other in paths)
                if (insidePath(other, scope) && ++editorCount > 1) break;
            // A separate code editor/search field must not borrow a composer's
            // controls from their common ancestor. Multiple editors inside the
            // same composer remain ambiguous.
            if (editorCount != 1) break;
            NSArray *buttons = indexedButtons(index, labels, scope);
            NSArray *send = indexedButtons(index, actionLabels(@"send"), scope);
            hasSubmit = hasSubmit || send.count > 0;
            BOOL idleComposer = !send.count && indexedButtons(index, idleLabels, scope).count == 1;
            if (!starting && idleComposer) {
                idleCandidate = scope;
                // Finish checking this editor's ancestors: a submit control
                // can live outside its inner input/voice wrapper.
            }
            if (!buttons.count) continue;
            if (buttons.count != 1) return 23;
            if (!candidate) candidate = @{@"scope": scope, @"button": buttons[0], @"editor": path.lastObject};
            if (!starting) break;
            if (idleComposer) {
                idleCandidate = candidate;
            }
            // A pending question can expose its own Dictate input. The main
            // message composer also owns Send, even when Send is disabled for
            // an empty draft. Never borrow Send across a multi-editor ancestor.
            if (send.count == 1) {
                [messageComposers addObject:candidate];
                break;
            }
        }
        if (idleCandidate && !hasSubmit) [idleComposers addObject:idleCandidate];
        if (candidate) [candidates addObject:candidate];
    }
    // Voice/Resume identifies the empty main chat even when a separate
    // question exposes its own Send/Dictate pair.
    if (starting && idleComposers.count) candidates = idleComposers;
    else if (starting && messageComposers.count) candidates = messageComposers;
    if (!starting && idleComposers.count) {
        controlCounts[@"candidates"] = @0;
        if (idleComposers.count != 1) return 16;
        return chatAreas(@[area], thread).count == 1 ? 29 : 24;
    }
    controlCounts[@"candidates"] = @(candidates.count);
    if (candidates.count != 1) return paths.count > 1 ? 16 : 22;
    NSDictionary *candidate = candidates[0];
    if (focusing) {
        if (chatAreas(@[area], thread).count != 1) return 24;
        id editor = candidate[@"editor"];
        AXError error = AXUIElementSetAttributeValue((__bridge AXUIElementRef)editor,
                                                     kAXFocusedAttribute, kCFBooleanTrue);
        if (error != kAXErrorSuccess || ![attribute(editor, kAXFocusedAttribute) isEqual:@YES]) return 30;
        return 0;
    }
    {
        int result = pressButton(candidate[@"button"], area, thread, labels);
        if (result || !starting) return result;
        fputs("pressed\n", stdout); fflush(stdout);
        beginStage(@"ready_ms");
        // Observe readiness only. A microphone-permission prompt must be handled
        // by the user; never acknowledge it or press Start a second time.
        for (int retry = 0; retry < 25; retry++) {
            if (chatAreas(@[area], thread).count != 1) return 24;
            NSDictionary *local = controlIndex([candidate[@"scope"] lastObject]);
            NSArray *active = local ? indexedButtons(local, actionLabels(@"dictate-stop"), nil) : nil;
            // A renderer update can replace that control group. Read the
            // current area as a fallback, without repeating the Start action.
            if (!active.count) {
                NSDictionary *fresh = controlIndex(area);
                active = fresh ? indexedButtons(fresh, actionLabels(@"dictate-stop"), nil) : nil;
            }
            if (!active) return 20;
            if (active.count == 1) return 0;
            usleep(100000);
        }
        return 26;
    }
}

static int pressComposer(id area, NSString *thread) {
    return pressAction(area, thread, @"send");
}

static int composerAction(NSString *thread, NSString *action) {
    if (!thread.length || !actionLabels(action)) return 21;
    if (!AXIsProcessTrusted()) return 10;
    NSArray *apps = [NSRunningApplication runningApplicationsWithBundleIdentifier:@"com.openai.codex"];
    if (apps.count != 1) return 11;
    id app = CFBridgingRelease(AXUIElementCreateApplication([apps[0] processIdentifier]));
    AXUIElementSetMessagingTimeout((__bridge AXUIElementRef)app, 1);
    // Navigation may load a different chat. Poll discovery only; never poll or
    // retry the action. Multiple matching views are always ambiguous.
    NSArray *lastWindows = nil;
    NSMutableDictionary *rootDiagnostic = [NSMutableDictionary dictionary];
    enableAccessibility(app, rootDiagnostic);
    beginStage(@"target_ms");
    for (int retry = 0; retry < 40; retry++) {
        NSArray *windows = applicationRoots(app, rootDiagnostic);
        lastWindows = windows;
        NSArray *areas = chatAreas(windows, thread);
        if (!areas) return 20;
        if (areas.count > 1) return 14;
        if (areas.count == 1) {
            // Revalidate the selected route immediately before finding controls.
            NSArray *fresh = chatAreas(@[areas[0]], thread);
            if (fresh.count != 1) return 24;
            reportDraftDiscovery();
            beginStage(@"controls_ms");
            return [action isEqual:@"send"] ? pressComposer(areas[0], thread) : pressAction(areas[0], thread, action);
        }
        usleep(100000);
    }
    NSMutableDictionary *counts = [chatDiscoveryCounts(lastWindows, thread) mutableCopy];
    reportDraftDiscovery();
    [counts addEntriesFromDictionary:rootDiagnostic];
    id manual = attribute(app, CFSTR("AXManualAccessibility"));
    counts[@"enableStatusAvailable"] = @([manual isKindOfClass:NSNumber.class]);
    counts[@"enabled"] = @([manual isEqual:@YES]);
    id enhanced = attribute(app, CFSTR("AXEnhancedUserInterface"));
    counts[@"enhancedStatusAvailable"] = @([enhanced isKindOfClass:NSNumber.class]);
    counts[@"enhancedEnabled"] = @([enhanced isEqual:@YES]);
    NSData *diagnostic = [NSJSONSerialization dataWithJSONObject:counts
                                                       options:0 error:NULL];
    if (diagnostic) {
        [[NSFileHandle fileHandleWithStandardError] writeData:diagnostic];
        fputc('\n', stderr);
    }
    return [counts[@"webAreas"] unsignedIntegerValue] == 0 ? 27 : 13;
}

int main(void) {
    @autoreleasepool {
        NSData *data = [NSFileHandle.fileHandleWithStandardInput readDataToEndOfFile];
        id request = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        if (![request isKindOfClass:NSDictionary.class] ||
            ![request[@"thread"] isKindOfClass:NSString.class] ||
            ![request[@"action"] isKindOfClass:NSString.class]) return 21;
        id title = request[@"title"];
        if (title && (![title isKindOfClass:NSString.class] || ![title length])) return 21;
        id project = request[@"draftProject"];
        if (project && (![project isKindOfClass:NSString.class] || ![project length] ||
                ![request[@"thread"] hasPrefix:@"@new:"])) return 21;
        draftProject = project;
        sidebarTitles = title ? @{request[@"thread"]: title} : nil;
        // No prompt, chat identity, or OS errors are printed or placed in argv.
        nativeTiming = [@{@"setup_ms": @0, @"target_ms": @0, @"controls_ms": @0,
            @"press_ms": @0, @"ready_ms": @0} mutableCopy];
        controlCounts = [@{@"editors": @0, @"buttons": @0, @"candidates": @0,
            @"scan_complete": @0, @"submit_buttons": @0, @"dictate_buttons": @0,
            @"stop_buttons": @0, @"resume_buttons": @0, @"voice_buttons": @0} mutableCopy];
        beginStage(@"setup_ms");
        int result = composerAction(request[@"thread"], request[@"action"]);
        beginStage(nil);
        for (NSString *key in nativeTiming.allKeys)
            nativeTiming[key] = @((NSUInteger)[nativeTiming[key] doubleValue]);
        NSData *timing = [NSJSONSerialization dataWithJSONObject:nativeTiming options:0 error:NULL];
        if (timing) {
            [[NSFileHandle fileHandleWithStandardError] writeData:timing];
            fputc('\n', stderr);
        }
        NSData *controls = [NSJSONSerialization dataWithJSONObject:controlCounts options:0 error:NULL];
        if (controls) {
            [[NSFileHandle fileHandleWithStandardError] writeData:controls];
            fputc('\n', stderr);
        }
        return result;
    }
}
