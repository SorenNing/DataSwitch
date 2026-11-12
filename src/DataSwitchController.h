#import "DataSwitchTypes.h"
#import "DataSwitchPrivate.h"

@interface DataSwitchController : UIViewController <CCUIContentModuleContentViewController>
@property(nonatomic,strong) DataSwitchService *service;
@property(nonatomic,strong) CCUIContentModuleContext *moduleContext;
@end
