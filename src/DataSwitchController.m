#import "DataSwitchController.h"
#import "DataSwitchGlyph.h"
#import <QuartzCore/QuartzCore.h>

@interface DataSwitchController ()
@property(nonatomic,strong) UIButton *compactButton;
@property(nonatomic,strong) UIView *panel;
@property(nonatomic,strong) UIImageView *headerIcon;
@property(nonatomic,strong) UILabel *heading;
@property(nonatomic,strong) UILabel *message;
@property(nonatomic,strong) UIView *headerLine;
@property(nonatomic,strong) UIView *rowLine;
@property(nonatomic,strong) NSArray<DataSwitchRow *> *rows;
@property(nonatomic,strong) NSArray<DataSwitchItem *> *items;
@property(nonatomic,strong) NSTimer *refreshTimer;
@property(nonatomic) BOOL expanded;
@property(nonatomic) BOOL busy;
@property(nonatomic) BOOL reading;
@property(nonatomic) NSUInteger readGeneration;
- (void)updateExpandedAppearance;
- (void)reload;
- (void)chooseRow:(DataSwitchRow *)row;
- (void)openPanel;
- (void)press:(UILongPressGestureRecognizer *)gesture;
- (void)stopRefresh;
@end

@implementation DataSwitchController
- (void)loadView {
    self.view=[[UIView alloc] initWithFrame:CGRectMake(0,0,64,64)];
    self.view.backgroundColor=UIColor.clearColor;
    self.compactButton=[UIButton buttonWithType:UIButtonTypeCustom];
    [self.compactButton setImage:DataSwitchLoadGlyph(self.class,YES) forState:UIControlStateNormal];
    self.compactButton.imageView.contentMode=UIViewContentModeCenter;
    self.compactButton.tintColor=UIColor.whiteColor;
    self.compactButton.accessibilityLabel=@"数据切换";
    self.compactButton.accessibilityHint=@"轻点选择默认蜂窝数据线路";
    [self.compactButton addTarget:self action:@selector(openPanel) forControlEvents:UIControlEventTouchUpInside];
    UILongPressGestureRecognizer *press=[[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(press:)];
    press.minimumPressDuration=.35;
    press.cancelsTouchesInView=YES;
    [self.compactButton addGestureRecognizer:press];
    [self.view addSubview:self.compactButton];
    self.panel=[UIView new];
    self.panel.backgroundColor=UIColor.clearColor;
    [self.view addSubview:self.panel];
    self.headerIcon=[[UIImageView alloc] initWithImage:DataSwitchLoadGlyph(self.class,NO)];
    self.headerIcon.tintColor=UIColor.whiteColor;
    self.headerIcon.contentMode=UIViewContentModeScaleAspectFit;
    [self.panel addSubview:self.headerIcon];
    self.heading=[UILabel new];
    self.heading.text=@"数据切换";
    self.heading.textColor=UIColor.whiteColor;
    self.heading.textAlignment=NSTextAlignmentCenter;
    self.heading.font=[UIFont systemFontOfSize:18 weight:UIFontWeightSemibold];
    [self.panel addSubview:self.heading];
    self.headerLine=[UIView new];
    self.headerLine.backgroundColor=[UIColor colorWithWhite:1 alpha:.25];
    [self.panel addSubview:self.headerLine];
    self.rowLine=[UIView new];
    self.rowLine.backgroundColor=[UIColor colorWithWhite:1 alpha:.10];
    [self.panel addSubview:self.rowLine];
    NSMutableArray *rows=[NSMutableArray array];
    for (NSInteger slot=1;slot<=2;slot++) {
        DataSwitchRow *row=[[DataSwitchRow alloc] initWithFrame:CGRectZero];
        row.tag=slot;
        [row addTarget:self action:@selector(chooseRow:) forControlEvents:UIControlEventTouchUpInside];
        [self.panel addSubview:row];
        [rows addObject:row];
    }
    self.rows=rows;
    self.message=[UILabel new];
    self.message.font=[UIFont systemFontOfSize:14];
    self.message.textAlignment=NSTextAlignmentCenter;
    self.message.textColor=UIColor.whiteColor;
    self.message.numberOfLines=2;
    [self.panel addSubview:self.message];
    [self updateExpandedAppearance];
}
- (double)preferredExpandedContentHeight { return 236.0; }
- (double)preferredExpandedContentWidth { return 336.0; }
- (bool)providesOwnPlatter { return false; }
- (bool)shouldBeginTransitionToExpandedContentModule { return !self.busy; }
- (bool)shouldFinishTransitionToExpandedContentModule { return true; }
- (bool)canDismissPresentedContent { return !self.busy; }
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    CGFloat width=CGRectGetWidth(self.view.bounds),height=CGRectGetHeight(self.view.bounds);
    self.compactButton.frame=self.view.bounds;
    self.panel.frame=self.view.bounds;
    self.headerIcon.frame=CGRectMake((width-32)*.5,20,32,32);
    self.heading.frame=CGRectMake(16,62,MAX(0,width-32),27);
    CGFloat pixel=1.0/MAX(1.0,self.view.window.screen.scale ?: UIScreen.mainScreen.scale);
    self.headerLine.frame=CGRectMake(0,102,width,pixel);
    CGFloat rowHeight=MAX(0,(height-102)*.5);
    for (NSUInteger i=0;i<self.rows.count;i++) self.rows[i].frame=CGRectMake(0,102+i*rowHeight,width,rowHeight);
    self.rowLine.frame=CGRectMake(16,102+rowHeight,MAX(0,width-32),pixel);
    self.message.frame=CGRectMake(16,110,MAX(0,width-32),MAX(0,height-120));
}
- (void)openPanel {
    if (self.busy || self.expanded || ![self.moduleContext respondsToSelector:@selector(requestExpandModule)]) return;
    [self.moduleContext requestExpandModule];
}
- (void)press:(UILongPressGestureRecognizer *)gesture {
    if (gesture.state==UIGestureRecognizerStateBegan) [self openPanel];
}
- (void)updateExpandedAppearance {
    self.compactButton.hidden=self.expanded;
    self.panel.hidden=!self.expanded;
    BOOL hasRows=self.items.count==2;
    self.message.hidden=hasRows;
    self.rowLine.hidden=!hasRows;
    for (DataSwitchRow *row in self.rows) {
        row.hidden=!hasRows;
        for (DataSwitchItem *item in self.items) if (item.slot==row.tag) [row updateWithItem:item busy:self.busy];
    }
    [self.view setNeedsLayout];
}
- (void)reload {
    if (self.busy || self.reading || !self.expanded) return;
    NSUInteger generation=++self.readGeneration;
    self.reading=YES;
    if (!self.items.count) self.message.text=@"正在读取数据线路…";
    __weak typeof(self) weakSelf=self;
    [self.service readItems:^(NSArray<DataSwitchItem *> *items,NSString *error) {
        typeof(self) self=weakSelf;
        if (!self || generation!=self.readGeneration) return;
        self.reading=NO;
        self.items=items;
        self.message.text=error ?: @"无法读取数据线路";
        [self updateExpandedAppearance];
    }];
}
- (void)stopRefresh {
    [self.refreshTimer invalidate];
    self.refreshTimer=nil;
    self.readGeneration++;
    self.reading=NO;
}
- (void)willTransitionToExpandedContentMode:(bool)expanded {
    self.expanded=expanded;
    [self updateExpandedAppearance];
    if (expanded) [self reload];
    else [self stopRefresh];
}
- (void)didTransitionToExpandedContentMode:(bool)expanded {
    self.expanded=expanded;
    [self updateExpandedAppearance];
    [self.refreshTimer invalidate];
    self.refreshTimer=nil;
    if (expanded) {
        __weak typeof(self) weakSelf=self;
        self.refreshTimer=[NSTimer scheduledTimerWithTimeInterval:1 repeats:YES block:^(NSTimer *timer) {
            typeof(self) self=weakSelf;
            if (!self || !self.expanded) { [timer invalidate]; return; }
            [self reload];
        }];
    } else [self stopRefresh];
}
- (void)controlCenterWillPresent { if (self.expanded) [self reload]; }
- (void)controlCenterDidDismiss {
    self.expanded=NO;
    [self stopRefresh];
    self.items=@[];
    [self updateExpandedAppearance];
}
- (void)chooseRow:(DataSwitchRow *)row {
    if (self.busy) return;
    DataSwitchItem *selected=nil;
    for (DataSwitchItem *item in self.items) if (item.slot==row.tag) selected=item;
    if (!selected.available || !selected.selectionKnown) return;
    self.busy=YES;
    [self stopRefresh];
    [self updateExpandedAppearance];
    __weak typeof(self) weakSelf=self;
    [self.service selectItem:selected completion:^(BOOL accepted,NSString *error) {
        typeof(self) self=weakSelf;
        if (!self) return;
        self.busy=NO;
        if (accepted) {
            if ([self.moduleContext respondsToSelector:@selector(dismissModule)]) [self.moduleContext dismissModule];
        } else if (self.expanded) {
            self.items=@[];
            self.message.text=error ?: @"蜂窝数据切换失败";
            [self updateExpandedAppearance];
        }
    }];
}
- (void)dealloc { [_refreshTimer invalidate]; }
@end
