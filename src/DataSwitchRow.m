#import "DataSwitchTypes.h"
#import <QuartzCore/QuartzCore.h>

@interface DataSwitchRow ()
@property(nonatomic,strong) UILabel *badge;
@property(nonatomic,strong) UILabel *carrier;
@end

@implementation DataSwitchRow
- (instancetype)initWithFrame:(CGRect)frame {
    if (!(self=[super initWithFrame:frame])) return nil;
    self.isAccessibilityElement=YES;
    self.accessibilityTraits=UIAccessibilityTraitButton;
    _badge=[UILabel new];
    _badge.font=[UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    _badge.textAlignment=NSTextAlignmentCenter;
    _badge.textColor=UIColor.whiteColor;
    _badge.layer.cornerRadius=11.5;
    _badge.layer.cornerCurve=kCACornerCurveContinuous;
    _badge.clipsToBounds=YES;
    _carrier=[UILabel new];
    _carrier.font=[UIFont systemFontOfSize:16];
    _carrier.textColor=UIColor.whiteColor;
    _carrier.adjustsFontSizeToFitWidth=YES;
    _carrier.minimumScaleFactor=0.75;
    [self addSubview:_badge];
    [self addSubview:_carrier];
    return self;
}
- (void)updateWithItem:(DataSwitchItem *)item busy:(BOOL)busy {
    self.enabled=item.available && item.selectionKnown && !busy;
    self.accessibilityTraits=UIAccessibilityTraitButton|(item.selected?UIAccessibilityTraitSelected:0);
    self.badge.text=busy?@"处理中":(!item.available?@"不可用":(!item.selectionKnown?@"状态未知":(item.selected?@"使用中":@"未选用")));
    self.badge.backgroundColor=item.available && item.selected?[UIColor colorWithRed:0.20 green:0.78 blue:0.35 alpha:1]:[UIColor colorWithWhite:1 alpha:0.16];
    self.carrier.text=item.name;
    self.alpha=item.available?1:0.55;
    self.accessibilityLabel=[NSString stringWithFormat:@"%@，%@",item.name,self.badge.text];
    self.accessibilityHint=item.selected?@"当前默认数据线路":@"轻点将此卡设为默认蜂窝数据线路";
    [self setNeedsLayout];
}
- (void)layoutSubviews {
    [super layoutSubviews];
    CGFloat width=CGRectGetWidth(self.bounds),height=CGRectGetHeight(self.bounds);
    CGFloat badgeWidth=MAX(64,ceil([self.badge sizeThatFits:CGSizeMake(CGFLOAT_MAX,23)].width)+20);
    CGFloat gap=12,available=MAX(0,width-32);
    CGFloat carrierWidth=MIN(ceil([self.carrier sizeThatFits:CGSizeMake(CGFLOAT_MAX,height)].width),MAX(0,available-badgeWidth-gap));
    CGFloat x=(width-badgeWidth-gap-carrierWidth)*0.5;
    self.badge.frame=CGRectMake(x,(height-23)*0.5,badgeWidth,23);
    self.carrier.frame=CGRectMake(x+badgeWidth+gap,0,carrierWidth,height);
}
- (void)setHighlighted:(BOOL)highlighted {
    [super setHighlighted:highlighted];
    self.backgroundColor=highlighted?[UIColor colorWithWhite:1 alpha:0.08]:UIColor.clearColor;
}
@end
