#import "DataSwitchTypes.h"
#import "DataSwitchPrivate.h"
#import "DataSwitchRuntime.h"
#import <CoreTelephony/CTCarrier.h>
#import <CoreTelephony/CTTelephonyNetworkInfo.h>

@implementation DataSwitchItem
- (instancetype)init {
    if ((self=[super init])) _name=@"运营商未知";
    return self;
}
@end

static NSString *DSString(id value) {
    if (![value isKindOfClass:NSString.class]) return nil;
    NSString *text=[value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    return text.length?text:nil;
}
static NSString *DSChineseCarrier(NSString *mcc, NSString *mnc) {
    if (![mcc isEqualToString:@"460"] || !mnc.length) return nil;
    if ([@[@"00",@"02",@"04",@"07",@"08"] containsObject:mnc]) return @"中国移动";
    if ([@[@"01",@"06",@"09"] containsObject:mnc]) return @"中国联通";
    if ([@[@"03",@"05",@"11"] containsObject:mnc]) return @"中国电信";
    if ([mnc isEqualToString:@"15"]) return @"中国广电";
    return nil;
}
static NSString *DSNormalizeCarrier(NSString *value) {
    NSString *text=DSString(value);
    if (!text || [@[@"--",@"Carrier",@"运营商",@"Unknown",@"未知"] containsObject:text]) return nil;
    NSString *lower=text.lowercaseString;
    if ([lower containsString:@"unicom"] || [text containsString:@"联通"]) return @"中国联通";
    if ([lower containsString:@"china telecom"] || [lower isEqualToString:@"ctcc"] || [text containsString:@"电信"]) return @"中国电信";
    if ([lower containsString:@"china mobile"] || [lower isEqualToString:@"cmcc"] || [text containsString:@"移动"]) return @"中国移动";
    if ([lower containsString:@"china broadnet"] || [text containsString:@"广电"]) return @"中国广电";
    return text;
}

static NSInteger DSSlotForContext(id context) {
    if (!context || ![context respondsToSelector:@selector(slotID)]) return 0;
    NSMethodSignature *sig=[context methodSignatureForSelector:@selector(slotID)];
    if (!sig || sig.numberOfArguments!=2 || strcmp(DSTrimType(sig.methodReturnType),"q")) return 0;
    long long slot=[(CTXPCServiceSubscriptionContext *)context slotID];
    return slot>=1 && slot<=2 ? (NSInteger)slot : 0;
}
static NSUUID *DSUUID(id context) {
    id value=DSReadObject(context,@selector(uuid));
    return [value isKindOfClass:NSUUID.class]?value:nil;
}
static id DSSystemTelephonyClient(void) {
    Class cls=NSClassFromString(@"SBTelephonyManager");
    SEL selector=NSSelectorFromString(@"sharedTelephonyManagerCreatingIfNecessary:");
    if (!cls || ![cls respondsToSelector:selector]) return nil;
    NSMethodSignature *sig=[cls methodSignatureForSelector:selector];
    if (!sig || sig.numberOfArguments!=3 || DSTrimType(sig.methodReturnType)[0]!='@') return nil;
    const char *arg=DSTrimType([sig getArgumentTypeAtIndex:2]);
    if (strcmp(arg,"B") && strcmp(arg,"c")) return nil;
    NSInvocation *call=[NSInvocation invocationWithMethodSignature:sig];
    call.target=cls; call.selector=selector;
    BOOL create=YES; [call setArgument:&create atIndex:2]; [call invoke];
    __unsafe_unretained id manager=nil; [call getReturnValue:&manager];
    return DSReadObject(manager,NSSelectorFromString(@"coreTelephonyClient"));
}

@interface DataSwitchService ()
@property(nonatomic,strong) CoreTelephonyClient *client;
@property(nonatomic,strong) CTTelephonyNetworkInfo *network;
@property(nonatomic,strong) dispatch_queue_t workQueue;
- (NSArray<DataSwitchItem *> *)readNow;
- (id)currentDataContext:(NSError **)error;
@end

@implementation DataSwitchService
- (instancetype)init {
    if (!(self=[super init])) return nil;
    _workQueue=dispatch_queue_create("com.ning.dataswitch.telephony",DISPATCH_QUEUE_SERIAL);
    @try { _client=DSSystemTelephonyClient(); }
    @catch (__unused NSException *exception) { _client=nil; }
    if (!_client) {
        Class cls=NSClassFromString(@"CoreTelephonyClient");
        if ([cls instancesRespondToSelector:@selector(initWithQueue:)])
            _client=[[(id)cls alloc] initWithQueue:dispatch_get_main_queue()];
    }
    _network=[CTTelephonyNetworkInfo new];
    return self;
}
- (NSString *)carrierForContext:(CTXPCServiceSubscriptionContext *)context {
    NSError *error=nil;
    NSString *name=nil;
    // The SIM's home PLMN is stable while roaming; never use the user-editable SIM label.
    if ([self.client respondsToSelector:@selector(copyMobileSubscriberCountryCode:error:)] &&
        [self.client respondsToSelector:@selector(copyMobileSubscriberNetworkCode:error:)]) {
        NSString *mcc=DSString([self.client copyMobileSubscriberCountryCode:context error:&error]);
        error=nil;
        NSString *mnc=DSString([self.client copyMobileSubscriberNetworkCode:context error:&error]);
        name=DSChineseCarrier(mcc,mnc);
    }
    // Legacy carrier metadata is only a UUID-matched fallback after home PLMN.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    NSDictionary<NSString *,CTCarrier *> *providers=self.network.serviceSubscriberCellularProviders;
    NSUUID *uuid=[context respondsToSelector:@selector(uuid)]?context.uuid:nil;
    // Match a provider only by this subscription UUID. Dictionary ordering is not a card-slot identity.
    CTCarrier *carrier=nil;
    if (uuid) for (NSString *key in providers) {
        if ([key caseInsensitiveCompare:uuid.UUIDString]==NSOrderedSame) { carrier=providers[key]; break; }
    }
    if (!name && carrier) name=DSNormalizeCarrier(carrier.carrierName) ?: DSChineseCarrier(carrier.mobileCountryCode,carrier.mobileNetworkCode);
#pragma clang diagnostic pop
    if (!name && [self.client respondsToSelector:@selector(getLocalizedOperatorName:error:)]) {
        error=nil; name=DSNormalizeCarrier([self.client getLocalizedOperatorName:context error:&error]);
    }
    if (!name && [self.client respondsToSelector:@selector(getOperatorName:error:)]) {
        error=nil; name=DSNormalizeCarrier([self.client getOperatorName:context error:&error]);
    }
    return name;
}

- (id)currentDataContext:(NSError **)error {
    // Same getter used by the original CCSwitchData menu's selected state.
    if (!DSMethodMatches(self.client,@selector(getCurrentDataSubscriptionContextSync:),"@",@[@"^@"])) {
        if (error) *error=[NSError errorWithDomain:@"com.ning.dataswitch" code:1 userInfo:nil];
        return nil;
    }
    return [self.client getCurrentDataSubscriptionContextSync:error];
}
- (NSArray<DataSwitchItem *> *)readNow {
    if (!self.client || ![self.client respondsToSelector:@selector(getSIMStatus:error:)]) return @[];
    NSMutableDictionary<NSNumber *,id> *contexts=[NSMutableDictionary dictionary];
    NSMutableSet<NSNumber *> *ambiguous=[NSMutableSet set];
    if (DSMethodMatches(self.client,@selector(getSubscriptionInfoWithError:),"@",@[@"^@"])) {
        NSError *error=nil;
        id info=[self.client getSubscriptionInfoWithError:&error];
        id subscriptions=DSReadObject(info,NSSelectorFromString(@"subscriptions"));
        if (!error && [subscriptions isKindOfClass:NSArray.class]) for (id context in subscriptions) {
            NSInteger slot=DSSlotForContext(context);
            if (slot) {
                NSNumber *key=@(slot);
                if (contexts[key]) [ambiguous addObject:key];
                else contexts[key]=context;
            }
        }
    }
    NSError *selectionError=nil;
    id selected=[self currentDataContext:&selectionError];
    NSInteger selectedSlot=DSSlotForContext(selected);
    NSUUID *selectedUUID=DSUUID(selected);
    BOOL known=!selectionError && selected && (selectedSlot || selectedUUID);
    Class contextClass=NSClassFromString(@"CTXPCServiceSubscriptionContext");
    NSMutableArray *items=[NSMutableArray array];
    for (NSInteger slot=1;slot<=2;slot++) {
        id context=contexts[@(slot)];
        if (!context && [contextClass respondsToSelector:@selector(contextWithSlot:)])
            context=[contextClass contextWithSlot:slot];
        DataSwitchItem *item=[DataSwitchItem new];
        item.slot=slot; item.context=context; item.subscriptionUUID=DSUUID(context);
        item.name=(context?[self carrierForContext:context]:nil) ?: @"运营商未知";
        NSError *error=nil;
        NSString *status=context?DSString([self.client getSIMStatus:context error:&error]):nil;
        item.available=context && !error && ![ambiguous containsObject:@(slot)] && [status isEqualToString:@"kCTSIMSupportSIMStatusReady"];
        item.selectionKnown=known && ![ambiguous containsObject:@(slot)];
        // UUIDs dominate slot order; a removed/replaced subscription must not inherit selection.
        if (known && selectedUUID && item.subscriptionUUID) item.selected=[selectedUUID isEqual:item.subscriptionUUID];
        else if (known) item.selected=selectedSlot==slot;
        [items addObject:item];
    }
    return items;
}
- (void)readItems:(DataSwitchReadCompletion)completion {
    dispatch_async(self.workQueue,^{
        NSArray *items=nil; NSString *message=nil;
        @try { items=[self readNow]; if (!items.count) message=@"无法读取数据线路"; }
        @catch (__unused NSException *exception) { message=@"无法读取数据线路"; }
        dispatch_async(dispatch_get_main_queue(),^{ completion(items ?: @[],message); });
    });
}
- (void)selectItem:(DataSwitchItem *)item completion:(DataSwitchActionCompletion)completion {
    NSInteger slot=item.slot;
    NSUUID *expectedUUID=[item.subscriptionUUID copy];
    dispatch_async(self.workQueue,^{
        NSString *message=nil; BOOL accepted=NO;
        @try {
            DataSwitchItem *fresh=nil;
            for (DataSwitchItem *value in [self readNow]) if (value.slot==slot) fresh=value;
            if (slot<1 || slot>2 || !fresh.available || !fresh.selectionKnown) message=@"此数据线路当前不可用";
            else if (expectedUUID && ![expectedUUID isEqual:fresh.subscriptionUUID]) message=@"SIM 信息已变化，请重新选择";
            else if (fresh.selected) accepted=YES;
            else if (!DSMethodMatches(self.client,@selector(setActiveUserDataSelection:error:),"v",@[@"@",@"^@"]) ||
                     !DSMethodMatches(fresh.context,@selector(setUserDataPreferred:),"v",@[@"@"]))
                message=@"系统数据切换接口不可用";
            else {
                NSError *error=nil;
                id target=[fresh.context respondsToSelector:@selector(copyWithZone:)]?[fresh.context copy]:nil;
                if (!target || DSSlotForContext(target)!=slot ||
                    (fresh.subscriptionUUID && ![fresh.subscriptionUUID isEqual:DSUUID(target)])) {
                    message=@"无法确认目标数据线路";
                } else {
                    [(CTXPCServiceSubscriptionContext *)target setUserDataPreferred:@YES];
                    // Retain the fresh subscription identity, then use the original void setter.
                    [self.client setActiveUserDataSelection:target error:&error];
                }
                // The setter returns void. Only NSError reports an immediate refusal.
                // Never use a guessed BOOL return or optimistically swap the displayed selection.
                accepted=!message && error==nil;
                if (!accepted && !message) message=@"蜂窝数据切换请求失败";
            }
        } @catch (__unused NSException *exception) { message=@"蜂窝数据切换请求失败"; }
        dispatch_async(dispatch_get_main_queue(),^{ completion(accepted,message); });
    });
}
@end
