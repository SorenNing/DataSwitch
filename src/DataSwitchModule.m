#import "DataSwitchController.h"

@interface DataSwitchModule : NSObject <CCUIContentModule>
@property(nonatomic,strong) DataSwitchController *controller;
@property(nonatomic,strong) CCUIContentModuleContext *contentModuleContext;
@end

@implementation DataSwitchModule
- (UIViewController<CCUIContentModuleContentViewController> *)contentViewController {
    if (!self.controller) {
        self.controller=[DataSwitchController new];
        self.controller.service=[DataSwitchService new];
        self.controller.moduleContext=self.contentModuleContext;
    }
    return self.controller;
}
- (void)setContentModuleContext:(CCUIContentModuleContext *)context {
    _contentModuleContext=context;
    self.controller.moduleContext=context;
}
- (UIViewController *)backgroundViewController { return nil; }
@end
