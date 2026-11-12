#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface DataSwitchItem : NSObject
@property(nonatomic) NSInteger slot;
@property(nonatomic,copy) NSString *name;
@property(nonatomic,copy,nullable) NSUUID *subscriptionUUID;
@property(nonatomic,strong,nullable) id context;
@property(nonatomic) BOOL selected;
@property(nonatomic) BOOL selectionKnown;
@property(nonatomic) BOOL available;
@end

typedef void (^DataSwitchReadCompletion)(NSArray<DataSwitchItem *> *items, NSString * _Nullable error);
typedef void (^DataSwitchActionCompletion)(BOOL accepted, NSString * _Nullable error);

@interface DataSwitchService : NSObject
- (void)readItems:(DataSwitchReadCompletion)completion;
- (void)selectItem:(DataSwitchItem *)item completion:(DataSwitchActionCompletion)completion;
@end

@interface DataSwitchRow : UIControl
- (void)updateWithItem:(DataSwitchItem *)item busy:(BOOL)busy;
@end

NS_ASSUME_NONNULL_END
