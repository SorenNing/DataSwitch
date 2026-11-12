#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <string.h>

static inline const char *DSTrimType(const char *type) {
    if (!type) return "";
    while (*type && strchr("rnNoORV",*type)) type++;
    return type;
}
static inline BOOL DSMethodMatches(id object, SEL selector, const char *result, NSArray<NSString *> *arguments) {
    if (!object || ![object respondsToSelector:selector]) return NO;
    NSMethodSignature *sig=[object methodSignatureForSelector:selector];
    if (!sig || sig.numberOfArguments!=arguments.count+2) return NO;
    const char *ret=DSTrimType(sig.methodReturnType);
    if (strcmp(result,"@")==0) {
        if (ret[0]!='@' || ret[1]=='?') return NO;
    } else if (strcmp(ret,result)) return NO;
    for (NSUInteger i=0;i<arguments.count;i++) {
        const char *actual=DSTrimType([sig getArgumentTypeAtIndex:i+2]);
        const char *wanted=arguments[i].UTF8String;
        if (strcmp(wanted,"@")==0) { if (actual[0]!='@' || actual[1]=='?') return NO; }
        else if (strcmp(wanted,"^@")==0) { if (actual[0]!='^' || DSTrimType(actual+1)[0]!='@') return NO; }
        else if (strcmp(actual,wanted)) return NO;
    }
    return YES;
}
static inline id DSReadObject(id object, SEL selector) {
    if (!DSMethodMatches(object,selector,"@",@[])) return nil;
    NSInvocation *call=[NSInvocation invocationWithMethodSignature:[object methodSignatureForSelector:selector]];
    call.target=object; call.selector=selector;
    [call invoke];
    __unsafe_unretained id result=nil;
    [call getReturnValue:&result];
    return result;
}
